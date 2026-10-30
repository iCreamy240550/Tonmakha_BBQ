"""services/notice_service.py — ข้อความแจ้งลูกค้า (ตาราง customer_notices) ที่หน้าเว็บมือถือจะดึงไปแสดง

kind ที่ใช้: 'sold_out' (เมนูหมด), 'item_cancelled' (ยกเลิกรายการ), 'staff_message' (พนักงานพิมพ์ส่ง), 'info'
ส่ง conn=conn ได้ เมื่อเรียกภายใน transaction ของผู้เรียก
"""
from database import db
from services import log_service


def add_notice(session_id: int, kind: str, message: str, conn=None) -> int:
    """เพิ่มข้อความถึงลูกค้าของรอบนี้ -> id"""
    return db.execute(
        "INSERT INTO customer_notices (session_id, kind, message, created_at) VALUES (?, ?, ?, ?)",
        (session_id, kind, message, db.now_str()), conn=conn)


def broadcast_open_sessions(kind: str, message: str, conn=None) -> int:
    """ส่งข้อความถึงทุกโต๊ะที่กำลังใช้งาน (สถานะ open) -> จำนวนโต๊ะที่ส่ง"""
    rows = db.query_all("SELECT id FROM table_sessions WHERE status = 'open'", conn=conn)
    for r in rows:
        add_notice(r["id"], kind, message, conn=conn)
    return len(rows)


def send_message(session_id: int, message: str, user_id: int | None = None) -> int:
    """พนักงานพิมพ์ข้อความส่งถึงโต๊ะ (log ให้) -> id ; ValueError ถ้าข้อความว่าง/ไม่พบรอบ"""
    message = (message or "").strip()
    if not message:
        raise ValueError("กรุณาพิมพ์ข้อความ")
    with db.transaction() as conn:
        if db.query_one("SELECT 1 FROM table_sessions WHERE id = ?", (session_id,), conn=conn) is None:
            raise ValueError("ไม่พบรอบของโต๊ะนี้")
        nid = add_notice(session_id, "staff_message", message, conn=conn)
        log_service.log_action("notice_send", f"ส่งข้อความถึงโต๊ะ: {message}", user_id=user_id,
                               ref_type="table_session", ref_id=session_id, conn=conn)
    return nid


def list_notices(session_id: int, limit: int = 50) -> list[dict]:
    """ข้อความของรอบ ใหม่สุดก่อน (อ่านแล้วและยังไม่อ่าน)"""
    rows = db.query_all("SELECT * FROM customer_notices WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                        (session_id, limit))
    return [dict(r) for r in rows]


def list_unread(session_id: int) -> list[dict]:
    """ข้อความที่ลูกค้ายังไม่ได้อ่าน เก่าสุดก่อน"""
    rows = db.query_all("SELECT * FROM customer_notices WHERE session_id = ? AND read_at IS NULL ORDER BY id",
                        (session_id,))
    return [dict(r) for r in rows]


def unread_count(session_id: int) -> int:
    """จำนวนข้อความที่ยังไม่อ่าน"""
    return db.query_one("SELECT COUNT(*) AS c FROM customer_notices WHERE session_id = ? AND read_at IS NULL",
                        (session_id,))["c"]


def mark_read(notice_id: int) -> None:
    """ทำเครื่องหมายว่าอ่านแล้ว 1 ข้อความ"""
    db.execute("UPDATE customer_notices SET read_at = ? WHERE id = ? AND read_at IS NULL",
               (db.now_str(), notice_id))


def mark_all_read(session_id: int) -> int:
    """ทำเครื่องหมายว่าอ่านแล้วทั้งหมดของรอบ -> จำนวนที่เปลี่ยน"""
    return db.execute_rowcount("UPDATE customer_notices SET read_at = ? WHERE session_id = ? AND read_at IS NULL",
                               (db.now_str(), session_id))
