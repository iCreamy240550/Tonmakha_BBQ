"""database/seed.py — ข้อมูลเริ่มต้น (โต๊ะ, เมนู, สต๊อก, เจ้าของ, พนักงานตัวอย่าง, ค่าตั้งค่า)

รันตรง ๆ:  python -m database.seed
รันซ้ำได้อย่างปลอดภัย: ส่วนไหนมีข้อมูลอยู่แล้วจะข้าม ไม่เขียนทับ

บัญชีตัวอย่าง (ต้องเปลี่ยนรหัสผ่านก่อนใช้งานจริง!):
    เจ้าของ  owner  / owner1234
    พนักงาน  staff1 / staff1234
"""
from pathlib import Path
import secrets
import sys
import types
import warnings

import config
from database import db, schema

SAMPLE_USERS = [
    # (username, รหัสผ่าน, ชื่อแสดง, role)
    ("owner", "owner1234", "เจ้าของร้าน", config.ROLE_OWNER),
    ("staff1", "staff1234", "พนักงาน 1", config.ROLE_STAFF),
]

# สต๊อก: (ชื่อ, หน่วย, จำนวนตั้งต้น, จุดเตือนขั้นต่ำ)  — เนื้อสัตว์นับเป็น กก. ส่วนของอื่นนับเป็นชิ้น/ขวด
SAMPLE_STOCK = [
    ("หมูสามชั้น", "กก.", 20, 3),
    ("หมูสไลซ์", "กก.", 20, 3),
    ("เนื้อวัวสไลซ์", "กก.", 10, 2),
    ("น้ำเปล่า", "ขวด", 48, 12),
    ("โค้ก", "ขวด", 48, 12),
    ("เบียร์ช้าง", "ขวด", 72, 24),
]

# เมนู: หมวด -> [(ชื่อ, ประเภท, ราคา(ต่อกก. ถ้าชั่ง / ต่อหน่วย ถ้าปกติ), ชื่อสต๊อกที่ผูก หรือ None)]
SAMPLE_MENU = {
    "หมูกระทะชั่งกิโล": [
        ("หมูสามชั้น", config.MENU_TYPE_WEIGHED, config.DEFAULT_WEIGH_PRICE_PER_KG, "หมูสามชั้น"),
        ("หมูสไลซ์", config.MENU_TYPE_WEIGHED, config.DEFAULT_WEIGH_PRICE_PER_KG, "หมูสไลซ์"),
        ("เนื้อวัวสไลซ์", config.MENU_TYPE_WEIGHED, config.DEFAULT_WEIGH_PRICE_PER_KG, "เนื้อวัวสไลซ์"),
    ],
    "ผักและของทานเล่น": [
        ("ผักรวม", config.MENU_TYPE_NORMAL, 40, None),
        ("ไข่ไก่", config.MENU_TYPE_NORMAL, 10, None),
        ("วุ้นเส้น", config.MENU_TYPE_NORMAL, 20, None),
    ],
    "เครื่องดื่ม": [
        ("น้ำเปล่า", config.MENU_TYPE_NORMAL, 15, "น้ำเปล่า"),
        ("โค้ก", config.MENU_TYPE_NORMAL, 20, "โค้ก"),
        ("เบียร์ช้าง", config.MENU_TYPE_NORMAL, 70, "เบียร์ช้าง"),
    ],
}


def _get_bcrypt():
    try:
        import bcrypt
        return bcrypt
    except ImportError:
        if Path("/tmp/vm_vendor").exists() and "/tmp/vm_vendor" not in sys.path:
            sys.path.append("/tmp/vm_vendor")
        try:
            import bcrypt
            return bcrypt
        except ImportError:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                import crypt as _std_crypt

            class _CompatBcryptModule(types.ModuleType):
                @staticmethod
                def gensalt(rounds: int = 12) -> bytes:
                    if hasattr(_std_crypt, "METHOD_BLOWFISH"):
                        s = _std_crypt.mksalt(_std_crypt.METHOD_BLOWFISH)
                    else:
                        s = "$2b$12$lTdudslGfF0exQM28dUaN."
                    return s.encode("utf-8")

                @staticmethod
                def hashpw(password: bytes, salt: bytes) -> bytes:
                    pw_str = password.decode("utf-8") if isinstance(password, (bytes, bytearray)) else str(password)
                    salt_str = salt.decode("utf-8") if isinstance(salt, (bytes, bytearray)) else str(salt)
                    hashed = _std_crypt.crypt(pw_str, salt_str)
                    if not hashed or not hashed.startswith("$2"):
                        raise ValueError("Invalid bcrypt salt or hash")
                    return hashed.encode("utf-8")

                @staticmethod
                def checkpw(password: bytes, hashed_password: bytes) -> bool:
                    pw_str = password.decode("utf-8") if isinstance(password, (bytes, bytearray)) else str(password)
                    h_str = hashed_password.decode("utf-8") if isinstance(hashed_password, (bytes, bytearray)) else str(hashed_password)
                    if not h_str.startswith("$2"):
                        raise ValueError("Invalid hash")
                    return _std_crypt.crypt(pw_str, h_str) == h_str

            compat = _CompatBcryptModule("bcrypt")
            sys.modules["bcrypt"] = compat
            return compat


def hash_password(password: str) -> str:
    """แฮชรหัสผ่านด้วย bcrypt -> ข้อความแฮช (auth_service ใช้ bcrypt.checkpw ตรวจภายหลัง)"""
    bcrypt = _get_bcrypt()
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def make_secret_key() -> str:
    """รหัสลับสุ่มสำหรับ QR ของโต๊ะ (ตัวอักษร+ตัวเลข ยาว config.SECRET_KEY_LENGTH)"""
    return secrets.token_urlsafe(config.SECRET_KEY_LENGTH)[: config.SECRET_KEY_LENGTH]


def _is_empty(table: str, conn) -> bool:
    return db.query_one(f"SELECT 1 FROM {table} LIMIT 1", conn=conn) is None


def seed_settings(conn) -> int:
    """ใส่ค่าตั้งค่าเริ่มต้น (ไม่ทับค่าที่มีแล้ว) -> จำนวนที่เพิ่ม"""
    added = 0
    for key, value in config.DEFAULT_SETTINGS.items():
        cur = conn.execute(
            "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, str(value), db.now_str()),
        )
        added += cur.rowcount
    return added


def seed_users(conn) -> int:
    """สร้างเจ้าของ + พนักงานตัวอย่าง (เฉพาะเมื่อตาราง users ยังว่าง)"""
    if not _is_empty("users", conn):
        return 0
    for username, password, display_name, role in SAMPLE_USERS:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (username, hash_password(password), display_name, role, db.now_str()),
        )
    return len(SAMPLE_USERS)


def seed_tables(conn) -> int:
    """สร้างโต๊ะ 1..DEFAULT_TABLE_COUNT พร้อมรหัสลับ (เฉพาะเมื่อตาราง tables ยังว่าง)"""
    if not _is_empty("tables", conn):
        return 0
    for no in range(1, config.DEFAULT_TABLE_COUNT + 1):
        conn.execute(
            "INSERT INTO tables (table_no, name, secret_key, active, created_at) VALUES (?, ?, ?, 1, ?)",
            (no, f"โต๊ะ {no}", make_secret_key(), db.now_str()),
        )
    return config.DEFAULT_TABLE_COUNT


def seed_stock(conn) -> int:
    """สร้างรายการสต๊อกตัวอย่าง (เฉพาะเมื่อตาราง stock_items ยังว่าง)"""
    if not _is_empty("stock_items", conn):
        return 0
    for name, unit, qty, min_qty in SAMPLE_STOCK:
        conn.execute(
            "INSERT INTO stock_items (name, unit, quantity, min_quantity, active) VALUES (?, ?, ?, ?, 1)",
            (name, unit, qty, min_qty),
        )
    return len(SAMPLE_STOCK)


def seed_menu(conn) -> int:
    """สร้างหมวดและเมนูตัวอย่าง ผูกกับสต๊อกตามชื่อ (เฉพาะเมื่อตาราง menu_categories ยังว่าง)
    ต้องเรียกหลัง seed_stock"""
    if not _is_empty("menu_categories", conn):
        return 0
    count = 0
    for cat_order, (cat_name, items) in enumerate(SAMPLE_MENU.items(), start=1):
        cat_id = conn.execute(
            "INSERT INTO menu_categories (name, sort_order, active) VALUES (?, ?, 1)",
            (cat_name, cat_order),
        ).lastrowid
        for item_order, (name, item_type, price, stock_name) in enumerate(items, start=1):
            stock_id = None
            if stock_name:
                row = db.query_one("SELECT id FROM stock_items WHERE name = ?", (stock_name,), conn=conn)
                stock_id = row["id"] if row else None
            conn.execute(
                "INSERT INTO menu_items (category_id, name, item_type, price, is_sold_out, "
                "stock_item_id, sort_order, active) VALUES (?, ?, ?, ?, 0, ?, ?, 1)",
                (cat_id, name, item_type, price, stock_id, item_order),
            )
            count += 1
    return count


def seed_all() -> dict[str, int]:
    """สร้างตาราง (ถ้ายังไม่มี) แล้วใส่ข้อมูลเริ่มต้นทั้งหมดใน transaction เดียว
    -> dict จำนวนที่เพิ่มของแต่ละส่วน เช่น {'settings': 12, 'users': 2, ...}"""
    schema.create_all()
    with db.transaction() as conn:
        return {
            "settings": seed_settings(conn),
            "users": seed_users(conn),
            "tables": seed_tables(conn),
            "stock": seed_stock(conn),
            "menu": seed_menu(conn),
        }


if __name__ == "__main__":
    result = seed_all()
    print("seed เสร็จ:", result)
    print("บัญชีตัวอย่าง: owner/owner1234 , staff1/staff1234 (เปลี่ยนรหัสก่อนใช้งานจริง)")
