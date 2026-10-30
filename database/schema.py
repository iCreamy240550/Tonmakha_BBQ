"""database/schema.py — สร้าง 17 ตารางของระบบ พร้อมระบบ migration แบบ idempotent

รันตรง ๆ:  python -m database.schema          (สร้างตารางที่ยังไม่มี และอัปเกรดโครงสร้างเดิมอย่างปลอดภัย)
           python -m database.schema --reset  (ลบทุกตารางแล้วสร้างใหม่ — ข้อมูลหาย!)

หมายเหตุ:
- เวลาเก็บเป็นข้อความ 'YYYY-MM-DD HH:MM:SS' (เวลาเครื่อง)
- น้ำหนักเก็บเป็น "กรัม" (จำนวนเต็ม) เสมอ ; 1 ขีด = 100 กรัม
- เงินเก็บเป็นทศนิยม REAL หน่วยบาท
- "โต๊ะว่าง" ไม่ได้เก็บเป็นสถานะ แต่คือโต๊ะที่ไม่มี session สถานะ pending/open/awaiting_payment
"""
import sys

import config
from database import db

SCHEMA_VERSION = 2

# ลำดับสำคัญ: ตารางที่ถูกอ้างอิงต้องมาก่อน
TABLES_SQL: dict[str, str] = {
    "users": """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name  TEXT NOT NULL,
            role          TEXT NOT NULL CHECK (role IN ('staff','owner')),
            active        INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL
        )""",
    "settings": """
        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    "shop_status": """
        CREATE TABLE IF NOT EXISTS shop_status (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            is_open    INTEGER NOT NULL DEFAULT 0,
            changed_at TEXT NOT NULL,
            changed_by INTEGER REFERENCES users(id)
        )""",
    "tables": """
        CREATE TABLE IF NOT EXISTS tables (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            table_no   INTEGER NOT NULL UNIQUE,
            name       TEXT NOT NULL,
            secret_key TEXT NOT NULL,
            active     INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )""",
    "table_sessions": """
        CREATE TABLE IF NOT EXISTS table_sessions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id      INTEGER NOT NULL REFERENCES tables(id),
            status        TEXT NOT NULL CHECK (status IN
                          ('pending','open','awaiting_payment','closed','cancelled')),
            started_at    TEXT NOT NULL,
            confirmed_at  TEXT,
            confirmed_by  INTEGER REFERENCES users(id),
            closed_at     TEXT,
            last_activity TEXT NOT NULL,
            device_id     TEXT,
            device_info   TEXT,
            cancel_reason TEXT,
            cancelled_by  TEXT,
            member_id     INTEGER,
            applied_promo_id INTEGER REFERENCES promotions(id)
        )""",
    "menu_categories": """
        CREATE TABLE IF NOT EXISTS menu_categories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active     INTEGER NOT NULL DEFAULT 1
        )""",
    "stock_items": """
        CREATE TABLE IF NOT EXISTS stock_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            unit         TEXT NOT NULL,
            quantity     REAL NOT NULL DEFAULT 0,
            min_quantity REAL NOT NULL DEFAULT 0,
            active       INTEGER NOT NULL DEFAULT 1,
            alert_level  TEXT NOT NULL DEFAULT 'normal'
                         CHECK (alert_level IN ('normal','low_stock','out_of_stock'))
        )""",
    "menu_items": """
        CREATE TABLE IF NOT EXISTS menu_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id   INTEGER NOT NULL REFERENCES menu_categories(id),
            name          TEXT NOT NULL,
            item_type     TEXT NOT NULL CHECK (item_type IN ('weighed','normal')),
            price         REAL NOT NULL DEFAULT 0,
            is_sold_out   INTEGER NOT NULL DEFAULT 0,
            stock_item_id INTEGER REFERENCES stock_items(id),
            image_path    TEXT,
            sort_order    INTEGER NOT NULL DEFAULT 0,
            active        INTEGER NOT NULL DEFAULT 1
        )""",
    "stock_movements": """
        CREATE TABLE IF NOT EXISTS stock_movements (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_item_id INTEGER NOT NULL REFERENCES stock_items(id),
            change_qty    REAL NOT NULL,
            reason        TEXT NOT NULL,
            ref_type      TEXT,
            ref_id        INTEGER,
            created_by    INTEGER REFERENCES users(id),
            created_at    TEXT NOT NULL
        )""",
    "orders": """
        CREATE TABLE IF NOT EXISTS orders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES table_sessions(id),
            status     TEXT NOT NULL DEFAULT 'new'
                       CHECK (status IN ('new','preparing','served','cancelled')),
            note       TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )""",
    "order_items": """
        CREATE TABLE IF NOT EXISTS order_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id      INTEGER NOT NULL REFERENCES orders(id),
            menu_item_id  INTEGER NOT NULL REFERENCES menu_items(id),
            name_snapshot TEXT NOT NULL,
            unit_price    REAL NOT NULL,
            quantity      INTEGER NOT NULL DEFAULT 1,
            status        TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','served','cancelled')),
            cancel_reason TEXT,
            cancelled_by  INTEGER REFERENCES users(id),
            cancelled_at  TEXT
        )""",
    "weigh_entries": """
        CREATE TABLE IF NOT EXISTS weigh_entries (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    INTEGER NOT NULL REFERENCES table_sessions(id),
            menu_item_id  INTEGER NOT NULL REFERENCES menu_items(id),
            name_snapshot TEXT NOT NULL,
            weight_grams  INTEGER NOT NULL CHECK (weight_grams > 0),
            price_per_kg  REAL NOT NULL,
            amount        REAL NOT NULL,
            status        TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','cancelled')),
            cancel_reason TEXT,
            created_by    INTEGER REFERENCES users(id),
            created_at    TEXT NOT NULL
        )""",
    "customer_notices": """
        CREATE TABLE IF NOT EXISTS customer_notices (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES table_sessions(id),
            kind       TEXT NOT NULL,
            message    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at    TEXT
        )""",
    "staff_alerts": """
        CREATE TABLE IF NOT EXISTS staff_alerts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    INTEGER REFERENCES table_sessions(id),
            stock_item_id INTEGER REFERENCES stock_items(id),
            kind          TEXT NOT NULL CHECK (kind IN
                          ('pending_timeout','idle_open','low_stock','out_of_stock')),
            message       TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','snoozed','resolved')),
            sound_played  INTEGER NOT NULL DEFAULT 0,
            snooze_until  TEXT,
            resolution    TEXT,
            resolved_by   INTEGER REFERENCES users(id),
            created_at    TEXT NOT NULL,
            resolved_at   TEXT
        )""",
    "promotions": """
        CREATE TABLE IF NOT EXISTS promotions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            promo_type  TEXT NOT NULL CHECK (promo_type IN ('percent','fixed')),
            value       REAL NOT NULL,
            min_amount  REAL NOT NULL DEFAULT 0,
            start_at    TEXT,
            end_at      TEXT,
            active      INTEGER NOT NULL DEFAULT 1,
            target      TEXT NOT NULL DEFAULT 'general' CHECK (target IN ('general','member')),
            code        TEXT,
            description TEXT
        )""",
    "bills": """
        CREATE TABLE IF NOT EXISTS bills (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL UNIQUE REFERENCES table_sessions(id),
            subtotal        REAL NOT NULL,
            promo_id        INTEGER REFERENCES promotions(id),
            discount        REAL NOT NULL DEFAULT 0,
            service_charge  REAL NOT NULL DEFAULT 0,
            vat             REAL NOT NULL DEFAULT 0,
            total           REAL NOT NULL,
            payment_method  TEXT,
            amount_received REAL NOT NULL DEFAULT 0,
            change_amount   REAL NOT NULL DEFAULT 0,
            cashier_id      INTEGER REFERENCES users(id),
            created_at      TEXT NOT NULL,
            paid_at         TEXT
        )""",
    "activity_log": """
        CREATE TABLE IF NOT EXISTS activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id),
            actor      TEXT,
            action     TEXT NOT NULL,
            detail     TEXT,
            ref_type   TEXT,
            ref_id     INTEGER,
            created_at TEXT NOT NULL
        )""",
}

INDEXES_SQL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_table_status ON table_sessions(table_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status ON table_sessions(status)",
    "CREATE INDEX IF NOT EXISTS idx_menu_items_cat ON menu_items(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_weigh_session ON weigh_entries(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_notices_session ON customer_notices(session_id, read_at)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_status ON staff_alerts(status)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_stock ON staff_alerts(stock_item_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_stock_mov_item ON stock_movements(stock_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_bills_paid ON bills(paid_at)",
    "CREATE INDEX IF NOT EXISTS idx_log_created ON activity_log(created_at)",
]

TABLE_NAMES: list[str] = list(TABLES_SQL.keys())


def _table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {r["name"] for r in rows}


def migrate(conn) -> None:
    """อัปเกรดฐานข้อมูลเดิมให้รองรับฟีเจอร์ใหม่แบบ idempotent (รันซ้ำได้ ไม่ลบข้อมูลเดิม)"""
    now = db.now_str()

    # 1. menu_items.image_path
    menu_cols = _table_columns(conn, "menu_items")
    if "image_path" not in menu_cols:
        conn.execute("ALTER TABLE menu_items ADD COLUMN image_path TEXT")

    # 2. stock_items.alert_level
    stock_cols = _table_columns(conn, "stock_items")
    if "alert_level" not in stock_cols:
        conn.execute(
            "ALTER TABLE stock_items ADD COLUMN alert_level TEXT NOT NULL DEFAULT 'normal'"
        )

    # 3. bills.amount_received, bills.change_amount
    bill_cols = _table_columns(conn, "bills")
    if "amount_received" not in bill_cols:
        conn.execute("ALTER TABLE bills ADD COLUMN amount_received REAL NOT NULL DEFAULT 0")
    if "change_amount" not in bill_cols:
        conn.execute("ALTER TABLE bills ADD COLUMN change_amount REAL NOT NULL DEFAULT 0")
    conn.execute(
        "UPDATE bills SET amount_received = total, change_amount = 0 "
        "WHERE amount_received = 0 AND total > 0"
    )

    # 4. staff_alerts: รองรับ stock_item_id (nullable session_id) และ kind 'low_stock'/'out_of_stock'
    alert_cols = _table_columns(conn, "staff_alerts")
    alert_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='staff_alerts'"
    ).fetchone()
    alert_sql = (alert_sql_row["sql"] or "") if alert_sql_row else ""
    if "stock_item_id" not in alert_cols or "low_stock" not in alert_sql:
        conn.execute(
            """
            CREATE TABLE staff_alerts_new (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    INTEGER REFERENCES table_sessions(id),
                stock_item_id INTEGER REFERENCES stock_items(id),
                kind          TEXT NOT NULL CHECK (kind IN
                              ('pending_timeout','idle_open','low_stock','out_of_stock')),
                message       TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active','snoozed','resolved')),
                sound_played  INTEGER NOT NULL DEFAULT 0,
                snooze_until  TEXT,
                resolution    TEXT,
                resolved_by   INTEGER REFERENCES users(id),
                created_at    TEXT NOT NULL,
                resolved_at   TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO staff_alerts_new (
                id, session_id, stock_item_id, kind, message, status,
                sound_played, snooze_until, resolution, resolved_by, created_at, resolved_at
            )
            SELECT
                id, session_id, NULL, kind, message, status,
                sound_played, snooze_until, resolution, resolved_by, created_at, resolved_at
            FROM staff_alerts
            """
        )
        conn.execute("DROP TABLE staff_alerts")
        conn.execute("ALTER TABLE staff_alerts_new RENAME TO staff_alerts")

    # 5. ถ้าตาราง settings มีข้อมูลอยู่แล้ว (ฐานข้อมูลเดิม) ให้เติมคีย์ใหม่ที่ยังไม่มี และปรับราคาชั่งกิโลเริ่มต้นเป็น 299
    has_settings = conn.execute("SELECT 1 FROM settings LIMIT 1").fetchone() is not None
    if has_settings:
        had_weigh_rate = (
            conn.execute("SELECT 1 FROM settings WHERE key = 'weigh_price_per_kg'").fetchone()
            is not None
        )
        for key, value in config.DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, str(value), now),
            )
        if not had_weigh_rate:
            # อัปเดตราคาเมนูชั่งกิโลเดิมในฐานข้อมูลให้ตรงกับกติกาใหม่ 299 บาท/กก. (ไม่กระทบบิล/รายการชั่งย้อนหลัง)
            conn.execute(
                "UPDATE menu_items SET price = ? WHERE item_type = ? AND price IN (280, 260, 420)",
                (float(config.DEFAULT_WEIGH_PRICE_PER_KG), config.MENU_TYPE_WEIGHED),
            )



    # 6. promotions: target ('general'|'member'), code, description และ table_sessions: member_id, applied_promo_id
    promo_cols = _table_columns(conn, "promotions")
    if "target" not in promo_cols:
        conn.execute("ALTER TABLE promotions ADD COLUMN target TEXT NOT NULL DEFAULT 'general'")
    if "code" not in promo_cols:
        conn.execute("ALTER TABLE promotions ADD COLUMN code TEXT")
    if "description" not in promo_cols:
        conn.execute("ALTER TABLE promotions ADD COLUMN description TEXT")

    sess_cols = _table_columns(conn, "table_sessions")
    if "member_id" not in sess_cols:
        conn.execute("ALTER TABLE table_sessions ADD COLUMN member_id INTEGER")
    if "applied_promo_id" not in sess_cols:
        conn.execute("ALTER TABLE table_sessions ADD COLUMN applied_promo_id INTEGER")


def create_all() -> None:
    """สร้างตารางและ index ที่ยังไม่มี (รันซ้ำได้ ไม่ลบข้อมูล) พร้อมรัน migration และแถว shop_status"""
    with db.transaction() as conn:
        for sql in TABLES_SQL.values():
            conn.execute(sql)
        migrate(conn)
        for sql in INDEXES_SQL:
            conn.execute(sql)
        conn.execute(
            "INSERT OR IGNORE INTO shop_status (id, is_open, changed_at) VALUES (1, 0, ?)",
            (db.now_str(),),
        )
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def drop_all() -> None:
    """ลบทุกตาราง (ใช้ตอนพัฒนา/ทดสอบเท่านั้น — ข้อมูลหาย!)"""
    conn = db.get_connection()
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        for name in reversed(TABLE_NAMES):
            conn.execute(f"DROP TABLE IF EXISTS {name}")
        conn.commit()
    finally:
        conn.close()


def list_tables() -> list[str]:
    """ชื่อตารางที่มีจริงในฐานข้อมูล (ไม่รวมตารางภายในของ SQLite)"""
    rows = db.query_all(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r["name"] for r in rows]


if __name__ == "__main__":
    if "--reset" in sys.argv:
        drop_all()
        print("ลบทุกตารางแล้ว")
    create_all()
    print(f"สร้าง/อัปเกรดตารางแล้ว {len(list_tables())} ตาราง:", ", ".join(list_tables()))
