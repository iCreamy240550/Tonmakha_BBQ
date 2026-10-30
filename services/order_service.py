"""services/order_service.py — ออเดอร์เมนูปกติ (ลูกค้าสั่งผ่านมือถือ / พนักงานสั่งแทน)

- สั่งได้เฉพาะรอบ open และเมนูประเภท 'normal' (เมนูชั่งกิโลให้พนักงานชั่งที่ weigh_service)
- เมนูหมด/ปิดใช้งาน/สต๊อกไม่พอ -> ValueError ; ตัดสต๊อกทันทีที่สั่งเพียงครั้งเดียว ; ยกเลิกรายการคืนสต๊อก
- ตรวจสอบสต๊อกซ้ำที่ฐานข้อมูลภายใน transaction (BEGIN IMMEDIATE) กันหลายโต๊ะสั่งชิ้นสุดท้ายพร้อมกัน
- สถานะออเดอร์: new -> preparing -> served (หรือ new -> served) ; cancelled เมื่อยกเลิกครบทุกรายการ
- สถานะรายการ: active / served / cancelled
- ยกเลิกรายการ/ออเดอร์: ต้องมีเหตุผล, log, แจ้งลูกค้า
"""
import config
from database import db
from services import log_service, notice_service, stock_service, table_service

MAX_QTY_PER_LINE = 99
_TRANSITIONS = {"new": ("preparing", "served"), "preparing": ("served",)}
_STATUS_TH = {"new": "ใหม่", "preparing": "กำลังทำ", "served": "เสิร์ฟแล้ว", "cancelled": "ยกเลิก"}


def _items_of(order_id: int, include_cancelled: bool) -> list[dict]:
    sql = "SELECT * FROM order_items WHERE order_id = ?" + ("" if include_cancelled else " AND status != 'cancelled'") + " ORDER BY id"
    out = []
    for r in db.query_all(sql, (order_id,)):
        d = dict(r)
        d["line_total"] = round(d["unit_price"] * d["quantity"], 2)
        out.append(d)
    return out


def _with_items(row, include_cancelled: bool = False) -> dict:
    d = dict(row)
    d["status_th"] = _STATUS_TH.get(d["status"], d["status"])
    d["items"] = _items_of(d["id"], include_cancelled)
    return d


def get_order(order_id: int, include_cancelled: bool = False) -> dict | None:
    """ออเดอร์ + items -> dict หรือ None"""
    r = db.query_one("SELECT * FROM orders WHERE id = ?", (order_id,))
    return _with_items(r, include_cancelled) if r else None


def list_orders(session_id: int, include_cancelled: bool = False) -> list[dict]:
    """ออเดอร์ของรอบ เก่าสุดก่อน (ไม่รวมออเดอร์/รายการที่ยกเลิก เว้นแต่ include_cancelled=True)"""
    sql = "SELECT * FROM orders WHERE session_id = ?" + ("" if include_cancelled else " AND status != 'cancelled'") + " ORDER BY id"
    return [_with_items(r, include_cancelled) for r in db.query_all(sql, (session_id,))]


def list_active_orders() -> list[dict]:
    """ออเดอร์ที่ยังไม่เสิร์ฟ (new/preparing) ของทุกโต๊ะ เก่าสุดก่อน สำหรับหน้าครัว (+ table_no, table_name)"""
    rows = db.query_all(
        "SELECT o.*, t.table_no, t.name AS table_name FROM orders o JOIN table_sessions s ON s.id = o.session_id "
        "JOIN tables t ON t.id = s.table_id WHERE o.status IN ('new','preparing') ORDER BY o.id")
    return [_with_items(r) for r in rows]


def session_total(session_id: int) -> float:
    """ยอดรวมรายการสั่งที่ไม่ยกเลิกของรอบ (บาท)"""
    return round(db.query_one(
        "SELECT COALESCE(SUM(oi.unit_price * oi.quantity), 0) AS t FROM order_items oi JOIN orders o ON o.id = oi.order_id "
        "WHERE o.session_id = ? AND oi.status != 'cancelled'", (session_id,))["t"], 2)


def create_order(session_id: int, items: list[dict], note: str | None = None, user_id: int | None = None) -> dict:
    """สร้างออเดอร์ items = [{'menu_item_id': int, 'quantity': int}, ...] -> ออเดอร์ (dict + items)
    user_id=None = ลูกค้าสั่งเอง ; ทั้งหมดสำเร็จหรือไม่สำเร็จพร้อมกัน (atomic transaction)
    ValueError ถ้า: รอบไม่ใช่ open / ไม่มีรายการ / จำนวนไม่ใช่ 1..99 / เมนูไม่พบ-ปิด-หมด-ไม่ใช่ประเภทปกติ / สต๊อกไม่พอ"""
    if not items:
        raise ValueError("ยังไม่ได้เลือกรายการ")
    for it in items:
        q = it.get("quantity")
        if not isinstance(q, int) or isinstance(q, bool) or not (1 <= q <= MAX_QTY_PER_LINE):
            raise ValueError(f"จำนวนต้องเป็นจำนวนเต็ม 1–{MAX_QTY_PER_LINE}")
    with db.transaction() as conn:
        s = db.query_one("SELECT s.status, t.table_no FROM table_sessions s JOIN tables t ON t.id = s.table_id "
                         "WHERE s.id = ?", (session_id,), conn=conn)
        if s is None:
            raise ValueError("ไม่พบรอบของโต๊ะนี้")
        if s["status"] == config.SESSION_PENDING:
            raise ValueError("รอพนักงานยืนยันโต๊ะก่อน จึงจะสั่งได้")
        if s["status"] != config.SESSION_OPEN:
            raise ValueError("โต๊ะนี้ปิดแล้ว สั่งไม่ได้")

        # ตรวจสอบเมนูและสต๊อกคงเหลือล่าสุดในฐานข้อมูลก่อนบันทึก
        requested_by_stock: dict[int, tuple[str, int]] = {}
        for it in items:
            m = db.query_one("SELECT * FROM menu_items WHERE id = ?", (it.get("menu_item_id"),), conn=conn)
            if m is None or not m["active"]:
                raise ValueError("ไม่พบเมนูที่เลือก")
            if m["item_type"] != config.MENU_TYPE_NORMAL:
                raise ValueError(f"{m['name']} เป็นเมนูชั่งกิโล กรุณาแจ้งพนักงาน")
            if m["is_sold_out"]:
                raise ValueError(f"{m['name']} สินค้าหมดแล้ว")
            if m["stock_item_id"] is not None:
                st = db.query_one("SELECT * FROM stock_items WHERE id = ?", (m["stock_item_id"],), conn=conn)
                if st is None or not st["active"] or st["quantity"] <= 0:
                    raise ValueError(f"{m['name']} สินค้าหมดแล้ว")
                prev_name, prev_qty = requested_by_stock.get(st["id"], (m["name"], 0))
                total_req = prev_qty + it["quantity"]
                if st["quantity"] < total_req:
                    raise ValueError(
                        f"{m['name']} เหลือไม่พอ (คงเหลือ {st['quantity']:g} {st['unit']} แต่ต้องการสั่ง {total_req} {st['unit']})"
                    )
                requested_by_stock[st["id"]] = (prev_name, total_req)

        oid = db.execute("INSERT INTO orders (session_id, status, note, created_by, created_at) VALUES (?, 'new', ?, ?, ?)",
                         (session_id, (note or "").strip() or None, user_id, db.now_str()), conn=conn)
        lines = []
        for it in items:
            m = db.query_one("SELECT * FROM menu_items WHERE id = ?", (it.get("menu_item_id"),), conn=conn)
            iid = db.execute(
                "INSERT INTO order_items (order_id, menu_item_id, name_snapshot, unit_price, quantity, status) "
                "VALUES (?, ?, ?, ?, ?, 'active')", (oid, m["id"], m["name"], m["price"], it["quantity"]), conn=conn)
            stock_service.deduct_for_menu_item(m["id"], it["quantity"], "ลูกค้าสั่ง", user_id=user_id,
                                               ref_type="order_item", ref_id=iid, strict=True, conn=conn)
            lines.append(f"{m['name']} x{it['quantity']}")
        table_service.touch_session(session_id, conn=conn)
        log_service.log_action("order_create", f"โต๊ะ {s['table_no']} สั่ง: " + ", ".join(lines), user_id=user_id,
                               actor=None if user_id else "ลูกค้า", ref_type="order", ref_id=oid, conn=conn)
    return get_order(oid)


def set_order_status(order_id: int, new_status: str, user_id: int | None = None) -> dict:
    """เปลี่ยนสถานะออเดอร์ new->preparing->served (ข้ามไป served ได้) ; served = รายการ active เป็น served ทั้งหมด
    ValueError ถ้าไม่พบ/ย้อนสถานะ/สถานะไม่ถูกต้อง (ยกเลิกใช้ cancel_order/cancel_item)"""
    with db.transaction() as conn:
        o = db.query_one("SELECT * FROM orders WHERE id = ?", (order_id,), conn=conn)
        if o is None:
            raise ValueError("ไม่พบออเดอร์")
        if new_status not in _TRANSITIONS.get(o["status"], ()):
            raise ValueError(f"เปลี่ยนสถานะไม่ได้ ({_STATUS_TH.get(o['status'], o['status'])} -> "
                             f"{_STATUS_TH.get(new_status, new_status)})")
        db.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id), conn=conn)
        if new_status == "served":
            db.execute("UPDATE order_items SET status = 'served' WHERE order_id = ? AND status = 'active'", (order_id,), conn=conn)
        table_service.touch_session(o["session_id"], conn=conn)
        log_service.log_action("order_status", f"ออเดอร์ #{order_id} -> {_STATUS_TH[new_status]}", user_id=user_id,
                               ref_type="order", ref_id=order_id, conn=conn)
    return get_order(order_id)


def _cancel(conn, order_id: int, items: list, reason: str, user_id: int | None) -> None:
    o = db.query_one("SELECT * FROM orders WHERE id = ?", (order_id,), conn=conn)
    s = db.query_one("SELECT status FROM table_sessions WHERE id = ?", (o["session_id"],), conn=conn)
    if s["status"] not in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT):
        raise ValueError("โต๊ะนี้ปิดแล้ว ยกเลิกรายการไม่ได้")
    for it in items:
        db.execute("UPDATE order_items SET status='cancelled', cancel_reason=?, cancelled_by=?, cancelled_at=? WHERE id=?",
                   (reason, user_id, db.now_str(), it["id"]), conn=conn)
        stock_service.return_to_stock(it["menu_item_id"], it["quantity"], "ยกเลิกรายการสั่ง", user_id=user_id,
                                      ref_type="order_item", ref_id=it["id"], conn=conn)
        notice_service.add_notice(o["session_id"], "item_cancelled",
                                  f"รายการ {it['name_snapshot']} x{it['quantity']} ถูกยกเลิก เหตุผล: {reason}", conn=conn)
        log_service.log_action("order_item_cancel", f"ยกเลิกรายการ {it['name_snapshot']} x{it['quantity']} "
                               f"(ออเดอร์ #{order_id}) เหตุผล: {reason}", user_id=user_id,
                               ref_type="order_item", ref_id=it["id"], conn=conn)
    left = db.query_one("SELECT COUNT(*) AS c FROM order_items WHERE order_id = ? AND status != 'cancelled'",
                        (order_id,), conn=conn)["c"]
    if left == 0:
        db.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,), conn=conn)
    table_service.touch_session(o["session_id"], conn=conn)


def cancel_item(order_item_id: int, reason: str, user_id: int) -> dict:
    """ยกเลิก 1 รายการ (ต้องมีเหตุผล) : คืนสต๊อก, log, แจ้งลูกค้า ; ยกเลิกครบทุกรายการ ออเดอร์เป็น cancelled
    -> ออเดอร์ล่าสุด (รวมรายการที่ยกเลิก) ; ValueError ถ้าไม่มีเหตุผล/ไม่พบ/ยกเลิกแล้ว/โต๊ะปิดแล้ว"""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("กรุณาระบุเหตุผลที่ยกเลิก")
    with db.transaction() as conn:
        it = db.query_one("SELECT * FROM order_items WHERE id = ?", (order_item_id,), conn=conn)
        if it is None:
            raise ValueError("ไม่พบรายการ")
        if it["status"] == "cancelled":
            raise ValueError("รายการนี้ถูกยกเลิกไปแล้ว")
        _cancel(conn, it["order_id"], [it], reason, user_id)
        order_id = it["order_id"]
    return get_order(order_id, include_cancelled=True)


def cancel_order(order_id: int, reason: str, user_id: int) -> dict:
    """ยกเลิกทั้งออเดอร์ (ทุกรายการที่ยังไม่ยกเลิก) ต้องมีเหตุผล -> ออเดอร์ (รวมรายการที่ยกเลิก)
    ValueError ถ้าไม่มีเหตุผล/ไม่พบ/ไม่เหลือรายการให้ยกเลิก/โต๊ะปิดแล้ว"""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("กรุณาระบุเหตุผลที่ยกเลิก")
    with db.transaction() as conn:
        if db.query_one("SELECT 1 FROM orders WHERE id = ?", (order_id,), conn=conn) is None:
            raise ValueError("ไม่พบออเดอร์")
        items = [dict(r) for r in db.query_all(
            "SELECT * FROM order_items WHERE order_id = ? AND status != 'cancelled'", (order_id,), conn=conn)]
        if not items:
            raise ValueError("ออเดอร์นี้ไม่มีรายการให้ยกเลิก")
        _cancel(conn, order_id, items, reason, user_id)
    return get_order(order_id, include_cancelled=True)
