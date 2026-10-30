"""services/takeaway_service.py — ระบบสั่งกลับบ้าน (Takeaway POS) สำหรับพนักงานและเจ้าของร้าน

รองรับ:
- ลูกค้าสั่งกลับบ้านโดยไม่ต้องสแกนเข้าโต๊ะ (พนักงาน/เจ้าของร้านเป็นผู้บันทึกรายการทั้งหมด)
- ส่วนที่ 1: รายการชั่งกิโล (เนื้อสัตว์ต่าง ๆ ต้องซื้อรวมกันขั้นต่ำ 1 กิโลกรัม = 1,000 กรัม ขึ้นไป)
  ใช้น้ำหนักที่ชั่งจริง และหากมีการกดเพิ่มซ้ำจะนำไปรวมกันในหัวข้อเดียวกันฝั่งซ้าย
- ส่วนที่ 2: รายการของเสริม/อื่น ๆ (ผัก เครื่องดื่ม ของทานเล่น ฯลฯ) ซื้อจำนวนเท่าไหร่ก็ได้ (หรือซื้อแต่เนื้ออย่างเดียวก็ได้)
  ตรวจสอบสต๊อกคงเหลือจริงใน transaction
- ชำระเงินด้วย เงินสด (cash) หรือ โอน/พร้อมเพย์ (transfer/promptpay) คำนวณส่วนลดโปรโมชั่น ค่าบริการ และ VAT ตามตั้งค่าร้าน
- บันทึกลงตาราง bills, weigh_entries, orders, order_items, ตัดสต๊อก, ออกสลิปใบเสร็จ (PDF/TXT/พิมพ์) และบันทึก activity_log ครบถ้วน
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import config
from database import db
from services import (
    checkout_service,
    log_service,
    menu_service,
    pricing_service,
    promo_service,
    qr_service,
    stock_service,
    weigh_service,
)

TAKEAWAY_TABLE_NO = 0
TAKEAWAY_TABLE_NAME = "สั่งกลับบ้าน"
MIN_TAKEAWAY_WEIGH_GRAMS = getattr(config, "MIN_FIRST_WEIGH_GRAMS", 1000)
MAX_TAKEAWAY_WEIGH_GRAMS = 50_000
MAX_QTY_PER_LINE = 99


def ensure_takeaway_table(conn=None) -> dict:
    """คืนแถวโต๊ะพิเศษสำหรับ 'สั่งกลับบ้าน' (table_no = 0, active = 0 เพื่อไม่ให้ปนในหน้าสถานะโต๊ะปกติ)"""
    from database.seed import make_secret_key

    def _do(c) -> dict:
        row = db.query_one("SELECT * FROM tables WHERE table_no = ?", (TAKEAWAY_TABLE_NO,), conn=c)
        if row is not None:
            if row["active"] != 0 or row["name"] != TAKEAWAY_TABLE_NAME:
                db.execute(
                    "UPDATE tables SET name = ?, active = 0 WHERE id = ?",
                    (TAKEAWAY_TABLE_NAME, row["id"]),
                    conn=c,
                )
                row = db.query_one("SELECT * FROM tables WHERE id = ?", (row["id"],), conn=c)
            return dict(row)
        tid = db.execute(
            "INSERT INTO tables (table_no, name, secret_key, active, created_at) VALUES (?, ?, ?, 0, ?)",
            (TAKEAWAY_TABLE_NO, TAKEAWAY_TABLE_NAME, make_secret_key(), db.now_str()),
            conn=c,
        )
        return dict(db.query_one("SELECT * FROM tables WHERE id = ?", (tid,), conn=c))

    if conn is not None:
        return _do(conn)
    with db.transaction() as c:
        return _do(c)


def get_takeaway_catalog() -> dict:
    """ดึงข้อมูลเมนูชั่งกิโล หมวดหมู่และรายการของเสริม สต๊อกคงเหลือ อัตราภาษี/ค่าบริการ และโปรโมชั่นสำหรับหน้าสั่งกลับบ้าน"""
    rate = weigh_service.get_price_per_kg()
    default_weighed = weigh_service.get_default_weighed_item()
    all_items = menu_service.list_items(include_inactive=False)
    categories = menu_service.list_categories(include_inactive=False)

    weighed_items = [it for it in all_items if it["item_type"] == config.MENU_TYPE_WEIGHED]
    normal_items = [it for it in all_items if it["item_type"] == config.MENU_TYPE_NORMAL]

    # หมวดหมู่ที่มีเมนูประเภท normal
    normal_cat_ids = {it["category_id"] for it in normal_items}
    normal_categories = [c for c in categories if c["id"] in normal_cat_ids]

    rates = pricing_service.get_rates()
    promos = promo_service.list_available(subtotal=None)

    return {
        "rate": rate,
        "default_weighed_item": {
            "id": default_weighed["id"],
            "name": weigh_service.DEFAULT_WEIGH_NAME,
            "price": rate,
            "unit": "กก.",
        },
        "weighed_items": weighed_items,
        "categories": normal_categories,
        "normal_items": normal_items,
        "min_weigh_grams": MIN_TAKEAWAY_WEIGH_GRAMS,
        "rates": rates,
        "promos": promos,
    }


def calculate_preview(
    weigh_grams: int,
    items: list[dict] | None = None,
    promo_id: int | None = None,
    conn=None,
) -> dict:
    """คำนวณยอดรายการสั่งกลับบ้าน (น้ำหนักรวมชั่งกิโล + รายการของเสริม + โปรโมชั่น + ค่าบริการ + VAT)"""
    w_grams = int(weigh_grams or 0)
    if w_grams < 0:
        raise ValueError("น้ำหนักต้องไม่ติดลบ")

    rate = weigh_service.get_price_per_kg(conn=conn)
    weigh_amount = weigh_service.calc_amount(w_grams, rate) if w_grams > 0 else 0.0

    # รวมรายการของเสริมชนิดเดียวกันเข้าด้วยกัน
    merged_qty: dict[int, int] = {}
    for raw in items or []:
        mid = int(raw.get("menu_item_id") or 0)
        qty = int(raw.get("quantity") or 0)
        if mid > 0 and qty > 0:
            merged_qty[mid] = merged_qty.get(mid, 0) + qty

    order_lines = []
    order_total = 0.0
    for mid, qty in merged_qty.items():
        if qty > MAX_QTY_PER_LINE:
            raise ValueError(f"จำนวนต่อรายการต้องไม่เกิน {MAX_QTY_PER_LINE}")
        m = menu_service.get_item(mid, conn=conn)
        if m is None or not m["active"]:
            raise ValueError("ไม่พบเมนูที่เลือก")
        if m["item_type"] != config.MENU_TYPE_NORMAL:
            raise ValueError(f"{m['name']} เป็นเมนูชั่งกิโล กรุณาใส่ในส่วนชั่งกิโล")
        unit_price = float(m["price"])
        line_total = float(
            (Decimal(str(unit_price)) * Decimal(qty)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        order_total = round(order_total + line_total, 2)
        order_lines.append({
            "menu_item_id": mid,
            "name": m["name"],
            "unit_price": unit_price,
            "quantity": qty,
            "unit": m.get("stock_unit") or "ชิ้น",
            "line_total": line_total,
            "stock_item_id": m.get("stock_item_id"),
            "stock_quantity": m.get("stock_quantity"),
            "is_sold_out": m.get("is_sold_out"),
        })

    subtotal = round(weigh_amount + order_total, 2)

    available_promos = []
    for p in promo_service.list_available(subtotal=subtotal):
        available_promos.append({
            **p,
            "display_label": f"{p['name']} ({p['label']}) ลด {p['discount']:,.2f}",
        })

    promo = None
    discount = 0.0
    selected_promo_id = None
    if promo_id is not None and subtotal > 0:
        try:
            promo = promo_service.check_applicable(promo_id, subtotal, conn=conn)
            discount = promo_service.calc_discount(promo, subtotal)
            selected_promo_id = promo["id"]
        except ValueError:
            promo = None
            discount = 0.0
            selected_promo_id = None

    rates = pricing_service.get_rates()
    totals = pricing_service.compute_totals(
        subtotal,
        discount,
        rates["service_charge_percent"],
        rates["vat_percent"],
    )

    return {
        "weigh_grams": w_grams,
        "weigh_kg": round(w_grams / config.GRAMS_PER_KG, 3),
        "weigh_kheed": round(w_grams / (config.GRAMS_PER_KG / config.KHEED_PER_KG), 2),
        "price_per_kg": rate,
        "weigh_total": weigh_amount,
        "order_lines": order_lines,
        "order_total": order_total,
        "subtotal": totals["subtotal"],
        "promo_id": selected_promo_id,
        "promo_name": promo["name"] if promo else None,
        "discount": totals["discount"],
        "after_discount": totals["after_discount"],
        "service_charge_enabled": rates["service_charge_enabled"],
        "service_charge_percent": rates["service_charge_percent"],
        "service_charge": totals["service_charge"],
        "vat_enabled": rates["vat_enabled"],
        "vat_percent": rates["vat_percent"],
        "vat": totals["vat"],
        "total": totals["total"],
        "available_promos": available_promos,
    }


def checkout_takeaway(
    weigh_grams: int,
    items: list[dict] | None,
    payment_method: str,
    user_id: int,
    promo_id: int | None = None,
    amount_received=checkout_service._UNSET,
    note: str | None = None,
) -> dict:
    """บันทึกคำสั่งซื้อกลับบ้าน ชำระเงิน (เงินสด / โอนพร้อมเพย์) ตัดสต๊อก บันทึกรายรับ ออกใบเสร็จ และบันทึก log
    กติกา:
    - ลูกค้าต้องซื้อพวกเนื้อต่าง ๆ (ส่วนชั่งกิโล) ขั้นต่ำ 1 กิโลกรัมขึ้นไป (>= 1,000 กรัม)
    - ส่วนของเสริมอื่น ๆ ซื้อเท่าไหร่ก็ได้ (0 ชิ้นขึ้นไป แต่ไม่เกินสต๊อกที่มี)
    """
    method = checkout_service.normalize_payment_method(payment_method)

    if not isinstance(weigh_grams, int) or isinstance(weigh_grams, bool):
        raise ValueError("กรุณากรอกน้ำหนักเนื้อชั่งกิโล")
    if weigh_grams < MIN_TAKEAWAY_WEIGH_GRAMS:
        raise ValueError("สั่งกลับบ้านต้องซื้อรายการเนื้อชั่งกิโลขั้นต่ำ 1 กิโลกรัม (1,000 กรัม) ขึ้นไป")
    if weigh_grams > MAX_TAKEAWAY_WEIGH_GRAMS:
        raise ValueError("น้ำหนักชั่งกิโลเกินกำหนด (สูงสุดไม่เกิน 50 กิโลกรัม)")

    merged_qty: dict[int, int] = {}
    for raw in items or []:
        mid = raw.get("menu_item_id")
        qty = raw.get("quantity")
        if mid is None or qty is None:
            continue
        if not isinstance(qty, int) or isinstance(qty, bool) or not (1 <= qty <= MAX_QTY_PER_LINE):
            raise ValueError(f"จำนวนสินค้าต้องเป็นจำนวนเต็ม 1–{MAX_QTY_PER_LINE}")
        merged_qty[int(mid)] = merged_qty.get(int(mid), 0) + qty

    with db.transaction() as conn:
        takeaway_table = ensure_takeaway_table(conn=conn)
        rate = weigh_service.get_price_per_kg(conn=conn)
        default_weighed = weigh_service.get_default_weighed_item(conn=conn)
        if default_weighed.get("is_sold_out"):
            raise ValueError(f"{default_weighed['name']} หมดแล้ว")

        # ตรวจสอบเมนูและสต๊อกของเสริมก่อนบันทึก
        requested_by_stock: dict[int, tuple[str, int]] = {}
        verified_items: list[tuple[dict, int]] = []
        for mid, qty in merged_qty.items():
            m = db.query_one("SELECT * FROM menu_items WHERE id = ?", (mid,), conn=conn)
            if m is None or not m["active"]:
                raise ValueError("ไม่พบเมนูที่เลือก")
            if m["item_type"] != config.MENU_TYPE_NORMAL:
                raise ValueError(f"{m['name']} เป็นเมนูชั่งกิโล กรุณาใส่ในส่วนชั่งกิโล")
            if m["is_sold_out"]:
                raise ValueError(f"{m['name']} สินค้าหมดแล้ว")
            if m["stock_item_id"] is not None:
                st = db.query_one("SELECT * FROM stock_items WHERE id = ?", (m["stock_item_id"],), conn=conn)
                if st is None or not st["active"] or st["quantity"] <= 0:
                    raise ValueError(f"{m['name']} สินค้าหมดแล้ว")
                prev_name, prev_qty = requested_by_stock.get(st["id"], (m["name"], 0))
                total_req = prev_qty + qty
                if st["quantity"] < total_req:
                    raise ValueError(
                        f"{m['name']} เหลือไม่พอ (คงเหลือ {st['quantity']:g} {st['unit']} แต่ต้องการสั่ง {total_req} {st['unit']})"
                    )
                requested_by_stock[st["id"]] = (prev_name, total_req)
            verified_items.append((dict(m), qty))

        # คำนวณราคาและโปรโมชั่นภายใน transaction
        weigh_amount = weigh_service.calc_amount(weigh_grams, rate)
        order_total = 0.0
        for m, qty in verified_items:
            line_amt = float(
                (Decimal(str(m["price"])) * Decimal(qty)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            order_total = round(order_total + line_amt, 2)

        subtotal = round(weigh_amount + order_total, 2)
        promo = None
        discount = 0.0
        if promo_id is not None:
            promo = promo_service.check_applicable(promo_id, subtotal, conn=conn)
            discount = promo_service.calc_discount(promo, subtotal)

        rates = pricing_service.get_rates()
        totals = pricing_service.compute_totals(
            subtotal,
            discount,
            rates["service_charge_percent"],
            rates["vat_percent"],
        )
        pay_info = checkout_service.validate_payment(
            totals["total"],
            method,
            amount_received=amount_received,
        )

        now = db.now_str()
        # 1) สร้าง session สำหรับบิลสั่งกลับบ้าน (สถานะ closed ทันทีเมื่อชำระเงินสำเร็จ)
        session_id = db.execute(
            "INSERT INTO table_sessions (table_id, status, started_at, confirmed_at, confirmed_by, "
            "closed_at, last_activity, device_id, device_info) "
            "VALUES (?, 'closed', ?, ?, ?, ?, ?, 'takeaway', 'สั่งกลับบ้าน')",
            (takeaway_table["id"], now, now, user_id, now, now),
            conn=conn,
        )

        # 2) บันทึกรายการชั่งกิโล (รวมเป็นหัวข้อเดียวกัน)
        weigh_name = weigh_service.DEFAULT_WEIGH_NAME
        wid = db.execute(
            "INSERT INTO weigh_entries (session_id, menu_item_id, name_snapshot, weight_grams, "
            "price_per_kg, amount, status, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (session_id, default_weighed["id"], weigh_name, weigh_grams, rate, weigh_amount, user_id, now),
            conn=conn,
        )
        stock_service.deduct_for_menu_item(
            default_weighed["id"],
            weigh_grams / config.GRAMS_PER_KG,
            "ขายสั่งกลับบ้าน (ชั่งกิโล)",
            user_id=user_id,
            ref_type="weigh_entry",
            ref_id=wid,
            strict=False,
            conn=conn,
        )
        log_service.log_action(
            "weigh_add",
            f"สั่งกลับบ้าน ชั่ง {weigh_name} {weigh_grams} กรัม ({rate:g} บาท/กก.) = {weigh_amount:g} บาท",
            user_id=user_id,
            ref_type="weigh_entry",
            ref_id=wid,
            conn=conn,
        )

        # 3) บันทึกออเดอร์รายการของเสริม (ถ้ามี)
        order_desc_parts = []
        if verified_items:
            clean_note = (note or "").strip() or "สั่งกลับบ้าน"
            oid = db.execute(
                "INSERT INTO orders (session_id, status, note, created_by, created_at) "
                "VALUES (?, 'served', ?, ?, ?)",
                (session_id, clean_note, user_id, now),
                conn=conn,
            )
            for m, qty in verified_items:
                iid = db.execute(
                    "INSERT INTO order_items (order_id, menu_item_id, name_snapshot, unit_price, quantity, status) "
                    "VALUES (?, ?, ?, ?, ?, 'served')",
                    (oid, m["id"], m["name"], m["price"], qty),
                    conn=conn,
                )
                stock_service.deduct_for_menu_item(
                    m["id"],
                    qty,
                    "ขายสั่งกลับบ้าน",
                    user_id=user_id,
                    ref_type="order_item",
                    ref_id=iid,
                    strict=True,
                    conn=conn,
                )
                order_desc_parts.append(f"{m['name']} x{qty}")
            log_service.log_action(
                "order_create",
                "สั่งกลับบ้าน สั่งของเสริม: " + ", ".join(order_desc_parts),
                user_id=user_id,
                ref_type="order",
                ref_id=oid,
                conn=conn,
            )

        # 4) บันทึกบิลเข้ารายรับ
        bill_id = db.execute(
            "INSERT INTO bills (session_id, subtotal, promo_id, discount, service_charge, vat, total, "
            "payment_method, amount_received, change_amount, cashier_id, created_at, paid_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                totals["subtotal"],
                promo["id"] if promo else None,
                totals["discount"],
                totals["service_charge"],
                totals["vat"],
                pay_info["total"],
                method,
                pay_info["amount_received"],
                pay_info["change_amount"],
                user_id,
                now,
                now,
            ),
            conn=conn,
        )

        if method == "cash":
            pay_detail_txt = f"รับเงิน {pay_info['amount_received']:,.2f} บาท เงินทอน {pay_info['change_amount']:,.2f} บาท"
        else:
            pay_detail_txt = f"รับโอน {pay_info['amount_received']:,.2f} บาท"

        log_detail = (
            f"สั่งกลับบ้าน (บิล #{bill_id}) ชำระ {pay_info['total']:,.2f} บาท ({checkout_service.PAYMENT_METHODS_TH[method]}) "
            f"{pay_detail_txt} [ชั่งกิโล {weigh_grams} กรัม"
            + (f", ของเสริม: {', '.join(order_desc_parts)}" if order_desc_parts else "")
            + "]"
            + (f" โปร: {promo['name']} -{totals['discount']:,.2f}" if promo else "")
        )
        log_service.log_action(
            "takeaway_checkout",
            log_detail,
            user_id=user_id,
            ref_type="bill",
            ref_id=bill_id,
            conn=conn,
        )

    bill_detail = checkout_service.get_bill_detail(session_id)
    receipt_info = checkout_service._extract_receipt_lines_and_totals(bill_detail)
    receipt_text = checkout_service.build_receipt_text(bill_detail)
    return {
        "session_id": session_id,
        "bill": bill_detail,
        "receipt_info": receipt_info,
        "receipt_text": receipt_text,
    }
