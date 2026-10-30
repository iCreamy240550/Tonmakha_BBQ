"""services/table_service.py — จัดการโต๊ะ และวงจรสถานะของรอบ (session) ของโต๊ะ

สถานะรอบ: pending -> open -> awaiting_payment -> closed ; ยกเลิก(cancelled) ได้จาก pending/open
"โต๊ะว่าง" = โต๊ะที่ไม่มีรอบ pending/open/awaiting_payment
ทุกฟังก์ชันที่เปลี่ยนสถานะจะ log ให้เอง ; ข้อผิดพลาดตามกติกา -> ValueError ข้อความไทย
ฟังก์ชันคืน dict (ไม่ใช่ Row)
"""
import config
from database import db
from services import log_service

ACTIVE_STATUSES = (config.SESSION_PENDING, config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT)
_ACTIVE_MARKS = ",".join("?" * len(ACTIVE_STATUSES))


# ---------------------------------------------------------------- จัดการโต๊ะ (เจ้าของ)

def get_table(table_id: int) -> dict | None:
    """โต๊ะตาม id -> dict หรือ None"""
    row = db.query_one("SELECT * FROM tables WHERE id = ?", (table_id,))
    return dict(row) if row else None


def get_table_by_no(table_no: int) -> dict | None:
    """โต๊ะตามเลขโต๊ะ -> dict หรือ None"""
    row = db.query_one("SELECT * FROM tables WHERE table_no = ?", (table_no,))
    return dict(row) if row else None


def list_tables(include_inactive: bool = False) -> list[dict]:
    """รายการโต๊ะเรียงตามเลขโต๊ะ (ไม่รวมแถวพิเศษ table_no = 0 สำหรับสั่งกลับบ้าน)"""
    sql = "SELECT * FROM tables WHERE table_no > 0" + ("" if include_inactive else " AND active = 1") + " ORDER BY table_no"
    return [dict(r) for r in db.query_all(sql)]


def add_table(table_no: int, name: str | None = None, user_id: int | None = None) -> dict:
    """เพิ่มโต๊ะ (สุ่มรหัสลับให้) -> dict ; ValueError ถ้าเลขโต๊ะซ้ำ/ไม่ใช่เลขบวก"""
    from database.seed import make_secret_key
    if not isinstance(table_no, int) or table_no <= 0:
        raise ValueError("เลขโต๊ะต้องเป็นจำนวนเต็มมากกว่า 0")
    with db.transaction() as conn:
        if db.query_one("SELECT 1 FROM tables WHERE table_no = ?", (table_no,), conn=conn):
            raise ValueError(f"มีโต๊ะ {table_no} อยู่แล้ว")
        tid = db.execute(
            "INSERT INTO tables (table_no, name, secret_key, active, created_at) VALUES (?, ?, ?, 1, ?)",
            (table_no, (name or "").strip() or f"โต๊ะ {table_no}", make_secret_key(), db.now_str()), conn=conn)
        log_service.log_action("table_add", f"เพิ่มโต๊ะ {table_no}", user_id=user_id,
                               ref_type="table", ref_id=tid, conn=conn)
    return get_table(tid)


def update_table(table_id: int, name: str | None = None, active: bool | None = None,
                 user_id: int | None = None) -> dict:
    """แก้ชื่อ/เปิด-ปิดใช้โต๊ะ ; ValueError ถ้าไม่พบ หรือจะปิดโต๊ะที่ยังมีรอบค้าง"""
    with db.transaction() as conn:
        t = db.query_one("SELECT * FROM tables WHERE id = ?", (table_id,), conn=conn)
        if t is None:
            raise ValueError("ไม่พบโต๊ะ")
        new_active = (1 if active else 0) if active is not None else t["active"]
        if t["active"] and not new_active and _active_session_row(table_id, conn):
            raise ValueError("โต๊ะนี้ยังมีลูกค้า/รอยืนยันอยู่ ปิดการใช้งานไม่ได้")
        new_name = (name or "").strip() or t["name"]
        db.execute("UPDATE tables SET name = ?, active = ? WHERE id = ?", (new_name, new_active, table_id), conn=conn)
        log_service.log_action("table_update", f"แก้โต๊ะ {t['table_no']}: ชื่อ={new_name}, ใช้งาน={new_active}",
                               user_id=user_id, ref_type="table", ref_id=table_id, conn=conn)
    return get_table(table_id)


def regenerate_secret(table_id: int, user_id: int | None = None) -> dict:
    """สุ่มรหัสลับใหม่ (QR เก่าใช้ไม่ได้ ต้องพิมพ์ใหม่) ; ValueError ถ้าไม่พบโต๊ะ"""
    from database.seed import make_secret_key
    with db.transaction() as conn:
        n = db.execute_rowcount("UPDATE tables SET secret_key = ? WHERE id = ?",
                                (make_secret_key(), table_id), conn=conn)
        if n == 0:
            raise ValueError("ไม่พบโต๊ะ")
        log_service.log_action("table_secret_reset", "เปลี่ยนรหัสลับ QR ของโต๊ะ", user_id=user_id,
                               ref_type="table", ref_id=table_id, conn=conn)
    return get_table(table_id)


# ---------------------------------------------------------------- อ่านรอบ

def _active_session_row(table_id: int, conn=None):
    return db.query_one(
        f"SELECT * FROM table_sessions WHERE table_id = ? AND status IN ({_ACTIVE_MARKS}) ORDER BY id DESC LIMIT 1",
        (table_id, *ACTIVE_STATUSES), conn=conn)


def get_session(session_id: int) -> dict | None:
    """รอบตาม id (ทุกสถานะ) -> dict หรือ None"""
    row = db.query_one("SELECT * FROM table_sessions WHERE id = ?", (session_id,))
    return dict(row) if row else None


def get_active_session(table_id: int) -> dict | None:
    """รอบที่ยังไม่จบของโต๊ะ (pending/open/awaiting_payment) -> dict หรือ None (= โต๊ะว่าง)"""
    row = _active_session_row(table_id)
    return dict(row) if row else None


def is_session_active(session_id: int) -> bool:
    """รอบนี้ยังไม่จบ (ยังเข้าใช้ได้) หรือไม่"""
    s = get_session(session_id)
    return bool(s) and s["status"] in ACTIVE_STATUSES


def list_pending_sessions() -> list[dict]:
    """รอบที่รอพนักงานยืนยัน เรียงเก่าสุดก่อน (+ table_no, table_name)"""
    rows = db.query_all(
        "SELECT s.*, t.table_no, t.name AS table_name FROM table_sessions s "
        "JOIN tables t ON t.id = s.table_id WHERE s.status = 'pending' ORDER BY s.id")
    return [dict(r) for r in rows]


def list_tables_with_status() -> list[dict]:
    """โต๊ะที่เปิดใช้งานทุกโต๊ะ + สถานะปัจจุบัน สำหรับหน้าโต๊ะของพนักงาน
    แต่ละ dict = ฟิลด์ของโต๊ะ (ไม่รวม secret_key) + status ('free' หรือสถานะรอบ) + status_th
    + session_id, started_at, last_activity (None ถ้าว่าง)"""
    result = []
    for t in list_tables():
        s = get_active_session(t["id"])
        status = s["status"] if s else config.TABLE_STATUS_FREE
        t.pop("secret_key", None)
        t.update(status=status, status_th=config.SESSION_STATUS_TH[status],
                 session_id=s["id"] if s else None,
                 started_at=s["started_at"] if s else None,
                 last_activity=s["last_activity"] if s else None)
        result.append(t)
    return result


# ---------------------------------------------------------------- เปลี่ยนสถานะ

def start_session(table_id: int, device_id: str | None = None, device_info: str | None = None) -> dict:
    """ลูกค้าสแกนผ่าน -> สร้างรอบ pending ; ถ้าโต๊ะมีรอบค้างอยู่แล้วและเป็นเครื่องเดิม (device_id ตรงกัน)
    คืนรอบเดิม ; ถ้าเครื่องอื่น -> ValueError ; ValueError ถ้าโต๊ะไม่พบ/ปิดใช้งาน
    (ไม่เช็คร้านเปิด/รหัสลับ — ใช้ qr_service.resolve_scan แทนสำหรับการสแกน)"""
    with db.transaction() as conn:
        t = db.query_one("SELECT * FROM tables WHERE id = ?", (table_id,), conn=conn)
        if t is None or not t["active"]:
            raise ValueError("ไม่พบโต๊ะนี้")
        existing = _active_session_row(table_id, conn)
        if existing:
            if device_id and existing["device_id"] == device_id:
                return dict(existing)
            raise ValueError("โต๊ะนี้มีลูกค้าใช้งานอยู่แล้ว")
        now = db.now_str()
        sid = db.execute(
            "INSERT INTO table_sessions (table_id, status, started_at, last_activity, device_id, device_info) "
            "VALUES (?, 'pending', ?, ?, ?, ?)", (table_id, now, now, device_id, device_info), conn=conn)
        log_service.log_action("session_start", f"ลูกค้าสแกนโต๊ะ {t['table_no']} รอยืนยัน",
                               actor="ลูกค้า", ref_type="table_session", ref_id=sid, conn=conn)
    return get_session(sid)


def _load_for_change(conn, session_id: int, allowed: tuple[str, ...], action_th: str):
    s = db.query_one("SELECT s.*, t.table_no FROM table_sessions s JOIN tables t ON t.id = s.table_id "
                     "WHERE s.id = ?", (session_id,), conn=conn)
    if s is None:
        raise ValueError("ไม่พบรอบของโต๊ะนี้")
    if s["status"] not in allowed:
        raise ValueError(f"{action_th}ไม่ได้ — สถานะปัจจุบันคือ "
                         f"{config.SESSION_STATUS_TH.get(s['status'], s['status'])}")
    return s


def confirm_session(session_id: int, user_id: int) -> dict:
    """พนักงานกดยืนยัน: pending -> open (สั่งได้)"""
    with db.transaction() as conn:
        s = _load_for_change(conn, session_id, (config.SESSION_PENDING,), "ยืนยันโต๊ะ")
        now = db.now_str()
        db.execute("UPDATE table_sessions SET status='open', confirmed_at=?, confirmed_by=?, last_activity=? "
                   "WHERE id=?", (now, user_id, now, session_id), conn=conn)
        log_service.log_action("session_confirm", f"ยืนยันโต๊ะ {s['table_no']}", user_id=user_id,
                               ref_type="table_session", ref_id=session_id, conn=conn)
    return get_session(session_id)


def cancel_session(session_id: int, cancelled_by: str = "staff", user_id: int | None = None,
                   reason: str | None = None) -> dict:
    """ยกเลิกรอบ -> cancelled (ต้องสแกนใหม่)
    cancelled_by: 'staff' (จาก pending/open) หรือ 'customer' (เฉพาะ pending)
    ValueError ถ้าสถานะไม่เหมาะ หรือรอบ open มีรายการชั่ง/สั่งที่ยังไม่ยกเลิกแล้ว (ให้ยกเลิกรายการ/เช็คเอาท์แทน)"""
    if cancelled_by not in ("staff", "customer"):
        raise ValueError("ผู้ยกเลิกไม่ถูกต้อง")
    allowed = (config.SESSION_PENDING,) if cancelled_by == "customer" else (config.SESSION_PENDING, config.SESSION_OPEN)
    with db.transaction() as conn:
        s = _load_for_change(conn, session_id, allowed, "ยกเลิกโต๊ะ")
        if s["status"] == config.SESSION_OPEN:
            busy = db.query_one(
                "SELECT (SELECT COUNT(*) FROM weigh_entries WHERE session_id=? AND status='active') + "
                "(SELECT COUNT(*) FROM order_items oi JOIN orders o ON o.id=oi.order_id "
                " WHERE o.session_id=? AND oi.status!='cancelled') AS c", (session_id, session_id), conn=conn)["c"]
            if busy:
                raise ValueError("โต๊ะนี้มีรายการชั่ง/สั่งแล้ว ยกเลิกโต๊ะไม่ได้ — ให้ยกเลิกรายการหรือเช็คเอาท์แทน")
        now = db.now_str()
        db.execute("UPDATE table_sessions SET status='cancelled', closed_at=?, last_activity=?, "
                   "cancel_reason=?, cancelled_by=? WHERE id=?", (now, now, reason, cancelled_by, session_id), conn=conn)
        who = "ลูกค้า" if cancelled_by == "customer" else "พนักงาน"
        log_service.log_action("session_cancel",
                               f"{who}ยกเลิกโต๊ะ {s['table_no']}" + (f" เหตุผล: {reason}" if reason else ""),
                               user_id=user_id, actor="ลูกค้า" if cancelled_by == "customer" else None,
                               ref_type="table_session", ref_id=session_id, conn=conn)
    return get_session(session_id)


def mark_awaiting_payment(session_id: int, user_id: int | None = None) -> dict:
    """open -> awaiting_payment (เริ่มเช็คเอาท์/ลูกค้าขอเช็คบิล)"""
    with db.transaction() as conn:
        s = _load_for_change(conn, session_id, (config.SESSION_OPEN,), "เรียกเช็คบิล")
        db.execute("UPDATE table_sessions SET status='awaiting_payment', last_activity=? WHERE id=?",
                   (db.now_str(), session_id), conn=conn)
        log_service.log_action("session_awaiting_payment", f"โต๊ะ {s['table_no']} รอชำระเงิน",
                               user_id=user_id, ref_type="table_session", ref_id=session_id, conn=conn)
    return get_session(session_id)


def close_session(session_id: int, user_id: int | None = None, conn=None) -> dict:
    """awaiting_payment -> closed (หลังชำระเงิน ; checkout_service เรียก) — ลูกค้าต้องสแกนใหม่
    ส่ง conn ได้ถ้าเรียกภายใน transaction ของ checkout"""
    def _do(c):
        s = _load_for_change(c, session_id, (config.SESSION_AWAITING_PAYMENT,), "ปิดโต๊ะ")
        now = db.now_str()
        db.execute("UPDATE table_sessions SET status='closed', closed_at=?, last_activity=? WHERE id=?",
                   (now, now, session_id), conn=c)
        log_service.log_action("session_close", f"ปิดโต๊ะ {s['table_no']} (ชำระแล้ว)", user_id=user_id,
                               ref_type="table_session", ref_id=session_id, conn=c)
    if conn is not None:
        _do(conn)
    else:
        with db.transaction() as c:
            _do(c)
    return get_session(session_id)


def touch_session(session_id: int, conn=None) -> None:
    """อัปเดต last_activity เป็นตอนนี้ (order/weigh service เรียกเมื่อมีความเคลื่อนไหว)"""
    db.execute("UPDATE table_sessions SET last_activity = ? WHERE id = ?", (db.now_str(), session_id), conn=conn)
