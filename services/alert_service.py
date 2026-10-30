"""services/alert_service.py — แจ้งเตือนโต๊ะเงียบ และ แจ้งเตือนสต๊อกใกล้หมด/สินค้าหมด

ประเภทแจ้งเตือน:
- กรณี A 'pending_timeout': รอบ pending นานเกิน alert_pending_minutes (นับจาก started_at) ยังไม่มีใครยืนยัน
- กรณี B 'idle_open'     : รอบ open ที่ไม่มีรายการชั่ง/รายการสั่ง (ที่ไม่ยกเลิก) และ last_activity ผ่านมาเกิน
                           alert_idle_open_minutes
- กรณี C 'low_stock'     : สต๊อกมากกว่า 0 แต่ต่ำกว่าหรือเท่ากับเกณฑ์ -> 'สต๊อกใกล้หมด: [ชื่อสินค้า] เหลือ [จำนวน] [หน่วย]'
- กรณี D 'out_of_stock'  : สต๊อกเท่ากับ 0 -> 'สินค้าหมด: [ชื่อสินค้า] เหลือ 0 [หน่วย]'

กติกา:
- โต๊ะเงียบ: 1 รอบ + 1 ชนิด มีแจ้งเตือนได้ 1 แถวตลอดชีวิตรอบ ; เงื่อนไขหาย -> auto_cleared
- สต๊อก: แจ้งเตือนเมื่อเปลี่ยนระดับเข้าสู่ใกล้หมดหรือสินค้าหมด ไม่สร้างแจ้งเตือนซ้ำทุกครั้งที่ refresh ;
        เมื่อเติมสต๊อกกลับสูงกว่าเกณฑ์ จะคืนสถานะปกติ (alert_level='normal') และปิดแจ้งเตือนเดิม
        เพื่อให้แจ้งเตือนรอบใหม่ได้ในอนาคตเมื่อสต๊อกลดลงอีกครั้ง
- เสียงเตือน: UI เรียก pop_sound_alerts() ซึ่งคืนแจ้งเตือนที่ยังไม่เคยเล่นเสียง และมาร์กว่าเล่นแล้ว
"""
from datetime import datetime, timedelta

import config
from database import db
from services import log_service, settings_service, stock_service, table_service

KIND_PENDING = "pending_timeout"
KIND_IDLE_OPEN = "idle_open"
KIND_LOW_STOCK = "low_stock"
KIND_OUT_OF_STOCK = "out_of_stock"

STOCK_KINDS = (KIND_LOW_STOCK, KIND_OUT_OF_STOCK)
TABLE_KINDS = (KIND_PENDING, KIND_IDLE_OPEN)

KIND_TH = {
    KIND_PENDING: "รอยืนยันนาน",
    KIND_IDLE_OPEN: "โต๊ะเงียบ",
    KIND_LOW_STOCK: "สต๊อกใกล้หมด",
    KIND_OUT_OF_STOCK: "สินค้าหมด",
}

_ALERT_SELECT = (
    "SELECT a.*, s.status AS session_status, s.started_at, s.last_activity, "
    "t.id AS table_id, t.table_no, t.name AS table_name, "
    "st.name AS stock_name, st.unit AS stock_unit, st.quantity AS stock_quantity "
    "FROM staff_alerts a "
    "LEFT JOIN table_sessions s ON s.id = a.session_id "
    "LEFT JOIN tables t ON t.id = s.table_id "
    "LEFT JOIN stock_items st ON st.id = a.stock_item_id"
)


# ---------------------------------------------------------------- ตัวช่วยภายใน

def _minutes(key: str) -> int:
    return max(1, settings_service.get_int(key, config.DEFAULT_SETTINGS[key]))


def _fmt_qty(val: float | int | None) -> str:
    v = max(0.0, float(val or 0))
    if v == int(v):
        return str(int(v))
    return f"{v:,.3f}".rstrip("0").rstrip(".")


def _alert(row) -> dict:
    d = dict(row)
    d["kind_th"] = KIND_TH.get(d["kind"], d["kind"])
    d["sound_played"] = bool(d["sound_played"])
    d["is_stock_alert"] = d["kind"] in STOCK_KINDS
    return d


def _has_items(session_id: int, conn=None) -> bool:
    c = db.query_one(
        "SELECT (SELECT COUNT(*) FROM weigh_entries WHERE session_id = ? AND status = 'active') + "
        "(SELECT COUNT(*) FROM order_items oi JOIN orders o ON o.id = oi.order_id "
        " WHERE o.session_id = ? AND oi.status != 'cancelled') AS c", (session_id, session_id), conn=conn)["c"]
    return c > 0


def _condition_holds(kind: str, session: dict, now: datetime, pending_min: int, idle_min: int, conn=None) -> bool:
    """เงื่อนไขของแจ้งเตือนโต๊ะชนิดนี้ยังเป็นจริงกับรอบนี้หรือไม่"""
    if kind == KIND_PENDING:
        return (session["status"] == config.SESSION_PENDING
                and now - db.parse_time(session["started_at"]) >= timedelta(minutes=pending_min))
    if kind == KIND_IDLE_OPEN:
        return (session["status"] == config.SESSION_OPEN
                and now - db.parse_time(session["last_activity"]) >= timedelta(minutes=idle_min)
                and not _has_items(session["id"], conn))
    return False


def _state_holds(kind: str, session_status: str | None, session_id: int | None, conn=None) -> bool:
    """สถานะ (ไม่รวมเวลา) ที่ทำให้แจ้งเตือนโต๊ะที่สร้างไปแล้วยังควรอยู่"""
    if not session_id:
        return False
    if kind == KIND_PENDING:
        return session_status == config.SESSION_PENDING
    if kind == KIND_IDLE_OPEN:
        return session_status == config.SESSION_OPEN and not _has_items(session_id, conn)
    return False


def _stock_state_holds(alert_row, conn=None) -> bool:
    """ตรวจสอบว่าแจ้งเตือนสต๊อกยังตรงกับระดับสต๊อกปัจจุบันหรือไม่"""
    sid = alert_row["stock_item_id"]
    if not sid:
        return False
    st = db.query_one("SELECT * FROM stock_items WHERE id = ?", (sid,), conn=conn)
    if st is None or not st["active"]:
        return False
    qty = float(st["quantity"])
    threshold = stock_service.effective_min_quantity(st, conn=conn)
    if alert_row["kind"] == KIND_OUT_OF_STOCK:
        return qty <= 0
    if alert_row["kind"] == KIND_LOW_STOCK:
        return 0 < qty <= threshold
    return False


def _message(kind: str, table_no: int, pending_min: int, idle_min: int) -> str:
    if kind == KIND_PENDING:
        return f"โต๊ะ {table_no} รอยืนยันเกิน {pending_min} นาทีแล้ว"
    return f"โต๊ะ {table_no} เปิดแล้วแต่ไม่มีรายการชั่ง/สั่งเกิน {idle_min} นาทีแล้ว"


def _stock_message(kind: str, name: str, qty: float, unit: str) -> str:
    if kind == KIND_OUT_OF_STOCK:
        return f"สินค้าหมด: {name} เหลือ 0 {unit}".strip()
    return f"สต๊อกใกล้หมด: {name} เหลือ {_fmt_qty(qty)} {unit}".strip()


def _get_for_action(conn, alert_id: int, allow_snoozed: bool = True) -> dict:
    r = db.query_one(_ALERT_SELECT + " WHERE a.id = ?", (alert_id,), conn=conn)
    if r is None:
        raise ValueError("ไม่พบแจ้งเตือน")
    if r["status"] == "resolved":
        raise ValueError("แจ้งเตือนนี้ถูกจัดการไปแล้ว")
    if r["status"] == "snoozed" and not allow_snoozed:
        raise ValueError("แจ้งเตือนนี้ถูกพักไว้อยู่")
    return dict(r)


def _resolve(conn, alert_id: int, resolution: str, user_id: int | None) -> None:
    db.execute("UPDATE staff_alerts SET status='resolved', resolution=?, resolved_by=?, resolved_at=?, "
               "snooze_until=NULL WHERE id=?", (resolution, user_id, db.now_str(), alert_id), conn=conn)


# ---------------------------------------------------------------- อ่าน

def get_alert(alert_id: int) -> dict | None:
    """แจ้งเตือนตาม id -> dict (+ kind_th, table_no, table_name, session_status, stock_name) หรือ None"""
    r = db.query_one(_ALERT_SELECT + " WHERE a.id = ?", (alert_id,))
    return _alert(r) if r else None


def list_active_alerts() -> list[dict]:
    """แจ้งเตือนที่ต้องแสดงเป็นแถบแดงตอนนี้ (status 'active') เก่าสุดก่อน"""
    return [_alert(r) for r in db.query_all(_ALERT_SELECT + " WHERE a.status = 'active' ORDER BY a.id")]


def list_recent_alerts(limit: int = 50) -> list[dict]:
    """ประวัติแจ้งเตือนทุกสถานะ ใหม่สุดก่อน (ดูย้อนหลัง)"""
    return [_alert(r) for r in db.query_all(_ALERT_SELECT + " ORDER BY a.id DESC LIMIT ?", (limit,))]


def active_count() -> int:
    """จำนวนแจ้งเตือนที่เป็น 'active' (ใช้โชว์ตัวเลขบนเมนู/แดชบอร์ด)"""
    return db.query_one("SELECT COUNT(*) AS c FROM staff_alerts WHERE status = 'active'")["c"]


# ---------------------------------------------------------------- ตรวจ (UI เรียกทุก 30 วินาที)

def _check_stock_alerts(conn, new_ids: list[int], cleared_ids: list[int]) -> None:
    """ตรวจสอบสต๊อกทุกรายการเพื่อสร้าง/อัปเดต/ล้างแจ้งเตือนสต๊อกใกล้หมดและสินค้าหมดโดยไม่สร้างซ้ำ"""
    stocks = db.query_all("SELECT * FROM stock_items ORDER BY id", conn=conn)
    for st in stocks:
        sid = st["id"]
        if not st["active"]:
            if st["alert_level"] != "normal":
                db.execute("UPDATE stock_items SET alert_level = 'normal' WHERE id = ?", (sid,), conn=conn)
            continue

        qty = float(st["quantity"])
        threshold = stock_service.effective_min_quantity(st, conn=conn)
        if qty <= 0:
            target_kind = KIND_OUT_OF_STOCK
        elif qty <= threshold:
            target_kind = KIND_LOW_STOCK
        else:
            target_kind = "normal"

        if target_kind == "normal":
            if st["alert_level"] != "normal":
                db.execute("UPDATE stock_items SET alert_level = 'normal' WHERE id = ?", (sid,), conn=conn)
            for a in db.query_all(
                "SELECT id, message FROM staff_alerts WHERE stock_item_id = ? AND status IN ('active','snoozed')",
                (sid,), conn=conn,
            ):
                _resolve(conn, a["id"], "auto_cleared", None)
                log_service.log_action(
                    "alert_auto_clear",
                    f"แจ้งเตือนสต๊อกหมดเงื่อนไขแล้ว (ปิดอัตโนมัติ): {a['message']}",
                    actor="ระบบ", ref_type="staff_alert", ref_id=a["id"], conn=conn,
                )
                cleared_ids.append(a["id"])
            continue

        # หากเปลี่ยนระดับระหว่าง low_stock <-> out_of_stock ให้ปิดแจ้งเตือนระดับเดิมก่อน
        for a in db.query_all(
            "SELECT id, kind, message FROM staff_alerts "
            "WHERE stock_item_id = ? AND kind != ? AND status IN ('active','snoozed')",
            (sid, target_kind), conn=conn,
        ):
            _resolve(conn, a["id"], "auto_cleared", None)
            cleared_ids.append(a["id"])

        msg = _stock_message(target_kind, st["name"], qty, st["unit"])
        existing_open = db.query_one(
            "SELECT * FROM staff_alerts WHERE stock_item_id = ? AND kind = ? AND status IN ('active','snoozed') "
            "ORDER BY id DESC LIMIT 1",
            (sid, target_kind), conn=conn,
        )
        if existing_open is not None:
            if existing_open["message"] != msg:
                db.execute("UPDATE staff_alerts SET message = ? WHERE id = ?", (msg, existing_open["id"]), conn=conn)
            if st["alert_level"] != target_kind:
                db.execute("UPDATE stock_items SET alert_level = ? WHERE id = ?", (target_kind, sid), conn=conn)
            continue

        # ถ้ายังไม่ได้อยู่ในระดับนี้มาก่อน (เพิ่งลดลงถึงเกณฑ์ หรือลดจากใกล้หมดเป็นหมด) ให้สร้างแจ้งเตือนใหม่ 1 ครั้ง
        if st["alert_level"] != target_kind:
            aid = db.execute(
                "INSERT INTO staff_alerts (session_id, stock_item_id, kind, message, status, created_at) "
                "VALUES (NULL, ?, ?, ?, 'active', ?)",
                (sid, target_kind, msg, db.now_str()), conn=conn,
            )
            db.execute("UPDATE stock_items SET alert_level = ? WHERE id = ?", (target_kind, sid), conn=conn)
            log_service.log_action(
                "alert_raised", msg, actor="ระบบ", ref_type="staff_alert", ref_id=aid, conn=conn
            )
            new_ids.append(aid)


def check_alerts(now: datetime | None = None) -> dict:
    """ตรวจโต๊ะทั้งหมดและสต๊อกทั้งหมดหนึ่งรอบ แล้วอัปเดตตาราง staff_alerts
    -> {'new': [alert dict], 'woken': [alert dict], 'cleared': [alert dict]}   (now ใช้ทดสอบเท่านั้น)"""
    now = now or datetime.now()
    pending_min, idle_min = _minutes("alert_pending_minutes"), _minutes("alert_idle_open_minutes")
    new_ids, woken_ids, cleared_ids = [], [], []
    with db.transaction() as conn:
        # 1) แจ้งเตือนโต๊ะเงียบใหม่
        sessions = db.query_all(
            "SELECT s.*, t.table_no FROM table_sessions s JOIN tables t ON t.id = s.table_id "
            "WHERE s.status IN ('pending','open')", conn=conn)
        for s in sessions:
            kind = KIND_PENDING if s["status"] == config.SESSION_PENDING else KIND_IDLE_OPEN
            if db.query_one("SELECT 1 FROM staff_alerts WHERE session_id = ? AND kind = ?",
                            (s["id"], kind), conn=conn):
                continue
            if _condition_holds(kind, dict(s), now, pending_min, idle_min, conn):
                msg = _message(kind, s["table_no"], pending_min, idle_min)
                aid = db.execute("INSERT INTO staff_alerts (session_id, kind, message, status, created_at) "
                                 "VALUES (?, ?, ?, 'active', ?)", (s["id"], kind, msg, db.now_str()), conn=conn)
                log_service.log_action("alert_raised", msg, actor="ระบบ", ref_type="staff_alert", ref_id=aid, conn=conn)
                new_ids.append(aid)

        # 2) แจ้งเตือนสต๊อกใกล้หมด / สินค้าหมด
        _check_stock_alerts(conn, new_ids, cleared_ids)

        # 3) แจ้งเตือนเดิมที่ยังไม่จบ (ทั้งโต๊ะและสต๊อก)
        open_alerts = db.query_all(_ALERT_SELECT + " WHERE a.status IN ('active','snoozed')", conn=conn)
        for a in open_alerts:
            if a["id"] in cleared_ids:
                continue
            is_stock = a["kind"] in STOCK_KINDS
            holds = _stock_state_holds(a, conn) if is_stock else _state_holds(a["kind"], a["session_status"], a["session_id"], conn)
            if not holds:
                _resolve(conn, a["id"], "auto_cleared", None)
                target_label = f"สต๊อก {a['stock_name'] or ''}".strip() if is_stock else f"โต๊ะ {a['table_no']}"
                log_service.log_action("alert_auto_clear",
                                       f"แจ้งเตือน{target_label} หมดเงื่อนไขแล้ว (ปิดอัตโนมัติ)",
                                       actor="ระบบ", ref_type="staff_alert", ref_id=a["id"], conn=conn)
                cleared_ids.append(a["id"])
            elif a["status"] == "snoozed" and a["snooze_until"] and now >= db.parse_time(a["snooze_until"]):
                db.execute("UPDATE staff_alerts SET status='active', sound_played=0, snooze_until=NULL WHERE id=?",
                           (a["id"],), conn=conn)
                log_service.log_action("alert_wake", f"เตือนซ้ำ: {a['message']}", actor="ระบบ",
                                       ref_type="staff_alert", ref_id=a["id"], conn=conn)
                woken_ids.append(a["id"])
    return {"new": [get_alert(i) for i in new_ids], "woken": [get_alert(i) for i in woken_ids],
            "cleared": [get_alert(i) for i in cleared_ids]}


def pop_sound_alerts() -> list[dict]:
    """แจ้งเตือน active ที่ยังไม่เคยเล่นเสียง -> list แล้วมาร์กว่าเล่นแล้ว (ให้ UI เล่นเสียงตามจำนวนที่ได้ครั้งเดียว)
    เรียกจากตัวเดียว (PC app) เท่านั้น"""
    with db.transaction() as conn:
        rows = db.query_all(_ALERT_SELECT + " WHERE a.status = 'active' AND a.sound_played = 0 ORDER BY a.id", conn=conn)
        if rows:
            db.executemany("UPDATE staff_alerts SET sound_played = 1 WHERE id = ?", [(r["id"],) for r in rows],
                           conn=conn)
    return [_alert(r) for r in rows]


# ---------------------------------------------------------------- ปุ่มของพนักงาน

def cancel_table(alert_id: int, user_id: int) -> dict:
    """ปุ่ม 'ยกเลิกโต๊ะ': ยกเลิกรอบ (table_service.cancel_session cancelled_by='staff') แล้วปิดแจ้งเตือน
    resolution 'cancelled_table' -> dict แจ้งเตือน ; ValueError ถ้าไม่พบ/จัดการแล้ว/ไม่ใช่แจ้งเตือนโต๊ะ"""
    a = _get_for_action(None, alert_id)
    if a["kind"] in STOCK_KINDS or not a.get("session_id"):
        raise ValueError("แจ้งเตือนสต๊อกไม่สามารถยกเลิกโต๊ะได้")
    reason = f"โต๊ะเงียบ ({KIND_TH.get(a['kind'])})"
    table_service.cancel_session(a["session_id"], cancelled_by="staff", user_id=user_id, reason=reason)
    with db.transaction() as conn:
        _resolve(conn, alert_id, "cancelled_table", user_id)
        log_service.log_action("alert_cancel_table", f"ยกเลิกโต๊ะ {a['table_no']} จากแจ้งเตือน: {a['message']}",
                               user_id=user_id, ref_type="staff_alert", ref_id=alert_id, conn=conn)
    return get_alert(alert_id)


def snooze(alert_id: int, user_id: int, now: datetime | None = None) -> dict:
    """ปุ่ม 'ปล่อยไว้': พักแจ้งเตือน alert_snooze_minutes นาที (status 'snoozed') แล้วเตือนอีกถ้าเงื่อนไขยังจริง
    -> dict แจ้งเตือน ; ValueError ถ้าไม่พบ/จัดการแล้ว/ถูกพักอยู่แล้ว"""
    minutes = _minutes("alert_snooze_minutes")
    with db.transaction() as conn:
        a = _get_for_action(conn, alert_id, allow_snoozed=False)
        until = ((now or datetime.now()) + timedelta(minutes=minutes)).strftime(db.TIME_FORMAT)
        db.execute("UPDATE staff_alerts SET status='snoozed', snooze_until=? WHERE id=?",
                   (until, alert_id), conn=conn)
        target = f"สต๊อก {a.get('stock_name') or ''}".strip() if a["kind"] in STOCK_KINDS else f"โต๊ะ {a['table_no']}"
        log_service.log_action("alert_snooze", f"ปล่อยไว้ {target} (เตือนอีกใน {minutes} นาที)",
                               user_id=user_id, ref_type="staff_alert", ref_id=alert_id, conn=conn)
    return get_alert(alert_id)


def mark_checked(alert_id: int, user_id: int) -> dict:
    """ปุ่ม 'ไปเช็คแล้ว' / 'รับทราบ': ปิดแจ้งเตือน resolution 'checked' -> dict แจ้งเตือน
    ValueError ถ้าไม่พบ/จัดการแล้ว"""
    with db.transaction() as conn:
        a = _get_for_action(conn, alert_id)
        _resolve(conn, alert_id, "checked", user_id)
        target = f"สต๊อก {a.get('stock_name') or ''}".strip() if a["kind"] in STOCK_KINDS else f"โต๊ะ {a['table_no']}"
        log_service.log_action("alert_checked", f"รับทราบ/ไปเช็ค {target} แล้ว: {a['message']}",
                               user_id=user_id, ref_type="staff_alert", ref_id=alert_id, conn=conn)
    return get_alert(alert_id)
