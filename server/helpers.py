"""server/helpers.py — ฟังก์ชันช่วยเหลือสำหรับจัดรูปแบบเวลา วันที่ น้ำหนัก ยอดเงิน และการแปลงค่าจากฟอร์ม
ใช้ใน server/routes/* โดยไม่ต้องพึ่งโมดูล ui/ เดิม
"""
from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
import socket
import subprocess
import sys

import config

STATUS_COLORS = {
    config.TABLE_STATUS_FREE: "#868e96",
    config.SESSION_PENDING: "#f08c00",
    config.SESSION_OPEN: "#2f9e44",
    config.SESSION_AWAITING_PAYMENT: "#1c7ed6",
    config.SESSION_CLOSED: "#495057",
    config.SESSION_CANCELLED: "#e03131",
}

ORDER_STATUS_COLORS = {
    "new": "#e03131",
    "preparing": "#f08c00",
    "served": "#2f9e44",
    "cancelled": "#868e96",
}

THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]
THAI_MONTHS_SHORT = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

ACTION_TH = {
    "login": "เข้าสู่ระบบ", "login_fail": "เข้าสู่ระบบไม่สำเร็จ", "logout": "ออกจากระบบ",
    "shop_open": "เปิดร้าน", "shop_close": "ปิดร้าน", "shop_closed": "ปิดร้าน",
    "session_start": "ลูกค้าสแกนเข้าโต๊ะ", "session_confirm": "ยืนยันโต๊ะ", "session_cancel": "ยกเลิกโต๊ะ",
    "session_awaiting_payment": "เริ่มเช็คบิล", "session_close": "ปิดโต๊ะ", "checkout_paid": "ชำระเงิน",
    "takeaway_checkout": "สั่งกลับบ้าน (ชำระเงิน)",
    "member_login": "สมาชิกเข้าสู่ระบบ", "member_signup": "สมัครสมาชิกใหม่", "member_google_auth": "สมาชิกเข้าผ่าน Google",
    "weigh_add": "ชั่งน้ำหนัก", "weigh_cancel": "ยกเลิกรายการชั่ง",
    "order_create": "สร้างออเดอร์", "order_status": "เปลี่ยนสถานะออเดอร์", "order_item_cancel": "ยกเลิกรายการสั่ง",
    "notice_send": "ส่งข้อความถึงลูกค้า",
    "alert_raised": "แจ้งเตือนด่วน (โต๊ะ/สต๊อก)", "alert_cancel_table": "แจ้งเตือน: ยกเลิกโต๊ะ", "alert_snooze": "แจ้งเตือน: ปล่อยไว้",
    "alert_checked": "แจ้งเตือน: รับทราบ/ไปเช็คแล้ว", "alert_wake": "แจ้งเตือนซ้ำ", "alert_auto_clear": "แจ้งเตือนปิดเอง",
    "menu_category_add": "เพิ่มหมวดเมนู", "menu_category_update": "แก้หมวดเมนู", "menu_item_add": "เพิ่มเมนู",
    "menu_item_update": "แก้เมนู", "menu_item_delete": "ลบ/ปิดใช้เมนู", "menu_price_change": "แก้ราคาเมนู",
    "menu_sold_out": "เมนูหมด", "menu_available": "เมนูกลับมามีขาย", "menu_image_update": "อัปโหลดรูปเมนู", "menu_image_delete": "ลบรูปเมนู",
    "stock_add": "เพิ่มรายการสต๊อก", "stock_update": "แก้รายการสต๊อก", "stock_delete": "ลบ/ปิดใช้รายการสต๊อก",
    "stock_delete_blocked": "ปฏิเสธการลบสต๊อก",
    "promo_add": "เพิ่มโปรโมชั่น", "promo_update": "แก้โปรโมชั่น",
    "table_add": "เพิ่มโต๊ะ", "table_update": "แก้โต๊ะ", "table_secret_reset": "สุ่มรหัสลับ QR ใหม่",
    "user_create": "สร้างผู้ใช้", "user_update": "แก้ผู้ใช้", "password_change": "เปลี่ยนรหัสผ่าน",
    "setting_change": "แก้ตั้งค่า",
    "backup_create": "สำรองข้อมูล", "backup_delete": "ลบไฟล์สำรอง", "backup_prune": "ลบไฟล์สำรองเก่า",
    "backup_restore": "กู้คืนข้อมูล",
}
ACTION_BY_TH = {v: k for k, v in ACTION_TH.items() if k != "shop_closed"}


def action_text(code: str) -> str:
    return ACTION_TH.get(code, code)


def who_text(row: dict) -> str:
    return row.get("user_name") or row.get("actor") or "-"


def money(value: float | int | None) -> str:
    return f"{float(value or 0):,.2f}"


def baht(value: float | int | None) -> str:
    return f"{money(value)} บาท"


def weight_text(grams: int | float | None) -> str:
    g = float(grams or 0)
    kheed = g / (config.GRAMS_PER_KG / config.KHEED_PER_KG)
    kheed_txt = f"{kheed:g}"
    if g >= config.GRAMS_PER_KG:
        return f"{g / config.GRAMS_PER_KG:g} กก. ({kheed_txt} ขีด)"
    return f"{kheed_txt} ขีด"


def _parse_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def fmt_time(text: str | None) -> str:
    dt = _parse_dt(text)
    return dt.strftime("%H:%M") if dt else "-"


def fmt_datetime(text: str | None) -> str:
    dt = _parse_dt(text)
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "-"


def minutes_since(text: str | None, now: datetime | None = None) -> int:
    dt = _parse_dt(text)
    if dt is None:
        return 0
    return max(0, int(((now or datetime.now()) - dt).total_seconds() // 60))


def duration_text(text: str | None, now: datetime | None = None) -> str:
    m = minutes_since(text, now)
    if m < 60:
        return f"{m} นาที"
    return f"{m // 60} ชม. {m % 60} นาที"


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status, "#868e96")


def ce_to_be_year(ce_year: int) -> int:
    y = int(ce_year)
    return y if y >= 2400 else y + 543


def be_to_ce_year(be_or_ce_year: int) -> int:
    y = int(be_or_ce_year)
    return y - 543 if y >= 2400 else y


def format_thai_date(iso_date: str | date | None, short_month: bool = False) -> str:
    if not iso_date:
        return "เลือกวันที่..."
    if isinstance(iso_date, date):
        d = iso_date
    else:
        try:
            d = datetime.strptime(str(iso_date).strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            return str(iso_date)
    be_y = ce_to_be_year(d.year)
    m_name = THAI_MONTHS_SHORT[d.month - 1] if short_month else THAI_MONTHS[d.month - 1]
    return f"{d.day:02d}/{d.month:02d}/{be_y} ({d.day} {m_name} {be_y})"


def parse_number(text: str, label: str, minimum: float | None = None, maximum: float | None = None,
                 allow_empty: bool = False, default: float = 0.0) -> float:
    t = (text or "").strip().replace(",", "")
    if not t:
        if allow_empty:
            return default
        raise ValueError(f"กรุณากรอก{label}")
    try:
        value = float(t)
    except ValueError:
        raise ValueError(f"{label}ต้องเป็นตัวเลข") from None
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{label}ไม่ถูกต้อง")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label}ต้องไม่น้อยกว่า {minimum:g}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}ต้องไม่เกิน {maximum:g}")
    return value


def parse_int(text: str, label: str, minimum: int | None = None, maximum: int | None = None) -> int:
    value = parse_number(text, label)
    if value != int(value):
        raise ValueError(f"{label}ต้องเป็นจำนวนเต็ม")
    value = int(value)
    if minimum is not None and value < minimum:
        raise ValueError(f"{label}ต้องไม่น้อยกว่า {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}ต้องไม่เกิน {maximum}")
    return value


def parse_percent(text: str, label: str) -> float:
    return parse_number(text, label, minimum=0, maximum=100)


def parse_date(text: str, label: str, allow_empty: bool = True) -> str:
    t = (text or "").strip()
    if not t:
        if allow_empty:
            return ""
        raise ValueError(f"กรุณาเลือก{label}")
    if "(" in t:
        t = t.split("(", 1)[0].strip()

    for sep, order in (("-", "ymd"), ("/", "dmy"), ("/", "ymd")):
        if sep in t:
            parts = t.split(sep)
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                try:
                    if order == "ymd" and len(parts[0]) == 4:
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    elif order == "dmy" and len(parts[2]) == 4:
                        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    else:
                        continue
                    ce_y = be_to_ce_year(y)
                    return date(ce_y, m, d).isoformat()
                except ValueError:
                    raise ValueError(f"{label}ไม่ถูกต้อง") from None
    raise ValueError(f"{label}ไม่ถูกต้อง (กรุณาเลือกวันที่จากปฏิทิน)")


def fmt_qty(value: float | int | None) -> str:
    return f"{float(value or 0):,.3f}".rstrip("0").rstrip(".")


def open_folder(path) -> bool:
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return True
    except Exception:
        return False


def detect_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            ip = sock.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("ไบต์", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.0f} {unit}" if unit == "ไบต์" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{num_bytes} ไบต์"
