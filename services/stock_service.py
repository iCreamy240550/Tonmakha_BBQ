"""services/stock_service.py — สต๊อกวัตถุดิบ/สินค้า + ประวัติการเคลื่อนไหว (stock_movements) + การลบอย่างปลอดภัย

หน่วยของเนื้อสัตว์คือ 'กก.' (ทศนิยม) ; เมนูผูกสต๊อกด้วย menu_items.stock_item_id
สต๊อกลงมาเป็น 0 -> เมนูที่ผูกอยู่หมดอัตโนมัติ (+แจ้งลูกค้า) ; เติมสต๊อกผ่าน restock() -> เมนูกลับมามีขาย
ปริมาณไม่ติดลบ (ปัดเป็น 0) และบันทึกส่วนที่เปลี่ยนจริงลง movement
ส่ง conn=conn ได้เมื่อเรียกภายใน transaction ของผู้เรียก
"""
import config
from database import db
from services import auth_service, log_service, menu_service, settings_service


def get_default_low_threshold(conn=None) -> float:
    """เกณฑ์สต๊อกใกล้หมดเริ่มต้นจากหน้าตั้งค่า (ค่าเริ่มต้น 5 หน่วย)"""
    row = db.query_one("SELECT value FROM settings WHERE key = 'stock_low_threshold'", conn=conn)
    if row is not None:
        try:
            return max(0.0, float(row["value"]))
        except (TypeError, ValueError):
            pass
    return float(config.DEFAULT_SETTINGS.get("stock_low_threshold", config.DEFAULT_STOCK_LOW_THRESHOLD))


def effective_min_quantity(row_or_dict, conn=None) -> float:
    """เกณฑ์แจ้งเตือนของรายการสต๊อก: ถ้าตั้งค่าเฉพาะรายการไว้ (> 0) ใช้ค่านั้น มิฉะนั้นใช้ค่าเริ่มต้นจาก settings"""
    min_q = float(row_or_dict["min_quantity"] or 0)
    if min_q > 0:
        return min_q
    return get_default_low_threshold(conn=conn)


def _row(r, conn=None) -> dict:
    d = dict(r)
    d["active"] = bool(d["active"])
    threshold = effective_min_quantity(d, conn=conn)
    d["effective_min_quantity"] = threshold
    d["is_out"] = d["quantity"] <= 0
    d["is_low"] = d["quantity"] <= threshold
    d["alert_level"] = d.get("alert_level") or "normal"
    return d


def get_item(stock_item_id: int, conn=None) -> dict | None:
    """รายการสต๊อก -> dict (+ is_low, is_out, effective_min_quantity) หรือ None"""
    r = db.query_one("SELECT * FROM stock_items WHERE id = ?", (stock_item_id,), conn=conn)
    return _row(r, conn=conn) if r else None


def list_items(include_inactive: bool = False) -> list[dict]:
    """รายการสต๊อกทั้งหมดเรียงตามชื่อ (+ is_low)"""
    sql = "SELECT * FROM stock_items" + ("" if include_inactive else " WHERE active = 1") + " ORDER BY name"
    return [_row(r) for r in db.query_all(sql)]


def list_low_stock() -> list[dict]:
    """รายการที่เหลือ <= จุดเตือนขั้นต่ำ (เฉพาะที่ใช้งาน)"""
    return [i for i in list_items() if i["is_low"]]


def add_item(name: str, unit: str, quantity: float = 0, min_quantity: float | None = None,
             user_id: int | None = None) -> dict:
    """เพิ่มรายการสต๊อก (ถ้ามีจำนวนตั้งต้น จะบันทึก movement 'ตั้งต้น') ; ValueError ถ้าข้อมูลผิด"""
    name, unit = (name or "").strip(), (unit or "").strip()
    if not name or not unit:
        raise ValueError("กรุณากรอกชื่อและหน่วย")
    if min_quantity is None:
        min_quantity = get_default_low_threshold()
    if quantity < 0 or min_quantity < 0:
        raise ValueError("จำนวนต้องไม่ติดลบ")
    with db.transaction() as conn:
        sid = db.execute(
            "INSERT INTO stock_items (name, unit, quantity, min_quantity, active, alert_level) "
            "VALUES (?, ?, 0, ?, 1, 'normal')",
            (name, unit, min_quantity), conn=conn,
        )
        if quantity:
            _adjust(conn, sid, quantity, "ตั้งต้น", user_id, None, None)
        log_service.log_action("stock_add", f"เพิ่มสต๊อก {name} ({unit})", user_id=user_id,
                               ref_type="stock_item", ref_id=sid, conn=conn)
    return get_item(sid)


def update_item(stock_item_id: int, name: str | None = None, unit: str | None = None,
                min_quantity: float | None = None, active: bool | None = None,
                user_id: int | None = None) -> dict:
    """แก้ชื่อ/หน่วย/จุดเตือน/เปิด-ปิด (ส่งเฉพาะที่จะแก้) ; ValueError ถ้าไม่พบ"""
    with db.transaction() as conn:
        s = db.query_one("SELECT * FROM stock_items WHERE id = ?", (stock_item_id,), conn=conn)
        if s is None:
            raise ValueError("ไม่พบรายการสต๊อก")
        if min_quantity is not None and min_quantity < 0:
            raise ValueError("จำนวนต้องไม่ติดลบ")
        new_min = s["min_quantity"] if min_quantity is None else min_quantity
        new_active = s["active"] if active is None else (1 if active else 0)
        db.execute(
            "UPDATE stock_items SET name=?, unit=?, min_quantity=?, active=? WHERE id=?",
            (
                ((name or "").strip() or s["name"]),
                ((unit or "").strip() or s["unit"]),
                new_min,
                new_active,
                stock_item_id,
            ),
            conn=conn,
        )
        # หากตั้งเกณฑ์ใหม่แล้วสต๊อกปัจจุบันสูงกว่าเกณฑ์ หรือปิดใช้งานรายการ ให้รีเซ็ตสถานะแจ้งเตือน
        updated = db.query_one("SELECT * FROM stock_items WHERE id = ?", (stock_item_id,), conn=conn)
        threshold = effective_min_quantity(updated, conn=conn)
        if not new_active or updated["quantity"] > threshold:
            _reset_stock_alert_state(conn, stock_item_id)
        log_service.log_action("stock_update", f"แก้สต๊อก {s['name']}", user_id=user_id,
                               ref_type="stock_item", ref_id=stock_item_id, conn=conn)
    return get_item(stock_item_id)


def _reset_stock_alert_state(conn, stock_item_id: int) -> None:
    """คืนสถานะแจ้งเตือนสต๊อกกลับเป็นปกติเมื่อเติมสต๊อกสูงกว่าเกณฑ์หรือปิดใช้งาน"""
    db.execute("UPDATE stock_items SET alert_level = 'normal' WHERE id = ?", (stock_item_id,), conn=conn)
    open_alerts = db.query_all(
        "SELECT id, message FROM staff_alerts WHERE stock_item_id = ? AND status IN ('active','snoozed')",
        (stock_item_id,), conn=conn,
    )
    now = db.now_str()
    for a in open_alerts:
        db.execute(
            "UPDATE staff_alerts SET status='resolved', resolution='auto_cleared', resolved_at=?, snooze_until=NULL "
            "WHERE id=?",
            (now, a["id"]), conn=conn,
        )
        log_service.log_action(
            "alert_auto_clear",
            f"แจ้งเตือนสต๊อกหมดเงื่อนไขแล้ว (ปิดอัตโนมัติ): {a['message']}",
            actor="ระบบ", ref_type="staff_alert", ref_id=a["id"], conn=conn,
        )


def _adjust(conn, stock_item_id, change_qty, reason, user_id, ref_type, ref_id) -> tuple[float, float]:
    """แกนกลาง -> (ปริมาณเดิม, ปริมาณใหม่) ; เรียกภายใน transaction เท่านั้น"""
    s = db.query_one("SELECT * FROM stock_items WHERE id = ?", (stock_item_id,), conn=conn)
    if s is None:
        raise ValueError("ไม่พบรายการสต๊อก")
    old = s["quantity"]
    new = max(0.0, round(old + change_qty, 3))
    db.execute("UPDATE stock_items SET quantity = ? WHERE id = ?", (new, stock_item_id), conn=conn)
    db.execute(
        "INSERT INTO stock_movements (stock_item_id, change_qty, reason, ref_type, ref_id, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (stock_item_id, round(new - old, 3), reason, ref_type, ref_id, user_id, db.now_str()),
        conn=conn,
    )
    if new <= 0 < old or (new <= 0 and old <= 0 and change_qty < 0):
        for m in db.query_all("SELECT id FROM menu_items WHERE stock_item_id = ?", (stock_item_id,), conn=conn):
            menu_service.set_sold_out(m["id"], True, auto=True, conn=conn)
    threshold = effective_min_quantity(s, conn=conn)
    if new > threshold:
        _reset_stock_alert_state(conn, stock_item_id)
    elif new > 0 and s["alert_level"] == "out_of_stock":
        # จากหมด (0) ขึ้นมาแต่ยังอยู่ในเกณฑ์ใกล้หมด ให้ปิดแจ้งเตือน 'สินค้าหมด' เพื่อให้เตือน 'ใกล้หมด' ได้ถูกต้อง
        db.execute("UPDATE stock_items SET alert_level = 'normal' WHERE id = ?", (stock_item_id,), conn=conn)
        now = db.now_str()
        for a in db.query_all(
            "SELECT id FROM staff_alerts WHERE stock_item_id = ? AND kind = 'out_of_stock' AND status IN ('active','snoozed')",
            (stock_item_id,), conn=conn,
        ):
            db.execute(
                "UPDATE staff_alerts SET status='resolved', resolution='auto_cleared', resolved_at=?, snooze_until=NULL WHERE id=?",
                (now, a["id"]), conn=conn,
            )
    return old, new


def adjust(stock_item_id: int, change_qty: float, reason: str, user_id: int | None = None,
           ref_type: str | None = None, ref_id: int | None = None, conn=None) -> float:
    """ปรับสต๊อก (+เพิ่ม/-ลด) พร้อมบันทึก movement -> ปริมาณใหม่ ; ถึง 0 -> เมนูที่ผูกหมดอัตโนมัติ
    ValueError ถ้าไม่พบรายการ (ไม่เปิดเมนูกลับ — ใช้ restock สำหรับการเติม)"""
    if conn is not None:
        return _adjust(conn, stock_item_id, change_qty, reason, user_id, ref_type, ref_id)[1]
    with db.transaction() as c:
        return _adjust(c, stock_item_id, change_qty, reason, user_id, ref_type, ref_id)[1]


def restock(stock_item_id: int, quantity: float, user_id: int | None = None,
            reason: str = "เติมสต๊อก", ref_type: str | None = None, ref_id: int | None = None, conn=None) -> float:
    """เติมสต๊อก (quantity > 0) -> ปริมาณใหม่ ; ถ้าจาก 0 กลับมามี เมนูที่ผูกอยู่จะกลับมามีขายอัตโนมัติ
    ValueError ถ้า quantity <= 0 หรือไม่พบรายการ"""
    if quantity is None or quantity <= 0:
        raise ValueError("จำนวนที่เติมต้องมากกว่า 0")

    def _do(c) -> float:
        old, new = _adjust(c, stock_item_id, quantity, reason, user_id, ref_type, ref_id)
        if old <= 0 < new:
            for m in db.query_all("SELECT id FROM menu_items WHERE stock_item_id = ?", (stock_item_id,), conn=c):
                menu_service.set_sold_out(m["id"], False, user_id=user_id, auto=True, conn=c)
        return new
    if conn is not None:
        return _do(conn)
    with db.transaction() as c:
        return _do(c)


def deduct_for_menu_item(menu_item_id: int, quantity: float, reason: str, user_id: int | None = None,
                         ref_type: str | None = None, ref_id: int | None = None,
                         strict: bool = True, conn=None) -> None:
    """ตัดสต๊อกของเมนูที่ผูกสต๊อกไว้ (ไม่ผูก = ไม่ทำอะไร) ; quantity หน่วยเดียวกับสต๊อก (ชั่งต้องแปลงเป็น กก. ก่อน)
    strict=True: สต๊อกไม่พอ -> ValueError (ใช้กับลูกค้าสั่ง) ; strict=False: ตัดจนเหลือ 0 (ใช้กับพนักงานชั่ง)"""
    def _do(c) -> None:
        m = db.query_one("SELECT name, stock_item_id FROM menu_items WHERE id = ?", (menu_item_id,), conn=c)
        if m is None:
            raise ValueError("ไม่พบเมนูนี้")
        if m["stock_item_id"] is None:
            return
        s = db.query_one("SELECT * FROM stock_items WHERE id = ?", (m["stock_item_id"],), conn=c)
        if s is None:
            raise ValueError("ไม่พบรายการสต๊อกที่ผูกกับเมนูนี้")
        if strict and s["quantity"] < quantity:
            raise ValueError(f"{m['name']} เหลือไม่พอ (เหลือ {s['quantity']:g} {s['unit']})")
        _adjust(c, s["id"], -quantity, reason, user_id, ref_type, ref_id)
    if conn is not None:
        _do(conn)
    else:
        with db.transaction() as c:
            _do(c)


def return_to_stock(menu_item_id: int, quantity: float, reason: str, user_id: int | None = None,
                    ref_type: str | None = None, ref_id: int | None = None, conn=None) -> None:
    """คืนสต๊อกของเมนูที่ผูกไว้ (เช่น ยกเลิกรายการ) ; ไม่ผูก = ไม่ทำอะไร ; ถ้าจาก 0 กลับมามี เมนูกลับมามีขาย"""
    def _do(c) -> None:
        m = db.query_one("SELECT stock_item_id FROM menu_items WHERE id = ?", (menu_item_id,), conn=c)
        if m is None or m["stock_item_id"] is None:
            return
        restock(m["stock_item_id"], quantity, user_id=user_id, reason=reason, ref_type=ref_type, ref_id=ref_id, conn=c)
    if conn is not None:
        _do(conn)
    else:
        with db.transaction() as c:
            _do(c)


def get_movements(stock_item_id: int | None = None, limit: int = 200) -> list[dict]:
    """ประวัติการเคลื่อนไหว ใหม่สุดก่อน (+ item_name, user_name)"""
    where, params = "", ()
    if stock_item_id is not None:
        where, params = " WHERE m.stock_item_id = ?", (stock_item_id,)
    rows = db.query_all(
        "SELECT m.*, s.name AS item_name, u.display_name AS user_name FROM stock_movements m "
        "JOIN stock_items s ON s.id = m.stock_item_id LEFT JOIN users u ON u.id = m.created_by"
        + where + " ORDER BY m.id DESC LIMIT ?", params + (limit,))
    return [dict(r) for r in rows]


def get_delete_impact(stock_item_id: int, conn=None) -> dict:
    """ตรวจสอบความสัมพันธ์ของรายการสต๊อกก่อนลบ (เมนูที่ผูก, ประวัติการเคลื่อนไหว, ออเดอร์/รายการชั่ง)
    -> {'stock_item': dict, 'linked_menus': list[dict], 'movements_count': int,
        'order_refs': int, 'weigh_refs': int, 'can_hard_delete': bool, 'impact_text': str}"""
    item = get_item(stock_item_id, conn=conn)
    if item is None:
        raise ValueError("ไม่พบรายการสต๊อก")
    menus = [
        dict(r)
        for r in db.query_all(
            "SELECT id, name, active FROM menu_items WHERE stock_item_id = ? ORDER BY id",
            (stock_item_id,), conn=conn,
        )
    ]
    movements_count = db.query_one(
        "SELECT COUNT(*) AS c FROM stock_movements WHERE stock_item_id = ?",
        (stock_item_id,), conn=conn,
    )["c"]
    order_refs = db.query_one(
        "SELECT COUNT(*) AS c FROM order_items oi JOIN menu_items m ON m.id = oi.menu_item_id "
        "WHERE m.stock_item_id = ?",
        (stock_item_id,), conn=conn,
    )["c"]
    weigh_refs = db.query_one(
        "SELECT COUNT(*) AS c FROM weigh_entries w JOIN menu_items m ON m.id = w.menu_item_id "
        "WHERE m.stock_item_id = ?",
        (stock_item_id,), conn=conn,
    )["c"]
    can_hard_delete = (len(menus) == 0 and movements_count == 0 and order_refs == 0 and weigh_refs == 0)
    parts = []
    if menus:
        menu_names = ", ".join(m["name"] for m in menus)
        parts.append(f"เชื่อมกับเมนู {len(menus)} รายการ ({menu_names})")
    if movements_count:
        parts.append(f"มีประวัติการเคลื่อนไหวสต๊อก {movements_count} รายการ")
    if order_refs or weigh_refs:
        parts.append(f"อ้างอิงในออเดอร์/รายการชั่ง ({order_refs + weigh_refs} รายการ)")
    if can_hard_delete:
        impact_text = f"รายการ '{item['name']}' ยังไม่มีประวัติการเคลื่อนไหวและไม่ได้ผูกกับเมนูใด ระบบจะลบออกจากฐานข้อมูลอย่างถาวร"
    else:
        impact_text = (
            f"รายการ '{item['name']}' มีข้อมูลอ้างอิง: " + " · ".join(parts)
            + "\nเพื่อไม่ให้ประวัติทางบัญชี/ออเดอร์/รายงานเสียหาย ระบบจะไม่อนุญาตให้ลบประวัติย้อนหลัง "
            "และจะปิดใช้งาน (Soft Delete) รายการนี้แทน"
        )
    return {
        "stock_item": item,
        "linked_menus": menus,
        "movements_count": movements_count,
        "order_refs": order_refs,
        "weigh_refs": weigh_refs,
        "can_hard_delete": can_hard_delete,
        "impact_text": impact_text,
    }


def delete_item(stock_item_id: int, user_id: int | None = None, allow_soft_delete: bool = True) -> dict:
    """ลบรายการสต๊อก (เฉพาะเจ้าของร้าน):
    - หากไม่มีความสัมพันธ์กับเมนู/ประวัติการเคลื่อนไหว/ออเดอร์ จะลบจริงใน transaction
    - หากมีความสัมพันธ์ จะห้ามลบประวัติย้อนหลัง:
      - ถ้า allow_soft_delete=True และรายการยังเปิดอยู่ จะทำ soft delete (active=0) พร้อมบันทึก log
      - ถ้า allow_soft_delete=False หรือรายการถูกปิดใช้ไปแล้ว จะปฏิเสธด้วย ValueError พร้อมข้อความอธิบายและบันทึก log"""
    if user_id is not None:
        user = auth_service.get_user(user_id)
        if user is None or not auth_service.is_owner(user):
            raise ValueError("เฉพาะเจ้าของร้านเท่านั้นที่สามารถลบรายการสต๊อกได้")

    with db.transaction() as conn:
        impact = get_delete_impact(stock_item_id, conn=conn)
        item = impact["stock_item"]
        if impact["can_hard_delete"]:
            db.execute("DELETE FROM staff_alerts WHERE stock_item_id = ?", (stock_item_id,), conn=conn)
            db.execute("DELETE FROM stock_items WHERE id = ?", (stock_item_id,), conn=conn)
            log_service.log_action(
                "stock_delete",
                f"ลบรายการสต๊อก {item['name']} ({item['unit']}) ถาวร",
                user_id=user_id, ref_type="stock_item", ref_id=stock_item_id, conn=conn,
            )
            return {
                "id": stock_item_id,
                "name": item["name"],
                "action": "deleted",
                "deleted": True,
                "soft_deleted": False,
                "message": f"ลบรายการสต๊อก '{item['name']}' เรียบร้อยแล้ว",
            }

        reasons = []
        if impact["linked_menus"]:
            reasons.append(f"ผูกเมนู {len(impact['linked_menus'])} รายการ")
        if impact["movements_count"]:
            reasons.append(f"มีประวัติเคลื่อนไหว {impact['movements_count']} รายการ")
        if impact["order_refs"] or impact["weigh_refs"]:
            reasons.append(f"มีประวัติออเดอร์/ชั่ง {impact['order_refs'] + impact['weigh_refs']} รายการ")
        reason_str = ", ".join(reasons)

        if not allow_soft_delete or not item["active"]:
            log_service.log_action(
                "stock_delete_blocked",
                f"ปฏิเสธการลบสต๊อก {item['name']} ถาวร ({reason_str})",
                user_id=user_id, ref_type="stock_item", ref_id=stock_item_id, conn=conn,
            )
        else:
            db.execute("UPDATE stock_items SET active = 0 WHERE id = ?", (stock_item_id,), conn=conn)
            _reset_stock_alert_state(conn, stock_item_id)
            log_service.log_action(
                "stock_delete",
                f"ปิดใช้งานสต๊อก {item['name']} แทนการลบถาวรเพื่อรักษาประวัติ ({reason_str})",
                user_id=user_id, ref_type="stock_item", ref_id=stock_item_id, conn=conn,
            )
            return {
                "id": stock_item_id,
                "name": item["name"],
                "action": "soft_deleted",
                "deleted": False,
                "soft_deleted": True,
                "message": f"รายการ '{item['name']}' มีประวัติอ้างอิง ({reason_str}) ระบบจึงปิดใช้งานแทนการลบถาวรเพื่อรักษาประวัติ",
            }

    raise ValueError(
        f"ไม่สามารถลบรายการสต๊อก '{item['name']}' แบบถาวรได้ เนื่องจาก{reason_str} "
        "(ระบบป้องกันการลบประวัติย้อนหลัง)"
    )
