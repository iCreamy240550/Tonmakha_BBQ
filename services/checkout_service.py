"""services/checkout_service.py — เช็คเอาท์: เรียกเช็คบิล -> ดูบิล/เลือกโปร -> ตรวจสอบยอดรับเงิน/ชำระเงิน -> ปิดโต๊ะ -> ออกใบเสร็จ PDF/TXT

ลำดับ:  start_checkout (open -> awaiting_payment)  ->  preview (เลือกโปรได้กี่ครั้งก็ได้)  ->  pay (บันทึกบิล + closed)
- 1 รอบมีได้ 1 บิล (bills.session_id UNIQUE) ; บิลที่บันทึกแล้วแก้ไม่ได้
- ช่องทางการชำระเงินใหม่รองรับเฉพาะ 'cash' (เงินสด) และ 'transfer' (โอน/PromptPay) เท่านั้น (ไม่อนุญาตให้สร้างรายการชำระแบบบัตรใหม่ แต่ยังแสดงประวัติบิลเก่าได้)
- pay คำนวณยอดจากฐานข้อมูลจริงภายใน transaction เดียวกับการปิดโต๊ะ (ไม่เชื่อยอดที่ส่งมาจาก UI)
- ตรวจสอบจำนวนเงินที่รับด้วย Decimal ป้องกัน floating-point error
- รองรับการส่งออกใบเสร็จทั้ง .pdf (รองรับภาษาไทยและฟอนต์ Prompt ครบถ้วน) และ .txt ตามรูปแบบมาตรฐานใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import secrets

import config
from database import db
from services import (
    auth_service,
    log_service,
    order_service,
    pricing_service,
    settings_service,
    table_service,
    weigh_service,
)

_UNSET = object()

# ช่องทางที่อนุญาตให้สร้างรายการชำระเงินใหม่ (เหลือเพียง 2 รูปแบบตามข้อกำหนด)
PAYMENT_METHODS_TH = {
    "cash": "เงินสด",
    "transfer": "โอน/PromptPay",
}
# รองรับการแสดงผลข้อมูลประวัติการชำระเงินเก่าที่อาจมีช่องทางบัตรอยู่แล้ว
HISTORICAL_PAYMENT_METHODS_TH = {
    **PAYMENT_METHODS_TH,
    "card": "บัตร",
}
_METHOD_ALIASES = {
    "cash": "cash",
    "เงินสด": "cash",
    "transfer": "transfer",
    "promptpay": "transfer",
    "โอน/promptpay": "transfer",
    "โอน/พร้อมเพย์": "transfer",
    "สแกน promptpay": "transfer",
}


def normalize_payment_method(payment_method: str) -> str:
    """แปลงชื่อวิธีชำระให้เป็นคีย์มาตรฐาน ('cash' | 'transfer') ;
    ไม่อนุญาตให้ส่งช่องทางบัตร ('card') หรือช่องทางอื่นเข้ามาสร้างรายการใหม่ -> ValueError ไทย"""
    key = (payment_method or "").strip().lower()
    if key == "card" or key == "บัตร":
        raise ValueError("ระบบยกเลิกการรับชำระเงินด้วยบัตรแล้ว (รองรับเฉพาะ เงินสด และ โอน/PromptPay)")
    if key not in _METHOD_ALIASES:
        raise ValueError("ช่องทางชำระเงินไม่ถูกต้อง (รองรับเฉพาะ เงินสด และ โอน/PromptPay)")
    return _METHOD_ALIASES[key]


def _q(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_money_decimal(value, label: str = "จำนวนเงินที่รับ") -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"กรุณากรอก{label}")
    text = str(value).strip().replace(",", "")
    if not text:
        raise ValueError(f"กรุณากรอก{label}")
    try:
        dec = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label}ต้องเป็นตัวเลขที่ถูกต้อง") from None
    if not dec.is_finite():
        raise ValueError(f"{label}ไม่ถูกต้อง")
    if dec < Decimal("0"):
        raise ValueError(f"{label}ต้องไม่ติดลบ")
    return _q(dec)


def validate_payment(total: float | Decimal, payment_method: str, amount_received=_UNSET) -> dict:
    """ตรวจสอบความถูกต้องของการรับชำระเงินด้วย Decimal:
    - เงินสด (cash): ต้องเป็นตัวเลข >= 0 และ >= ยอดที่ต้องชำระ ; เงินทอน = เงินรับ - ยอดที่ต้องชำระ (ไม่ติดลบ)
    - โอน/PromptPay (transfer): ไม่คำนวณเงินทอน (change_amount = 0.00 เสมอ)
    คืน dict: {'payment_method', 'payment_method_th', 'total', 'amount_received', 'change_amount'}"""
    method = normalize_payment_method(payment_method)
    total_dec = _q(Decimal(str(total)))
    if total_dec <= Decimal("0"):
        raise ValueError("ยอดที่ต้องชำระต้องมากกว่า 0")

    if method == "cash":
        if amount_received is _UNSET:
            received_dec = total_dec
        else:
            received_dec = _parse_money_decimal(amount_received, "จำนวนเงินสดที่รับ")
        if received_dec < total_dec:
            raise ValueError(
                f"จำนวนเงินสดที่รับ ({received_dec:,.2f} บาท) น้อยกว่ายอดที่ต้องชำระ ({total_dec:,.2f} บาท)"
            )
        change_dec = _q(received_dec - total_dec)
    else:
        if amount_received is _UNSET or amount_received is None or str(amount_received).strip() == "":
            received_dec = total_dec
        else:
            received_dec = _parse_money_decimal(amount_received, "จำนวนเงินที่รับ")
            if received_dec < total_dec:
                raise ValueError(
                    f"จำนวนเงินที่รับ ({received_dec:,.2f} บาท) น้อยกว่ายอดที่ต้องชำระ ({total_dec:,.2f} บาท)"
                )
            # การชำระด้วยการโอน/PromptPay ไม่มีการคิดเงินทอน ยึดยอดรับจริงตามยอดสุทธิ
            received_dec = total_dec
        change_dec = Decimal("0.00")

    return {
        "payment_method": method,
        "payment_method_th": PAYMENT_METHODS_TH[method],
        "total": float(total_dec),
        "amount_received": float(received_dec),
        "change_amount": float(change_dec),
    }


def _session_or_error(session_id: int, conn=None) -> dict:
    s = db.query_one("SELECT s.*, t.table_no, t.name AS table_name FROM table_sessions s "
                     "JOIN tables t ON t.id = s.table_id WHERE s.id = ?", (session_id,), conn=conn)
    if s is None:
        raise ValueError("ไม่พบรอบของโต๊ะนี้")
    return dict(s)


def _unserved_count(session_id: int, conn=None) -> int:
    return db.query_one("SELECT COUNT(*) AS c FROM orders WHERE session_id = ? AND status IN ('new','preparing')",
                        (session_id,), conn=conn)["c"]


# ---------------------------------------------------------------- เริ่มเช็คเอาท์ / ดูบิล

def start_checkout(session_id: int, user_id: int | None = None) -> dict:
    """พนักงานกดเช็คบิล: open -> awaiting_payment แล้วคืนตัวอย่างบิล (เหมือน preview ไม่ใช้โปร)
    ValueError ถ้ารอบไม่ใช่ open / ไม่มีรายการเลย (ให้ยกเลิกโต๊ะแทน)"""
    s = _session_or_error(session_id)
    if s["status"] != config.SESSION_OPEN:
        raise ValueError(f"เช็คบิลไม่ได้ — สถานะปัจจุบันคือ "
                         f"{config.SESSION_STATUS_TH.get(s['status'], s['status'])}")
    if pricing_service.calc_bill(session_id)["subtotal"] <= 0:
        raise ValueError("โต๊ะนี้ยังไม่มีรายการ เช็คบิลไม่ได้ — ถ้าลูกค้าไม่ได้ใช้บริการให้ยกเลิกโต๊ะแทน")
    table_service.mark_awaiting_payment(session_id, user_id=user_id)
    return preview(session_id)


def preview(session_id: int, promo_id: int | None = None) -> dict:
    """ดูบิลก่อนชำระ (อ่านอย่างเดียว) ใช้ได้กับรอบ open / awaiting_payment
    รอบที่ชำระแล้ว (closed) -> คืนบิลที่บันทึกไว้ (get_bill_detail) ; ValueError ถ้ารอบถูกยกเลิก/ไม่พบ"""
    s = _session_or_error(session_id)
    if s["status"] == config.SESSION_CLOSED:
        detail = get_bill_detail(session_id)
        if detail is None:
            raise ValueError("ไม่พบบิลของรอบนี้")
        return detail
    if s["status"] not in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT):
        raise ValueError("รอบนี้ไม่มีบิล (ยังไม่เริ่มใช้งานหรือถูกยกเลิก)")
    bill = pricing_service.calc_bill(session_id, promo_id=promo_id)
    bill.update(table_no=s["table_no"], table_name=s["table_name"], status=s["status"],
                status_th=config.SESSION_STATUS_TH[s["status"]],
                weigh_entries=weigh_service.list_entries(session_id),
                orders=order_service.list_orders(session_id),
                unserved_orders=_unserved_count(session_id))
    return bill


# ---------------------------------------------------------------- ชำระเงิน

def pay(session_id: int, payment_method: str, user_id: int, promo_id: int | None = None,
        force: bool = False, amount_received=_UNSET) -> dict:
    """บันทึกบิล + ปิดโต๊ะ (awaiting_payment -> closed) ใน transaction เดียว -> dict บิล (get_bill_detail)
    payment_method: 'cash' | 'transfer' | 'promptpay' (ไม่อนุญาต 'card')
    amount_received: จำนวนเงินที่รับจริง (กรณีเงินสดต้อง >= ยอดสุทธิ)
    force: ยืนยันปิดบิลทั้งที่ยังมีออเดอร์ new/preparing ค้าง (จะตั้งเป็น served ให้)
    ValueError ถ้าข้อมูลผิดพลาด (เมื่อไม่ผ่านจะไม่บันทึกบิลและไม่เปลี่ยนสถานะโต๊ะ)"""
    method = normalize_payment_method(payment_method)
    with db.transaction() as conn:
        s = _session_or_error(session_id, conn)
        if s["status"] == config.SESSION_CLOSED or db.query_one("SELECT 1 FROM bills WHERE session_id = ?", (session_id,), conn=conn):
            raise ValueError("โต๊ะนี้ชำระเงินไปแล้ว")
        if s["status"] != config.SESSION_AWAITING_PAYMENT:
            raise ValueError(f"ชำระเงินไม่ได้ — สถานะปัจจุบันคือ "
                             f"{config.SESSION_STATUS_TH.get(s['status'], s['status'])} (ต้องกดเช็คบิลก่อน)")
        bill = pricing_service.calc_bill(session_id, promo_id=promo_id, conn=conn)
        if bill["subtotal"] <= 0:
            raise ValueError("ยอดรวมเป็น 0 บันทึกบิลไม่ได้")
        # ตรวจสอบยอดรับเงินเทียบกับยอดสุทธิที่คำนวณใหม่จากฐานข้อมูลจริง
        pay_info = validate_payment(bill["total"], method, amount_received=amount_received)

        unserved = _unserved_count(session_id, conn)
        if unserved and not force:
            raise ValueError(f"ยังมีออเดอร์ที่ยังไม่เสิร์ฟ {unserved} รายการ — ยืนยันเพื่อปิดบิลต่อ")
        if unserved:
            db.execute("UPDATE order_items SET status='served' WHERE status='active' AND order_id IN "
                       "(SELECT id FROM orders WHERE session_id = ? AND status IN ('new','preparing'))",
                       (session_id,), conn=conn)
            db.execute("UPDATE orders SET status='served' WHERE session_id = ? AND status IN ('new','preparing')",
                       (session_id,), conn=conn)
        now = db.now_str()
        bill_id = db.execute(
            "INSERT INTO bills (session_id, subtotal, promo_id, discount, service_charge, vat, total, "
            "payment_method, amount_received, change_amount, cashier_id, created_at, paid_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, bill["subtotal"], bill["promo_id"], bill["discount"], bill["service_charge"],
             bill["vat"], pay_info["total"], method, pay_info["amount_received"], pay_info["change_amount"],
             user_id, now, now),
            conn=conn,
        )
        table_service.close_session(session_id, user_id=user_id, conn=conn)
        if method == "cash":
            pay_detail_txt = f"รับเงิน {pay_info['amount_received']:,.2f} บาท เงินทอน {pay_info['change_amount']:,.2f} บาท"
        else:
            pay_detail_txt = f"รับโอน {pay_info['amount_received']:,.2f} บาท"
        detail = (
            f"โต๊ะ {s['table_no']} ชำระ {pay_info['total']:,.2f} บาท ({PAYMENT_METHODS_TH[method]}) "
            f"{pay_detail_txt}"
            + (f" โปร: {bill['promo_name']} -{bill['discount']:,.2f}" if bill["promo_id"] else "")
            + (f" [ปิดบิลทั้งที่มีออเดอร์ค้าง {unserved} รายการ]" if unserved else "")
        )
        log_service.log_action("checkout_paid", detail, user_id=user_id, ref_type="bill", ref_id=bill_id, conn=conn)
    return get_bill_detail(session_id)


# ---------------------------------------------------------------- อ่านบิลที่บันทึกแล้ว

def _bill_row(row) -> dict:
    d = dict(row)
    d["payment_method_th"] = HISTORICAL_PAYMENT_METHODS_TH.get(d["payment_method"], d["payment_method"])
    if not d.get("amount_received") and d.get("total"):
        d["amount_received"] = d["total"]
    if d.get("change_amount") is None:
        d["change_amount"] = 0.0
    return d


def get_bill(session_id: int) -> dict | None:
    """บิลของรอบ (เฉพาะที่ชำระแล้ว) -> dict (+ payment_method_th, table_no, table_name, promo_name, cashier_name) หรือ None"""
    r = db.query_one(
        "SELECT b.*, t.table_no, t.name AS table_name, p.name AS promo_name, "
        "COALESCE(u.display_name, u.username) AS cashier_name, u.username AS cashier_username "
        "FROM bills b JOIN table_sessions s ON s.id = b.session_id JOIN tables t ON t.id = s.table_id "
        "LEFT JOIN promotions p ON p.id = b.promo_id LEFT JOIN users u ON u.id = b.cashier_id "
        "WHERE b.session_id = ?", (session_id,))
    return _bill_row(r) if r else None


def get_bill_by_id(bill_id: int) -> dict | None:
    """บิลตาม id (เหมือน get_bill)"""
    r = db.query_one("SELECT session_id FROM bills WHERE id = ?", (bill_id,))
    return get_bill(r["session_id"]) if r else None


def get_bill_detail(session_id: int) -> dict | None:
    """บิลที่บันทึกแล้ว + รายละเอียดรายการ (ใช้พิมพ์ใบเสร็จ/หน้าบิลลูกค้า)"""
    b = get_bill(session_id)
    if b is None:
        return None
    b["weigh_entries"] = weigh_service.list_entries(session_id)
    b["orders"] = order_service.list_orders(session_id)
    b["after_discount"] = round(b["subtotal"] - b["discount"], 2)
    return b


def list_bills(date_from: str | None = None, date_to: str | None = None, limit: int = 100,
               offset: int = 0) -> list[dict]:
    """รายการบิลที่ชำระแล้ว ใหม่สุดก่อน ; date_from/date_to = 'YYYY-MM-DD' (ตามเวลาชำระ)"""
    clauses, params = [], []
    if date_from:
        clauses.append("b.paid_at >= ?")
        params.append(f"{date_from} 00:00:00")
    if date_to:
        clauses.append("b.paid_at <= ?")
        params.append(f"{date_to} 23:59:59")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db.query_all(
        "SELECT b.*, t.table_no, t.name AS table_name, p.name AS promo_name, "
        "COALESCE(u.display_name, u.username) AS cashier_name, u.username AS cashier_username "
        "FROM bills b JOIN table_sessions s ON s.id = b.session_id JOIN tables t ON t.id = s.table_id "
        "LEFT JOIN promotions p ON p.id = b.promo_id LEFT JOIN users u ON u.id = b.cashier_id" + where +
        " ORDER BY b.id DESC LIMIT ? OFFSET ?", tuple(params) + (limit, offset))
    return [_bill_row(r) for r in rows]


# ---------------------------------------------------------------- ใบเสร็จ (.txt และ .pdf)

def _fmt_money(v) -> str:
    return f"{float(v or 0):,.2f}"


def _split_date_time(text: str | None) -> tuple[str, str]:
    """แยกวันเวลาที่บันทึกในบิล ('YYYY-MM-DD HH:MM:SS') ออกเป็น ('DD/MM/YYYY', 'HH:MM:SS')
    โดยใช้วันเวลาที่บันทึกไว้กับบิลจริง หากไม่มีจึงใช้เวลาปัจจุบันของระบบ"""
    raw = (text or "").strip() or db.now_str()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M:%S")
        except ValueError:
            continue
    return raw[:10], raw[11:19] if len(raw) >= 19 else "-"


def _fmt_weight(grams) -> str:
    g = float(grams or 0)
    kheed = g / (config.GRAMS_PER_KG / config.KHEED_PER_KG)
    kheed_txt = f"{kheed:g}"
    if g >= config.GRAMS_PER_KG:
        return f"{g / config.GRAMS_PER_KG:g} กก. ({kheed_txt} ขีด)"
    return f"{kheed_txt} ขีด"


def _resolve_bill_dict(bill_or_session_id) -> dict:
    if isinstance(bill_or_session_id, dict):
        return bill_or_session_id
    if isinstance(bill_or_session_id, int):
        b = get_bill_detail(bill_or_session_id)
        if b is None:
            by_id = get_bill_by_id(bill_or_session_id)
            if by_id is not None:
                b = get_bill_detail(by_id["session_id"])
        if b is not None:
            return b
    raise ValueError("ไม่พบบิลสำหรับออกใบเสร็จ")


def _resolve_cashier_name(bill: dict) -> str:
    """ดึงชื่อพนักงานขายจากข้อมูลผู้ดำเนินการออกบิลจริง (display_name หรือ username จากบัญชีที่ล็อกอิน)"""
    name = (bill.get("cashier_name") or "").strip()
    if name:
        return name
    cid = bill.get("cashier_id")
    if cid:
        u = auth_service.get_user(int(cid))
        if u:
            return (u.get("display_name") or u.get("username") or "").strip() or "-"
    return "-"


def _extract_receipt_lines_and_totals(bill: dict) -> dict:
    """รวบรวมรายการสินค้า จำนวนรายการ และยอดเงินทั้งหมดจากข้อมูลบิลจริง"""
    lines = []
    total_qty_count = 0

    for e in bill.get("weigh_entries", []):
        w_txt = _fmt_weight(e["weight_grams"])
        rate = float(e.get("price_per_kg", config.DEFAULT_WEIGH_PRICE_PER_KG))
        amt = float(e.get("amount") or 0)
        lines.append({
            "qty_str": "1",
            "name": f"{e['name_snapshot']} ({w_txt} @{_fmt_money(rate)}/กก.)",
            "amount_str": _fmt_money(amt),
            "amount": amt,
        })
        total_qty_count += 1

    for o in bill.get("orders", []):
        for it in o.get("items", []):
            qty = int(it.get("quantity") or 1)
            line_amt = float(it.get("line_total", round(float(it["unit_price"]) * qty, 2)))
            lines.append({
                "qty_str": str(qty),
                "name": str(it["name_snapshot"]),
                "amount_str": _fmt_money(line_amt),
                "amount": line_amt,
            })
            total_qty_count += qty

    subtotal = float(bill.get("subtotal") or 0)
    discount = float(bill.get("discount") or 0)
    after_discount = float(bill.get("after_discount") if bill.get("after_discount") is not None else round(subtotal - discount, 2))
    service_charge = float(bill.get("service_charge") or 0)
    vat = float(bill.get("vat") or 0)
    total = float(bill.get("total") or 0)
    pre_vat = round(after_discount + service_charge, 2)

    method = bill.get("payment_method") or "cash"
    method_th = HISTORICAL_PAYMENT_METHODS_TH.get(method, bill.get("payment_method_th") or method)
    received = float(bill.get("amount_received") if bill.get("amount_received") is not None else total)
    change = float(bill.get("change_amount") or 0)

    date_str, time_str = _split_date_time(bill.get("paid_at") or bill.get("created_at"))
    cashier = _resolve_cashier_name(bill)
    shop = settings_service.get_shop_info()

    raw_tno = bill.get("table_no")
    is_takeaway = (raw_tno == 0 or bill.get("table_name") == "สั่งกลับบ้าน")
    table_label = "สั่งกลับบ้าน" if is_takeaway else f"โต๊ะ {raw_tno if raw_tno is not None else '-'}"

    return {
        "shop": shop,
        "bill_no": bill.get("id") or f"S{bill.get('session_id', '-')}",
        "table_no": "สั่งกลับบ้าน" if is_takeaway else (raw_tno if raw_tno is not None else "-"),
        "table_name": bill.get("table_name") or table_label,
        "table_label": table_label,
        "is_takeaway": is_takeaway,
        "cashier": cashier,
        "date_str": date_str,
        "time_str": time_str,
        "lines": lines,
        "total_qty_count": total_qty_count,
        "subtotal": subtotal,
        "discount": discount,
        "promo_name": bill.get("promo_name"),
        "after_discount": after_discount,
        "service_charge": service_charge,
        "service_charge_percent": bill.get("service_charge_percent"),
        "pre_vat": pre_vat,
        "vat": vat,
        "vat_percent": bill.get("vat_percent") or 7,
        "total": total,
        "method": method,
        "method_th": method_th,
        "received": received,
        "change": change,
    }


def build_receipt_text(bill_or_session_id) -> str:
    """สร้างข้อความใบเสร็จ (.txt) จัดย่อหน้าและลำดับข้อมูลตามรูปแบบใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน"""
    bill = _resolve_bill_dict(bill_or_session_id)
    info = _extract_receipt_lines_and_totals(bill)
    shop = info["shop"]
    width = 50
    sep = "-" * width

    def _center(text: str) -> str:
        text = text.strip()
        if len(text) >= width:
            return text
        pad = (width - len(text)) // 2
        return (" " * pad) + text

    def _lr(left: str, right: str) -> str:
        space = max(1, width - len(left) - len(right))
        return f"{left}{' ' * space}{right}"

    out = [
        _center(shop["shop_name"]),
    ]
    if shop["shop_tax_id_enabled"] and shop["shop_tax_id"]:
        out.append(_center(f"เลขผู้เสียภาษี {shop['shop_tax_id']}"))
    out.append(_center("ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน"))
    if shop["address_line1"]:
        out.append(_center(shop["address_line1"]))
    if shop["address_line2"]:
        out.append(_center(shop["address_line2"]))
    if shop["phone_line"]:
        out.append(_center(shop["phone_line"]))

    out.extend([
        sep,
        f"พนักงานขาย   {info['cashier']}",
        f"วันที่         {info['date_str']}",
        f"เวลา          {info['time_str']}",
        f"โต๊ะ          {info['table_label']} (บิล #{info['bill_no']})",
        sep,
        f"{'จำนวน'.ljust(7)}{'รายการ'.ljust(29)}{'จำนวนเงิน'.rjust(14)}",
        sep,
    ])

    for ln in info["lines"]:
        q_col = ln["qty_str"].center(5).ljust(7)
        amt_col = ln["amount_str"].rjust(14)
        name_txt = ln["name"]
        if len(name_txt) <= 28:
            out.append(f"{q_col}{name_txt.ljust(29)}{amt_col}")
        else:
            out.append(f"{q_col}{name_txt[:28].ljust(29)}{amt_col}")
            rem = name_txt[28:]
            while rem:
                out.append(f"{'':7}{rem[:28]}")
                rem = rem[28:]

    out.append(sep)
    out.append(f"จำนวนรวม   {info['total_qty_count']}")

    promo_suffix = f" ({info['promo_name']})" if info.get("promo_name") else ""
    fin_rows = [
        ("รวมเป็นเงิน", _fmt_money(info["subtotal"])),
        ("รวมเป็นเงินก่อนคิดภาษีและส่วนลด", _fmt_money(info["subtotal"])),
        (f"ส่วนลด{promo_suffix}", _fmt_money(info["discount"])),
        ("จำนวนเงินหลังหักส่วนลด", _fmt_money(info["after_discount"])),
    ]
    if info["service_charge"] > 0:
        pct = info.get("service_charge_percent")
        sc_lbl = f"ค่าบริการ ({pct:g}%)" if pct else "ค่าบริการ"
        fin_rows.append((sc_lbl, _fmt_money(info["service_charge"])))
    fin_rows.extend([
        ("ราคาไม่รวมภาษีมูลค่าเพิ่ม", _fmt_money(info["pre_vat"])),
        ("ภาษีมูลค่าเพิ่ม 7%", _fmt_money(info["vat"])),
        ("รวมทั้งสิ้น", f"{_fmt_money(info['total'])} บาท"),
    ])

    for lbl, val in fin_rows:
        out.append(_lr(f"      {lbl}", val))

    out.append(sep)
    out.append(f"ช่องทางการชำระ :   {info['method_th']}")
    if info["method"] == "cash":
        out.append(_lr("รับเงินมา", f"{_fmt_money(info['received'])} บาท"))
        out.append(_lr("เงินทอน", f"{_fmt_money(info['change'])} บาท"))

    out.extend([
        sep,
        _center(shop["shop_name"]),
        _center("ขอบคุณที่ใช้บริการ"),
    ])
    return "\n".join(out) + "\n"


def _safe_receipt_path(bill: dict, ext: str, out_dir: Path | str | None = None,
                       filename: str | None = None) -> Path:
    target_dir = Path(out_dir) if out_dir else Path(config.EXPORTS_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = ext if ext.startswith(".") else f".{ext}"
    if filename:
        safe_name = Path(filename).name
        if not safe_name.lower().endswith(ext.lower()):
            safe_name += ext
        candidate = target_dir / safe_name
    else:
        bill_no = bill.get("id") or f"s{bill.get('session_id', 0)}"
        raw_tno = bill.get("table_no")
        table_tag = "takeaway" if (raw_tno == 0 or bill.get("table_name") == "สั่งกลับบ้าน") else f"table{raw_tno or 0}"
        stamp = db.now_str().replace(":", "").replace("-", "").replace(" ", "_")
        candidate = target_dir / f"receipt_bill{bill_no}_{table_tag}_{stamp}{ext}"

    if candidate.exists():
        stem = candidate.stem
        candidate = target_dir / f"{stem}_{secrets.token_hex(3)}{ext}"
    return candidate


def export_receipt_txt(bill_or_session_id, out_dir: Path | str | None = None,
                       filename: str | None = None) -> Path:
    """บันทึกใบเสร็จเป็นไฟล์ .txt ลงโฟลเดอร์ exports/ -> Path"""
    bill = _resolve_bill_dict(bill_or_session_id)
    text = build_receipt_text(bill)
    path = _safe_receipt_path(bill, ".txt", out_dir=out_dir, filename=filename)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise ValueError(f"บันทึกไฟล์ใบเสร็จ TXT ไม่สำเร็จ: {e}") from None
    return path


def _find_thai_fonts() -> tuple[Path, Path]:
    """ค้นหาฟอนต์ Prompt (ปกติ, หนา) จากโฟลเดอร์โปรเจกต์เท่านั้น (ไม่ใช้ NotoSansThai/Tahoma/Leelawadee)"""
    base_assets = config.BASE_DIR / "assets"
    candidates_reg = [
        config.FONTS_DIR / "Prompt-Regular.ttf",
        base_assets / "fonts" / "Prompt-Regular.ttf",
    ]
    candidates_bold = [
        config.FONTS_DIR / "Prompt-Bold.ttf",
        base_assets / "fonts" / "Prompt-Bold.ttf",
    ]
    reg = next((p for p in candidates_reg if p.exists() and p.is_file()), None)
    bold = next((p for p in candidates_bold if p.exists() and p.is_file()), None)
    if reg is None or bold is None:
        raise ValueError("ไม่พบไฟล์ฟอนต์ Prompt (Prompt-Regular.ttf / Prompt-Bold.ttf) สำหรับสร้าง PDF ในโฟลเดอร์ assets/fonts/")
    return reg, bold


def export_receipt_pdf(bill_or_session_id, out_dir: Path | str | None = None,
                       filename: str | None = None) -> Path:
    """สร้างและบันทึกใบเสร็จเป็นไฟล์ .pdf (ใช้ฟอนต์ Prompt และจัดย่อหน้าตามแบบใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน) -> Path"""
    bill = _resolve_bill_dict(bill_or_session_id)
    info = _extract_receipt_lines_and_totals(bill)
    shop = info["shop"]
    path = _safe_receipt_path(bill, ".pdf", out_dir=out_dir, filename=filename)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as e:
        raise ValueError(f"ยังไม่ได้ติดตั้งไลบรารีสำหรับสร้าง PDF (reportlab): {e}") from None

    try:
        reg_path, bold_path = _find_thai_fonts()
        font_reg = "Prompt"
        font_bold = "PromptBold"
        if font_reg not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_reg, str(reg_path)))
        if font_bold not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_bold, str(bold_path)))

        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=f"ใบเสร็จรับเงิน {info['table_label']}",
        )

        style_shop = ParagraphStyle("ShopTH", fontName=font_bold, fontSize=16, leading=22, alignment=1, textColor=colors.HexColor("#2b2118"))
        style_head = ParagraphStyle("HeadTH", fontName=font_reg, fontSize=11, leading=16, alignment=1, textColor=colors.HexColor("#2b2118"))
        style_sub = ParagraphStyle("SubTH", fontName=font_bold, fontSize=12, leading=18, alignment=1, textColor=colors.HexColor("#2b2118"))
        style_meta = ParagraphStyle("MetaTH", fontName=font_reg, fontSize=10.5, leading=15, textColor=colors.HexColor("#2b2118"))
        style_cell = ParagraphStyle("CellTH", fontName=font_reg, fontSize=10.5, leading=15, textColor=colors.HexColor("#2b2118"))
        style_cell_c = ParagraphStyle("CellCTH", fontName=font_reg, fontSize=10.5, leading=15, alignment=1, textColor=colors.HexColor("#2b2118"))
        style_cell_r = ParagraphStyle("CellRTH", fontName=font_reg, fontSize=10.5, leading=15, alignment=2, textColor=colors.HexColor("#2b2118"))
        style_cell_b = ParagraphStyle("CellBTH", fontName=font_bold, fontSize=10.5, leading=15, textColor=colors.HexColor("#2b2118"))
        style_cell_bc = ParagraphStyle("CellBCTH", fontName=font_bold, fontSize=10.5, leading=15, alignment=1, textColor=colors.HexColor("#2b2118"))
        style_cell_br = ParagraphStyle("CellBRTH", fontName=font_bold, fontSize=10.5, leading=15, alignment=2, textColor=colors.HexColor("#2b2118"))
        style_total_l = ParagraphStyle("TotLTH", fontName=font_bold, fontSize=12.5, leading=18, alignment=2, textColor=colors.HexColor("#e8590c"))
        style_total_r = ParagraphStyle("TotRTH", fontName=font_bold, fontSize=12.5, leading=18, alignment=2, textColor=colors.HexColor("#e8590c"))
        style_foot_b = ParagraphStyle("FootBTH", fontName=font_bold, fontSize=11.5, leading=17, alignment=1, textColor=colors.HexColor("#2b2118"))
        style_foot = ParagraphStyle("FootTH", fontName=font_reg, fontSize=10.5, leading=15, alignment=1, textColor=colors.HexColor("#2b2118"))

        story = [
            Paragraph(shop["shop_name"], style_shop),
        ]
        if shop["shop_tax_id_enabled"] and shop["shop_tax_id"]:
            story.append(Paragraph(f"เลขผู้เสียภาษี {shop['shop_tax_id']}", style_head))
        story.append(Paragraph("ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน", style_sub))
        if shop["address_line1"]:
            story.append(Paragraph(shop["address_line1"], style_head))
        if shop["address_line2"]:
            story.append(Paragraph(shop["address_line2"], style_head))
        if shop["phone_line"]:
            story.append(Paragraph(shop["phone_line"], style_head))

        story.extend([
            Spacer(1, 3 * mm),
            HRFlowable(width="100%", thickness=0.9, color=colors.HexColor("#2b2118")),
            Spacer(1, 2 * mm),
        ])

        meta_rows = [
            [Paragraph("<b>พนักงานขาย</b>", style_meta), Paragraph(str(info["cashier"]), style_meta)],
            [Paragraph("<b>วันที่</b>", style_meta), Paragraph(str(info["date_str"]), style_meta)],
            [Paragraph("<b>เวลา</b>", style_meta), Paragraph(str(info["time_str"]), style_meta)],
            [Paragraph("<b>โต๊ะ</b>", style_meta), Paragraph(f"{info['table_label']} (บิล #{info['bill_no']})", style_meta)],
        ]
        meta_table = Table(meta_rows, colWidths=[35 * mm, 135 * mm])
        meta_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 2 * mm))

        # ตารางรายการสินค้า: จำนวน | รายการ | จำนวนเงิน
        item_rows = [[
            Paragraph("จำนวน", style_cell_bc),
            Paragraph("รายการ", style_cell_b),
            Paragraph("จำนวนเงิน", style_cell_br),
        ]]
        for ln in info["lines"]:
            item_rows.append([
                Paragraph(ln["qty_str"], style_cell_c),
                Paragraph(ln["name"], style_cell),
                Paragraph(ln["amount_str"], style_cell_r),
            ])

        items_table = Table(item_rows, colWidths=[24 * mm, 108 * mm, 38 * mm], repeatRows=1)
        items_table.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 0.9, colors.HexColor("#2b2118")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.HexColor("#2b2118")),
            ("LINEBELOW", (0, -1), (-1, -1), 0.9, colors.HexColor("#2b2118")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>จำนวนรวม</b> &nbsp;&nbsp; {info['total_qty_count']}", style_meta))
        story.append(Spacer(1, 1 * mm))

        promo_suffix = f" ({info['promo_name']})" if info.get("promo_name") else ""
        sum_rows = [
            [Paragraph("รวมเป็นเงิน (รวมเป็นเงินก่อนคิดภาษีและส่วนลด)", style_cell_r), Paragraph(_fmt_money(info["subtotal"]), style_cell_r)],
            [Paragraph(f"ส่วนลด{promo_suffix}", style_cell_r), Paragraph(_fmt_money(info["discount"]), style_cell_r)],
            [Paragraph("จำนวนเงินหลังหักส่วนลด", style_cell_r), Paragraph(_fmt_money(info["after_discount"]), style_cell_r)],
        ]
        if info["service_charge"] > 0:
            pct = info.get("service_charge_percent")
            sc_label = f"ค่าบริการ ({pct:g}%)" if pct else "ค่าบริการ"
            sum_rows.append([Paragraph(sc_label, style_cell_r), Paragraph(_fmt_money(info["service_charge"]), style_cell_r)])

        sum_rows.extend([
            [Paragraph("ราคาไม่รวมภาษีมูลค่าเพิ่ม", style_cell_r), Paragraph(_fmt_money(info["pre_vat"]), style_cell_r)],
            [Paragraph("ภาษีมูลค่าเพิ่ม 7%", style_cell_r), Paragraph(_fmt_money(info["vat"]), style_cell_r)],
            [Paragraph("รวมทั้งสิ้น (ยอดชำระสุทธิ)", style_total_l), Paragraph(f"{_fmt_money(info['total'])} บาท", style_total_r)],
        ])

        sum_table = Table(sum_rows, colWidths=[122 * mm, 48 * mm])
        sum_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, -1), (-1, -1), 0.9, colors.HexColor("#2b2118")),
        ]))
        story.append(sum_table)
        story.append(Spacer(1, 3 * mm))

        pay_rows = [
            [Paragraph("<b>ช่องทางการชำระ :</b>", style_cell_b), Paragraph(info["method_th"], style_cell), Paragraph("", style_cell_r)],
        ]
        if info["method"] == "cash":
            pay_rows.append([Paragraph("รับเงินมา", style_cell), Paragraph("", style_cell), Paragraph(f"{_fmt_money(info['received'])} บาท", style_cell_r)])
            pay_rows.append([Paragraph("เงินทอน", style_cell_b), Paragraph("", style_cell), Paragraph(f"{_fmt_money(info['change'])} บาท", style_cell_br)])

        pay_table = Table(pay_rows, colWidths=[45 * mm, 77 * mm, 48 * mm])
        pay_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEBELOW", (0, -1), (-1, -1), 0.9, colors.HexColor("#2b2118")),
        ]))
        story.append(pay_table)
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph(shop["shop_name"], style_foot_b))
        story.append(Paragraph("ขอบคุณที่ใช้บริการ", style_foot))

        doc.build(story)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"สร้างไฟล์ใบเสร็จ PDF ไม่สำเร็จ: {e}") from None

    return path


def export_receipt(bill_or_session_id, fmt: str = "pdf", out_dir: Path | str | None = None,
                   filename: str | None = None) -> Path:
    """ส่งออกใบเสร็จตามชนิดไฟล์ที่เลือก ('pdf' หรือ 'txt') -> Path"""
    kind = (fmt or "").strip().lower().lstrip(".")
    if kind == "pdf":
        return export_receipt_pdf(bill_or_session_id, out_dir=out_dir, filename=filename)
    if kind == "txt":
        return export_receipt_txt(bill_or_session_id, out_dir=out_dir, filename=filename)
    raise ValueError("ชนิดไฟล์ใบเสร็จไม่ถูกต้อง (รองรับเฉพาะ pdf และ txt)")
