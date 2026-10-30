"""services/weigh_service.py — รายการชั่งกิโล (พนักงานชั่งแล้วบันทึกที่หน้าชั่ง)

น้ำหนักเก็บเป็นกรัม (int) ; 1 ขีด = 100 กรัม ; 1 กก. = 1000 กรัม
กติกาการชั่งน้ำหนัก:
- การชั่งครั้งแรกของแต่ละโต๊ะ (รอบการให้บริการปัจจุบันที่ยังไม่มีรายการชั่ง active) ต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม (1,000 กรัม)
- หลังจากบันทึกการชั่งครั้งแรกสำเร็จแล้ว การชั่งครั้งถัดไปของโต๊ะเดียวกันสามารถชั่งน้ำหนักเท่าใดก็ได้ (1–50,000 กรัม)
- หากรายการชั่งครั้งแรกถูกยกเลิกจนไม่เหลือรายการชั่งที่ใช้งานอยู่ของโต๊ะในรอบนั้น หรือเริ่มรอบบริการใหม่ จะกลับมาใช้เงื่อนไขชั่งครั้งแรก 1 กิโลกรัมอีกครั้ง
อัตราราคาชั่งกิโลอ่านจาก settings_service ('weigh_price_per_kg', ค่าเริ่มต้น 299 บาท/กก.)
ราคา = น้ำหนัก(กก.) × ราคา/กก. ปัดเศษ 2 ตำแหน่ง (ปัดขึ้นที่ .5) ; ราคา/ชื่อตอนชั่งถูกเก็บไว้ (snapshot)
ชั่งได้เฉพาะรอบสถานะ open ; ตัดสต๊อก (กก.) แบบไม่เข้มงวด (ตัดจนเหลือ 0 ไม่ error)
ยกเลิกรายการ: ต้องใส่เหตุผล, คืนสต๊อก, log, แจ้งลูกค้า (ทำได้ตอน open/awaiting_payment)
"""
from decimal import ROUND_HALF_UP, Decimal

import config
from database import db
from services import log_service, notice_service, settings_service, stock_service, table_service

MAX_WEIGHT_GRAMS = 50_000  # กันกรอกผิด: เกิน 50 กก. ต่อครั้ง
MIN_FIRST_WEIGH_GRAMS = getattr(config, "MIN_FIRST_WEIGH_GRAMS", 1000)
FIRST_WEIGH_ERROR_MSG = "การชั่งครั้งแรกของโต๊ะต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม"
DEFAULT_WEIGH_NAME = "หมูกระทะชั่งกิโล"


def kheed_to_grams(kheed: float) -> int:
    """แปลงขีด -> กรัม (เช่น 2.5 ขีด = 250)"""
    return int(round(float(kheed) * (config.GRAMS_PER_KG / config.KHEED_PER_KG)))


def grams_to_kheed(grams: int) -> float:
    """แปลงกรัม -> ขีด"""
    return grams / (config.GRAMS_PER_KG / config.KHEED_PER_KG)


def kg_to_grams(kg: float) -> int:
    """แปลงกิโลกรัม -> กรัม (เช่น 1.2 กก. = 1200)"""
    return int(round(float(kg) * config.GRAMS_PER_KG))


def grams_to_kg(grams: int) -> float:
    """แปลงกรัม -> กิโลกรัม"""
    return grams / config.GRAMS_PER_KG


def get_price_per_kg(conn=None) -> float:
    """อัตราราคาหมูกระทะชั่งกิโล (บาท/กก.) จากตาราง settings (ค่าเริ่มต้น 299 บาท/กก.)"""
    row = db.query_one("SELECT value FROM settings WHERE key = 'weigh_price_per_kg'", conn=conn)
    if row is not None:
        try:
            val = float(row["value"])
            if val > 0:
                return round(val, 2)
        except (TypeError, ValueError):
            pass
    val = settings_service.get_float("weigh_price_per_kg", float(config.DEFAULT_WEIGH_PRICE_PER_KG))
    return round(val if val > 0 else float(config.DEFAULT_WEIGH_PRICE_PER_KG), 2)


def calc_amount(weight_grams: int, price_per_kg: float | None = None) -> float:
    """ราคา = น้ำหนัก(กก.) × ราคา/กก. ปัด 2 ตำแหน่ง (ROUND_HALF_UP) -> float"""
    rate = get_price_per_kg() if price_per_kg is None else price_per_kg
    amount = Decimal(weight_grams) * Decimal(str(rate)) / Decimal(config.GRAMS_PER_KG)
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _entry(row) -> dict:
    d = dict(row)
    d["weight_kheed"] = grams_to_kheed(d["weight_grams"])
    d["weight_kg"] = grams_to_kg(d["weight_grams"])
    return d


def get_entry(entry_id: int) -> dict | None:
    """รายการชั่งตาม id -> dict (+ weight_kheed, weight_kg) หรือ None"""
    r = db.query_one("SELECT * FROM weigh_entries WHERE id = ?", (entry_id,))
    return _entry(r) if r else None


def list_entries(session_id: int, include_cancelled: bool = False) -> list[dict]:
    """รายการชั่งของรอบ เก่าสุดก่อน"""
    sql = "SELECT * FROM weigh_entries WHERE session_id = ?" + ("" if include_cancelled else " AND status = 'active'") + " ORDER BY id"
    return [_entry(r) for r in db.query_all(sql, (session_id,))]


def is_first_weigh(session_id: int, conn=None) -> bool:
    """ตรวจสอบจากข้อมูลจริงของรอบการให้บริการ (session_id) ว่าโต๊ะนี้ยังไม่เคยมีรายการชั่งที่ใช้งานอยู่ใช่หรือไม่"""
    if session_id is None:
        return True
    row = db.query_one(
        "SELECT COUNT(*) AS c FROM weigh_entries WHERE session_id = ? AND status = 'active'",
        (session_id,), conn=conn,
    )
    return (row["c"] if row else 0) == 0


def session_total(session_id: int) -> float:
    """ยอดรวมรายการชั่งที่ไม่ยกเลิกของรอบ (บาท)"""
    return round(db.query_one("SELECT COALESCE(SUM(amount), 0) AS t FROM weigh_entries "
                              "WHERE session_id = ? AND status = 'active'", (session_id,))["t"], 2)


def get_default_weighed_item(conn=None) -> dict:
    """คืนรายการเมนูชั่งกิโลหลักสำหรับหน้าชั่ง (สร้างให้อัตโนมัติถ้ายังไม่มีในฐานข้อมูล)"""
    rate = get_price_per_kg(conn=conn)
    row = db.query_one(
        "SELECT * FROM menu_items WHERE item_type = ? AND active = 1 AND is_sold_out = 0 "
        "ORDER BY sort_order, id LIMIT 1",
        (config.MENU_TYPE_WEIGHED,), conn=conn,
    )
    if row is None:
        row = db.query_one(
            "SELECT * FROM menu_items WHERE item_type = ? AND active = 1 ORDER BY sort_order, id LIMIT 1",
            (config.MENU_TYPE_WEIGHED,), conn=conn,
        )
    if row is not None:
        return dict(row)

    # กรณีฐานข้อมูลยังไม่มีเมนูชั่งกิโลที่เปิดใช้งานเลย ให้สร้างหมวดและเมนูชั่งกิโลหลัก
    cat = db.query_one("SELECT id FROM menu_categories ORDER BY sort_order, id LIMIT 1", conn=conn)
    if cat is None:
        cid = db.execute(
            "INSERT INTO menu_categories (name, sort_order, active) VALUES (?, 1, 1)",
            (DEFAULT_WEIGH_NAME,), conn=conn,
        )
    else:
        cid = cat["id"]
    iid = db.execute(
        "INSERT INTO menu_items (category_id, name, item_type, price, is_sold_out, stock_item_id, sort_order, active) "
        "VALUES (?, ?, ?, ?, 0, NULL, 1, 1)",
        (cid, DEFAULT_WEIGH_NAME, config.MENU_TYPE_WEIGHED, rate), conn=conn,
    )
    return dict(db.query_one("SELECT * FROM menu_items WHERE id = ?", (iid,), conn=conn))


def add_entry(session_id: int, menu_item_id: int | None = None, weight_grams: int | None = None,
              user_id: int | None = None) -> dict:
    """บันทึกรายการชั่ง -> dict รายการ
    รองรับทั้งการส่ง menu_item_id=None (ใช้เมนูชั่งกิโลหลักและอัตราจาก settings_service)
    และการระบุ menu_item_id โดยตรง
    ValueError ถ้า:
      - รอบไม่ใช่ open
      - การชั่งครั้งแรกของโต๊ะในรอบนี้มีน้ำหนักน้อยกว่า 1 กิโลกรัม (1,000 กรัม)
      - ไม่ใช่เมนูชั่งกิโล / เมนูปิดใช้งานหรือหมด / น้ำหนักไม่ใช่จำนวนเต็มกรัม 1..50000"""
    if not isinstance(weight_grams, int) or isinstance(weight_grams, bool) or not (0 < weight_grams <= MAX_WEIGHT_GRAMS):
        raise ValueError("น้ำหนักไม่ถูกต้อง (ต้องเป็นกรัมจำนวนเต็ม 1–50,000)")
    with db.transaction() as conn:
        s = db.query_one("SELECT s.status, t.table_no FROM table_sessions s JOIN tables t ON t.id = s.table_id "
                         "WHERE s.id = ?", (session_id,), conn=conn)
        if s is None:
            raise ValueError("ไม่พบรอบของโต๊ะนี้")
        if s["status"] != config.SESSION_OPEN:
            raise ValueError("ชั่งได้เฉพาะโต๊ะที่ยืนยันและกำลังใช้งานอยู่")

        # ตรวจสอบเงื่อนไขการชั่งครั้งแรกของแต่ละโต๊ะจากฐานข้อมูลจริงภายใน transaction
        if is_first_weigh(session_id, conn=conn) and weight_grams < MIN_FIRST_WEIGH_GRAMS:
            raise ValueError(FIRST_WEIGH_ERROR_MSG)

        setting_rate = get_price_per_kg(conn=conn)
        if menu_item_id is None:
            m = get_default_weighed_item(conn=conn)
            menu_item_id = m["id"]
            if m["is_sold_out"]:
                raise ValueError(f"{m['name']} หมดแล้ว")
            price_per_kg = setting_rate
            name_snapshot = DEFAULT_WEIGH_NAME
        else:
            row = db.query_one("SELECT * FROM menu_items WHERE id = ?", (menu_item_id,), conn=conn)
            if row is None or not row["active"]:
                raise ValueError("ไม่พบเมนูนี้")
            m = dict(row)
            if m["item_type"] != config.MENU_TYPE_WEIGHED:
                raise ValueError("เมนูนี้ไม่ใช่เมนูชั่งกิโล")
            if m["is_sold_out"]:
                raise ValueError(f"{m['name']} หมดแล้ว")
            price_per_kg = float(m["price"]) if m["price"] else setting_rate
            name_snapshot = m["name"]

        amount = calc_amount(weight_grams, price_per_kg)
        eid = db.execute(
            "INSERT INTO weigh_entries (session_id, menu_item_id, name_snapshot, weight_grams, price_per_kg, amount, "
            "status, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (session_id, menu_item_id, name_snapshot, weight_grams, price_per_kg, amount, user_id, db.now_str()),
            conn=conn,
        )
        stock_service.deduct_for_menu_item(menu_item_id, weight_grams / config.GRAMS_PER_KG, "ชั่งขายหน้าโต๊ะ",
                                           user_id=user_id, ref_type="weigh_entry", ref_id=eid, strict=False, conn=conn)
        table_service.touch_session(session_id, conn=conn)
        log_service.log_action(
            "weigh_add",
            f"โต๊ะ {s['table_no']} ชั่ง {name_snapshot} {weight_grams} กรัม ({price_per_kg:g} บาท/กก.) = {amount:g} บาท",
            user_id=user_id, ref_type="weigh_entry", ref_id=eid, conn=conn,
        )
    return get_entry(eid)


def cancel_entry(entry_id: int, reason: str, user_id: int) -> dict:
    """ยกเลิกรายการชั่ง (ต้องมีเหตุผล) : คืนสต๊อก, log, แจ้งลูกค้า
    ValueError ถ้าไม่มีเหตุผล/ไม่พบรายการ/ยกเลิกไปแล้ว/รอบปิดแล้ว (ทำได้เฉพาะ open และ awaiting_payment)"""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("กรุณาระบุเหตุผลที่ยกเลิก")
    with db.transaction() as conn:
        e = db.query_one("SELECT * FROM weigh_entries WHERE id = ?", (entry_id,), conn=conn)
        if e is None:
            raise ValueError("ไม่พบรายการชั่ง")
        if e["status"] == "cancelled":
            raise ValueError("รายการนี้ถูกยกเลิกไปแล้ว")
        s = db.query_one("SELECT status FROM table_sessions WHERE id = ?", (e["session_id"],), conn=conn)
        if s["status"] not in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT):
            raise ValueError("โต๊ะนี้ปิดแล้ว ยกเลิกรายการไม่ได้")
        db.execute("UPDATE weigh_entries SET status='cancelled', cancel_reason=? WHERE id=?", (reason, entry_id), conn=conn)
        stock_service.return_to_stock(e["menu_item_id"], e["weight_grams"] / config.GRAMS_PER_KG,
                                      "ยกเลิกรายการชั่ง", user_id=user_id, ref_type="weigh_entry", ref_id=entry_id, conn=conn)
        notice_service.add_notice(e["session_id"], "item_cancelled",
                                  f"รายการชั่ง {e['name_snapshot']} {e['weight_grams']} กรัม ถูกยกเลิก เหตุผล: {reason}", conn=conn)
        table_service.touch_session(e["session_id"], conn=conn)
        log_service.log_action("weigh_cancel", f"ยกเลิกรายการชั่ง {e['name_snapshot']} {e['weight_grams']} กรัม "
                               f"({e['amount']:g} บาท) เหตุผล: {reason}", user_id=user_id,
                               ref_type="weigh_entry", ref_id=entry_id, conn=conn)
    return get_entry(entry_id)
