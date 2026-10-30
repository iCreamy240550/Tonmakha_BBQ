"""services/log_service.py — บันทึกกิจกรรมสำคัญลงตาราง activity_log

กติกา: ทุกการเปลี่ยนแปลงสำคัญ (ยกเลิก, แก้ราคา, ยกเลิกรายการ, เปลี่ยนสถานะ ฯลฯ) ต้องเรียก log_action
ถ้ากำลังอยู่ใน transaction ให้ส่ง conn=conn เพื่อให้ log สำเร็จ/ล้มเหลวพร้อมการเปลี่ยนแปลงนั้น
"""
from database import db


def log_action(action: str, detail: str | None = None, user_id: int | None = None,
               actor: str | None = None, ref_type: str | None = None,
               ref_id: int | None = None, conn=None) -> int:
    """บันทึก 1 รายการ -> id ของ log
    action: รหัสสั้น ๆ ภาษาอังกฤษ เช่น 'session_confirm'; detail: คำอธิบายภาษาไทย
    user_id: พนักงาน/เจ้าของที่ทำ (None ถ้าเป็นลูกค้า/ระบบ); actor: ชื่อผู้ทำเป็นข้อความ เช่น 'ลูกค้า', 'ระบบ'
    ref_type/ref_id: อ้างอิงข้อมูลที่เกี่ยวข้อง เช่น ('table_session', 12)"""
    return db.execute(
        "INSERT INTO activity_log (user_id, actor, action, detail, ref_type, ref_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, actor, action, detail, ref_type, ref_id, db.now_str()),
        conn=conn,
    )


def _where(action, user_id, date_from, date_to):
    clauses, params = [], []
    if action:
        clauses.append("l.action = ?")
        params.append(action)
    if user_id is not None:
        clauses.append("l.user_id = ?")
        params.append(user_id)
    if date_from:
        clauses.append("l.created_at >= ?")
        params.append(f"{date_from} 00:00:00")
    if date_to:
        clauses.append("l.created_at <= ?")
        params.append(f"{date_to} 23:59:59")
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", tuple(params)


def get_logs(limit: int = 200, offset: int = 0, action: str | None = None,
             user_id: int | None = None, date_from: str | None = None,
             date_to: str | None = None) -> list[dict]:
    """ดึง log ใหม่สุดก่อน -> list ของ dict (id, user_id, user_name, actor, action, detail,
    ref_type, ref_id, created_at); date_from/date_to รูปแบบ 'YYYY-MM-DD'"""
    where, params = _where(action, user_id, date_from, date_to)
    rows = db.query_all(
        "SELECT l.*, u.display_name AS user_name FROM activity_log l "
        "LEFT JOIN users u ON u.id = l.user_id" + where +
        " ORDER BY l.id DESC LIMIT ? OFFSET ?",
        params + (limit, offset),
    )
    return [dict(r) for r in rows]


def count_logs(action: str | None = None, user_id: int | None = None,
               date_from: str | None = None, date_to: str | None = None) -> int:
    """จำนวน log ตามตัวกรองเดียวกับ get_logs"""
    where, params = _where(action, user_id, date_from, date_to)
    return db.query_one("SELECT COUNT(*) AS c FROM activity_log l" + where, params)["c"]
