"""services/auth_service.py — ล็อกอิน, จัดการผู้ใช้ (พนักงาน/เจ้าของ), สิทธิ์

ผู้ใช้ที่คืนจากฟังก์ชันเป็น dict: id, username, display_name, role, active, created_at (ไม่มี password_hash)
ข้อผิดพลาดตามกติกา (ชื่อซ้ำ, รหัสสั้นเกิน ฯลฯ) -> raise ValueError พร้อมข้อความภาษาไทย ให้ UI แสดงได้เลย
"""
import config
from database import db, seed
from services import log_service

_PUBLIC_COLS = "id, username, display_name, role, active, created_at"


def hash_password(password: str) -> str:
    """แฮชรหัสผ่านด้วย bcrypt -> ข้อความแฮช"""
    bcrypt = seed._get_bcrypt()
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """ตรวจรหัสผ่านกับแฮช -> bool (แฮชเสียหายถือว่าไม่ผ่าน)"""
    bcrypt = seed._get_bcrypt()
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def login(username: str, password: str) -> dict | None:
    """ล็อกอิน -> dict ผู้ใช้ ถ้าสำเร็จ ; None ถ้าชื่อ/รหัสผิด หรือบัญชีถูกปิด (log ทั้งสำเร็จและล้มเหลว)"""
    username = (username or "").strip()
    row = db.query_one("SELECT * FROM users WHERE username = ?", (username,))
    if row is None or not row["active"] or not verify_password(password or "", row["password_hash"]):
        log_service.log_action("login_fail", f"ล็อกอินไม่สำเร็จ: {username}", actor="ระบบ",
                               ref_type="user", ref_id=row["id"] if row else None)
        return None
    log_service.log_action("login", f"{row['display_name']} เข้าสู่ระบบ", user_id=row["id"])
    return get_user(row["id"])


def get_user(user_id: int) -> dict | None:
    """ผู้ใช้ตาม id -> dict หรือ None"""
    row = db.query_one(f"SELECT {_PUBLIC_COLS} FROM users WHERE id = ?", (user_id,))
    return dict(row) if row else None


def list_users(include_inactive: bool = True) -> list[dict]:
    """รายชื่อผู้ใช้ทั้งหมด เรียงตาม id"""
    sql = f"SELECT {_PUBLIC_COLS} FROM users"
    if not include_inactive:
        sql += " WHERE active = 1"
    return [dict(r) for r in db.query_all(sql + " ORDER BY id")]


def is_owner(user: dict | None) -> bool:
    """user เป็นเจ้าของหรือไม่"""
    return bool(user) and user.get("role") == config.ROLE_OWNER


def has_permission(user: dict | None, required_role: str) -> bool:
    """เจ้าของทำได้ทุกอย่าง; พนักงานทำได้เฉพาะงาน required_role='staff'"""
    if not user or not user.get("active", True):
        return False
    return is_owner(user) or user.get("role") == required_role


def _check_password(password: str) -> None:
    if len(password or "") < config.MIN_PASSWORD_LENGTH:
        raise ValueError(f"รหัสผ่านต้องยาวอย่างน้อย {config.MIN_PASSWORD_LENGTH} ตัวอักษร")


def _active_owner_count(conn, exclude_id: int | None = None) -> int:
    sql = "SELECT COUNT(*) AS c FROM users WHERE role = 'owner' AND active = 1"
    params: tuple = ()
    if exclude_id is not None:
        sql += " AND id != ?"
        params = (exclude_id,)
    return db.query_one(sql, params, conn=conn)["c"]


def create_user(username: str, password: str, display_name: str, role: str,
                by_user_id: int | None = None) -> dict:
    """สร้างผู้ใช้ใหม่ -> dict ; ValueError ถ้าชื่อว่าง/ซ้ำ/role ผิด/รหัสสั้น"""
    username = (username or "").strip()
    display_name = (display_name or "").strip() or username
    if not username:
        raise ValueError("กรุณากรอกชื่อผู้ใช้")
    if role not in (config.ROLE_STAFF, config.ROLE_OWNER):
        raise ValueError("สิทธิ์ผู้ใช้ไม่ถูกต้อง")
    _check_password(password)
    with db.transaction() as conn:
        if db.query_one("SELECT 1 FROM users WHERE username = ?", (username,), conn=conn):
            raise ValueError("ชื่อผู้ใช้นี้ถูกใช้แล้ว")
        uid = db.execute(
            "INSERT INTO users (username, password_hash, display_name, role, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (username, hash_password(password), display_name, role, db.now_str()), conn=conn)
        log_service.log_action("user_create", f"สร้างผู้ใช้ {username} ({role})",
                               user_id=by_user_id, ref_type="user", ref_id=uid, conn=conn)
    return get_user(uid)


def update_user(user_id: int, display_name: str | None = None, role: str | None = None,
                active: bool | None = None, by_user_id: int | None = None) -> dict:
    """แก้ชื่อแสดง/สิทธิ์/เปิด-ปิดบัญชี (ส่งเฉพาะที่จะแก้) -> dict ใหม่
    ValueError ถ้าไม่พบผู้ใช้ หรือจะทำให้ไม่เหลือเจ้าของที่ใช้งานได้"""
    with db.transaction() as conn:
        row = db.query_one("SELECT * FROM users WHERE id = ?", (user_id,), conn=conn)
        if row is None:
            raise ValueError("ไม่พบผู้ใช้")
        new_role = role if role is not None else row["role"]
        new_active = (1 if active else 0) if active is not None else row["active"]
        if new_role not in (config.ROLE_STAFF, config.ROLE_OWNER):
            raise ValueError("สิทธิ์ผู้ใช้ไม่ถูกต้อง")
        loses_owner = row["role"] == "owner" and row["active"] and (new_role != "owner" or not new_active)
        if loses_owner and _active_owner_count(conn, exclude_id=user_id) == 0:
            raise ValueError("ต้องมีเจ้าของที่ใช้งานได้อย่างน้อย 1 คน")
        new_name = (display_name or "").strip() or row["display_name"]
        db.execute("UPDATE users SET display_name = ?, role = ?, active = ? WHERE id = ?",
                   (new_name, new_role, new_active, user_id), conn=conn)
        log_service.log_action("user_update",
                               f"แก้ผู้ใช้ {row['username']}: ชื่อ={new_name}, สิทธิ์={new_role}, ใช้งาน={new_active}",
                               user_id=by_user_id, ref_type="user", ref_id=user_id, conn=conn)
    return get_user(user_id)


def change_password(user_id: int, new_password: str, by_user_id: int | None = None) -> None:
    """เปลี่ยนรหัสผ่าน ; ValueError ถ้ารหัสสั้นเกิน/ไม่พบผู้ใช้"""
    _check_password(new_password)
    with db.transaction() as conn:
        n = db.execute_rowcount("UPDATE users SET password_hash = ? WHERE id = ?",
                                (hash_password(new_password), user_id), conn=conn)
        if n == 0:
            raise ValueError("ไม่พบผู้ใช้")
        log_service.log_action("password_change", "เปลี่ยนรหัสผ่าน", user_id=by_user_id,
                               ref_type="user", ref_id=user_id, conn=conn)
