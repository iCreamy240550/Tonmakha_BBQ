"""database/db.py — ตัวเชื่อมฐานข้อมูล SQLite (โหมด WAL ใช้ร่วมกัน 2 โปรเซส: PC + เว็บมือถือ)

หลักการ: เปิดการเชื่อมต่อใหม่ต่อ 1 การทำงาน (เปิดถูกมากใน SQLite) จึงปลอดภัยกับหลายเธรด
(Tk เธรดหลัก, NiceGUI, ตัวตรวจแจ้งเตือน) ไม่ต้องแชร์ connection ข้ามเธรด

UI ห้ามเรียกโมดูลนี้ตรง ๆ — ให้ผ่าน services/ เท่านั้น
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import config

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_str() -> str:
    """เวลาปัจจุบัน (เวลาเครื่อง) เป็นข้อความ 'YYYY-MM-DD HH:MM:SS'"""
    return datetime.now().strftime(TIME_FORMAT)


def parse_time(text: str) -> datetime:
    """แปลงข้อความเวลาในฐานข้อมูลกลับเป็น datetime"""
    return datetime.strptime(text, TIME_FORMAT)


def _ensure_filesystem_compatible(db_path: Path) -> None:
    """หากไฟล์ SQLite ค้างโหมด WAL (byte 18,19 = 2) บนระบบไฟล์จำลองที่ไม่รองรับ mmap/shm (เช่น 9p/network share)
    ให้สลับ header เป็น rollback journal (1) อัตโนมัติเพื่อป้องกัน disk I/O error"""
    if not db_path.exists() or db_path.stat().st_size < 100:
        return
    try:
        c = sqlite3.connect(str(db_path), timeout=config.DB_TIMEOUT_SECONDS)
        c.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
        c.close()
    except sqlite3.OperationalError:
        try:
            data = bytearray(db_path.read_bytes())
            if len(data) >= 20 and (data[18] == 2 or data[19] == 2):
                data[18] = 1
                data[19] = 1
                db_path.write_bytes(bytes(data))
        except OSError:
            pass


def get_connection() -> sqlite3.Connection:
    """เปิด connection ใหม่ (WAL, foreign_keys เปิด, แถวเข้าถึงด้วยชื่อคอลัมน์ได้)
    ผู้เรียกต้อง close() เอง — แนะนำให้ใช้ transaction() แทน"""
    db_path = Path(config.DB_PATH)
    _ensure_filesystem_compatible(db_path)
    conn = sqlite3.connect(str(db_path), timeout=config.DB_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={int(config.DB_TIMEOUT_SECONDS * 1000)}")
    return conn


@contextmanager
def transaction():
    """ใช้เป็น `with transaction() as conn:` — สำเร็จ = commit, error = rollback, ปิดให้อัตโนมัติ
    ใช้เมื่อต้องทำหลายคำสั่งให้สำเร็จพร้อมกัน (ส่ง conn ต่อให้ helper ด้านล่าง)"""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(sql: str, params: tuple = (), conn: sqlite3.Connection | None = None) -> list[sqlite3.Row]:
    """SELECT หลายแถว -> list ของ Row (ว่าง = [])"""
    if conn is not None:
        return conn.execute(sql, params).fetchall()
    c = get_connection()
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def query_one(sql: str, params: tuple = (), conn: sqlite3.Connection | None = None) -> sqlite3.Row | None:
    """SELECT แถวเดียว -> Row หรือ None"""
    if conn is not None:
        return conn.execute(sql, params).fetchone()
    c = get_connection()
    try:
        return c.execute(sql, params).fetchone()
    finally:
        c.close()


def execute(sql: str, params: tuple = (), conn: sqlite3.Connection | None = None) -> int:
    """INSERT/UPDATE/DELETE -> คืน lastrowid (INSERT) ; ถ้าไม่ส่ง conn จะ commit ให้เอง"""
    if conn is not None:
        return conn.execute(sql, params).lastrowid
    with transaction() as c:
        return c.execute(sql, params).lastrowid


def execute_rowcount(sql: str, params: tuple = (), conn: sqlite3.Connection | None = None) -> int:
    """เหมือน execute แต่คืนจำนวนแถวที่ถูกแก้ (ใช้เช็คว่า UPDATE โดนจริงไหม)"""
    if conn is not None:
        return conn.execute(sql, params).rowcount
    with transaction() as c:
        return c.execute(sql, params).rowcount


def executemany(sql: str, rows: list[tuple], conn: sqlite3.Connection | None = None) -> None:
    """รันคำสั่งเดียวกันหลายชุดพารามิเตอร์"""
    if conn is not None:
        conn.executemany(sql, rows)
        return
    with transaction() as c:
        c.executemany(sql, rows)
