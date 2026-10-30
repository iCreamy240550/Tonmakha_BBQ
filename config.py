"""config.py — ค่าคงที่กลางของโปรเจกต์ (ทั้งฝั่ง PC และฝั่งเว็บมือถือใช้ร่วมกัน)

หมายเหตุ: ค่าที่เจ้าของปรับได้จากหน้าตั้งค่า (เช่น ภาษีมูลค่าเพิ่ม, ค่าบริการ, เวลาแจ้งเตือน, PromptPay, ข้อมูลร้านบนใบเสร็จ)
จะถูกเก็บในตาราง `settings` — ค่าใน DEFAULT_SETTINGS ด้านล่างใช้เป็นค่าเริ่มต้นตอน seed/migration เท่านั้น
"""
import os
from pathlib import Path
import secrets

# ---------- ข้อมูลร้าน ----------
APP_NAME = "ต้นมะค่า แคมป์ปิ้งบาร์หมูกระทะ"
APP_NAME_SHORT = "ต้นมะค่า"

# ---------- พาธต่าง ๆ ----------
BASE_DIR = Path(__file__).resolve().parent

# โหลดตัวแปรสภาพแวดล้อมจาก BASE_DIR/.env หากมีไลบรารี python-dotenv (ถ้าไม่มีให้ข้ามแบบไม่พัง)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env", override=False)
except Exception:
    pass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_flag_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return 1
    if raw in ("0", "false", "no", "off"):
        return 0
    try:
        return 1 if int(raw) != 0 else 0
    except ValueError:
        return default


DB_PATH = BASE_DIR / "tonmakha.db"
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"
FONTS_DIR = ASSETS_DIR / "fonts"
QR_DIR = ASSETS_DIR / "qr_codes"
UPLOADS_DIR = ASSETS_DIR / "uploads"
MENU_IMAGE_DIR = UPLOADS_DIR / "menu"
EXPORTS_DIR = BASE_DIR / "exports"
BACKUPS_DIR = BASE_DIR / "backups"
FRONTEND_DIR = BASE_DIR / "frontend"
SECRET_FILE = BASE_DIR / "web_secret.key"

# ---------- การตั้งค่าอีเมล (SMTP) ความปลอดภัย OTP และบัญชีตัวอย่างสมาชิก ----------
SMTP_HOST = os.getenv("SMTP_HOST", "").strip() or "smtp.gmail.com"
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "").strip() or APP_NAME
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()

_raw_otp_secret = os.getenv("OTP_SECRET", "").strip()
OTP_SECRET_CONFIGURED = len(_raw_otp_secret) >= 32
OTP_SECRET_IS_EPHEMERAL = not bool(_raw_otp_secret)
OTP_SECRET = _raw_otp_secret if _raw_otp_secret else secrets.token_urlsafe(48)

MEMBER_DEMO_ACCOUNTS = _env_flag_int("MEMBER_DEMO_ACCOUNTS", 0)

# ---------- รูปภาพเมนู ----------
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # จำกัดขนาดไฟล์อัปโหลดสูงสุด 5 MB
MENU_IMAGE_MAX_DIM = 400                # ขนาดภาพมาตรฐาน 1:1 (400x400 px) เหมาะกับมือถือและ PC
ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

# ---------- เว็บเซิร์ฟเวอร์ ----------
WEB_HOST = "0.0.0.0"          # ให้มือถือในเครือข่ายเดียวกันเข้าได้
WEB_PORT = 8080
# ฐานของลิงก์ใน QR เช่น "http://192.168.1.50:8080" — ให้เจ้าของแก้ผ่านหน้าตั้งค่า (key: public_base_url)
PUBLIC_BASE_URL = f"http://localhost:{WEB_PORT}"
QR_PATH_TEMPLATE = "/t/{table_no}?k={secret_key}"
SECRET_KEY_LENGTH = 16        # ความยาวรหัสลับของโต๊ะ
POLL_SECONDS = 3.0            # ลูกค้าเช็คสถานะ/ข้อความ/สต๊อกทุกกี่วินาที

# ---------- ความปลอดภัยเว็บและคุกกี้ ----------
STAFF_COOKIE_NAME = "tonmakha_staff"
CUSTOMER_COOKIE_NAME = "tonmakha_customer"
STAFF_SESSION_TTL_SECONDS = 12 * 3600           # 12 ชั่วโมง
CUSTOMER_SESSION_TTL_SECONDS = 30 * 24 * 3600   # 30 วัน
# วงเครือข่ายที่อนุญาตให้เข้าหน้าพนักงาน/เจ้าของ (/staff และ /api/staff|owner/*)
# ค่าเริ่มต้นอนุญาตเฉพาะเครื่องที่รันเซิร์ฟเวอร์ (localhost) ตาม PLAN §6.1
STAFF_ALLOWED_NETS = ("127.0.0.1/32", "::1/128", "localhost", "testclient")
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 600    # 10 นาที
LOGIN_LOCKOUT_SECONDS = 300   # 5 นาที
SCAN_MAX_ATTEMPTS = 30
SCAN_WINDOW_SECONDS = 60      # จำกัดความถี่สแกนต่อ IP

# ---------- ฐานข้อมูล ----------
DB_TIMEOUT_SECONDS = 10       # รอ lock ได้นานสุด

# ---------- สถานะ (ใช้ค่าอังกฤษในฐานข้อมูล) ----------
TABLE_STATUS_FREE = "free"
SESSION_PENDING = "pending"
SESSION_OPEN = "open"
SESSION_AWAITING_PAYMENT = "awaiting_payment"
SESSION_CLOSED = "closed"
SESSION_CANCELLED = "cancelled"

# ข้อความแสดงบนหน้าจอ (ภาษาไทย)
SESSION_STATUS_TH = {
    TABLE_STATUS_FREE: "ว่าง",
    SESSION_PENDING: "รอยืนยัน",
    SESSION_OPEN: "ใช้งาน",
    SESSION_AWAITING_PAYMENT: "รอชำระ",
    SESSION_CLOSED: "ปิด",
    SESSION_CANCELLED: "ยกเลิก",
}

# ประเภทเมนู
MENU_TYPE_WEIGHED = "weighed"   # ชั่งกิโล
MENU_TYPE_NORMAL = "normal"     # ปกติ

# บทบาทผู้ใช้
ROLE_STAFF = "staff"
ROLE_OWNER = "owner"

# ---------- ราคาและน้ำหนัก ----------
GRAMS_PER_KG = 1000
KHEED_PER_KG = 10             # 1 กก. = 10 ขีด
MIN_FIRST_WEIGH_GRAMS = 1000  # การชั่งครั้งแรกของแต่ละโต๊ะต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม (1,000 กรัม)
DEFAULT_WEIGH_PRICE_PER_KG = 299

# ---------- แจ้งเตือนโต๊ะเงียบและสต๊อก ----------
ALERT_CHECK_INTERVAL_SECONDS = 30
DEFAULT_STOCK_LOW_THRESHOLD = 5

# ---------- PromptPay เริ่มต้น (แก้ไขได้ที่หน้าตั้งค่าของเจ้าของร้าน) ----------
DEFAULT_PROMPTPAY_ID = "012345678"
DEFAULT_PROMPTPAY_NAME = "นางสาวพะพินพอ เพิ่มพูนพูน"

# ---------- ข้อมูลร้านสำหรับใบเสร็จ (แก้ไขได้ที่หน้าตั้งค่าของเจ้าของร้าน) ----------
DEFAULT_SHOP_NAME = APP_NAME
DEFAULT_SHOP_TAX_ID = ""
DEFAULT_SHOP_TAX_ID_ENABLED = 0
DEFAULT_SHOP_ADDRESS = ""
DEFAULT_SHOP_SUBDISTRICT = "วังตะเฆ่"
DEFAULT_SHOP_DISTRICT = "หนองบัวระเหว"
DEFAULT_SHOP_PROVINCE = "ชัยภูมิ"
DEFAULT_SHOP_POSTAL_CODE = ""
DEFAULT_SHOP_PHONE = ""

# ค่าเริ่มต้นของตาราง settings (เจ้าของปรับได้ภายหลัง)
DEFAULT_SETTINGS = {
    "alert_pending_minutes": 5,                        # กรณี A: pending นานเกิน N นาที
    "alert_idle_open_minutes": 10,                     # กรณี B: open แต่ไม่มีรายการ/ออเดอร์เกิน N นาที
    "alert_snooze_minutes": 5,                         # กด "ปล่อยไว้" แล้วเตือนอีกใน N นาที
    "stock_low_threshold": DEFAULT_STOCK_LOW_THRESHOLD,# เกณฑ์สต๊อกใกล้หมดเริ่มต้น (หน่วย)
    "service_charge_enabled": 0,
    "service_charge_percent": 10,
    "vat_enabled": 0,
    "vat_percent": 7,
    "public_base_url": PUBLIC_BASE_URL,
    "promptpay_id": DEFAULT_PROMPTPAY_ID,              # หมายเลขพร้อมเพย์รับเงิน
    "promptpay_name": DEFAULT_PROMPTPAY_NAME,          # ชื่อบัญชีพร้อมเพย์สำหรับพนักงานตรวจสอบ
    "weigh_price_per_kg": DEFAULT_WEIGH_PRICE_PER_KG,  # ราคาหมูกระทะชั่งกิโล (บาท/กก.)
    "shop_name": DEFAULT_SHOP_NAME,                    # ชื่อร้านบนใบเสร็จ
    "shop_tax_id": DEFAULT_SHOP_TAX_ID,                # เลขประจำตัวผู้เสียภาษี
    "shop_tax_id_enabled": DEFAULT_SHOP_TAX_ID_ENABLED,# เปิด/ปิดการแสดงเลขประจำตัวผู้เสียภาษีบนใบเสร็จ
    "shop_address": DEFAULT_SHOP_ADDRESS,              # ที่อยู่ร้าน (บ้านเลขที่/หมู่ที่/ถนน)
    "shop_subdistrict": DEFAULT_SHOP_SUBDISTRICT,      # ตำบล/แขวง
    "shop_district": DEFAULT_SHOP_DISTRICT,            # อำเภอ/เขต
    "shop_province": DEFAULT_SHOP_PROVINCE,            # จังหวัด
    "shop_postal_code": DEFAULT_SHOP_POSTAL_CODE,      # รหัสไปรษณีย์
    "shop_phone": DEFAULT_SHOP_PHONE,                  # เบอร์โทรศัพท์ร้าน
    "staff_allowed_nets": "",                          # วงเครือข่ายที่อนุญาตเพิ่มสำหรับหน้าพนักงาน (คั่นด้วยจุลภาค)
}

# ---------- ความปลอดภัย ----------
MIN_PASSWORD_LENGTH = 4
MEMBER_MIN_PASSWORD_LENGTH = 8
MEMBER_MAX_PASSWORD_BYTES = 72

# ---------- ตัวอย่างข้อมูลเริ่มต้น (ใช้ใน seed.py) ----------
DEFAULT_TABLE_COUNT = 10
