"""services/shop_service.py — เปิด/ปิดร้าน (ตาราง shop_status แถวเดียว)

ร้านปิด = ลูกค้าสแกน QR แล้วขึ้น "ร้านปิดอยู่" และเข้าไม่ได้
"""
from database import db
from services import log_service

_ACTIVE = ("pending", "open", "awaiting_payment")


def get_status() -> dict:
    """-> {'is_open': bool, 'changed_at': str, 'changed_by': int|None}"""
    row = db.query_one("SELECT * FROM shop_status WHERE id = 1")
    if row is None:  # ยังไม่ได้ create_all()
        return {"is_open": False, "changed_at": None, "changed_by": None}
    return {"is_open": bool(row["is_open"]), "changed_at": row["changed_at"], "changed_by": row["changed_by"]}


def is_open() -> bool:
    """ร้านเปิดอยู่หรือไม่"""
    return get_status()["is_open"]


def active_session_count() -> int:
    """จำนวนโต๊ะที่ยังมีรอบใช้งานค้างอยู่ (pending/open/awaiting_payment)"""
    marks = ",".join("?" * len(_ACTIVE))
    return db.query_one(f"SELECT COUNT(*) AS c FROM table_sessions WHERE status IN ({marks})", _ACTIVE)["c"]


def _set(is_open_flag: bool, user_id: int | None, action: str, detail: str) -> None:
    with db.transaction() as conn:
        db.execute("UPDATE shop_status SET is_open = ?, changed_at = ?, changed_by = ? WHERE id = 1",
                   (1 if is_open_flag else 0, db.now_str(), user_id), conn=conn)
        log_service.log_action(action, detail, user_id=user_id, ref_type="shop", conn=conn)


def open_shop(user_id: int | None = None) -> None:
    """เปิดร้าน (เปิดซ้ำได้ ไม่ error) + log"""
    if is_open():
        return
    _set(True, user_id, "shop_open", "เปิดร้าน")


def close_shop(user_id: int | None = None, force: bool = False) -> None:
    """ปิดร้าน + log ; ValueError ถ้ายังมีโต๊ะค้างอยู่ (ยกเว้น force=True)"""
    if not is_open():
        return
    n = active_session_count()
    if n and not force:
        raise ValueError(f"ยังมี {n} โต๊ะที่ใช้งาน/รอยืนยัน/รอชำระอยู่ — จัดการให้เสร็จก่อนปิดร้าน")
    detail = "ปิดร้าน" + (f" (บังคับ ทั้งที่ยังค้าง {n} โต๊ะ)" if n else "")
    _set(False, user_id, "shop_close", detail)
