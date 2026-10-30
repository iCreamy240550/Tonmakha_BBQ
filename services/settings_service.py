"""services/settings_service.py — อ่าน/เขียนค่าตั้งค่า (ตาราง settings, เก็บเป็นข้อความ)

ถ้ายังไม่มีคีย์ในฐานข้อมูล จะใช้ค่าจาก config.DEFAULT_SETTINGS
เมื่อเปลี่ยน weigh_price_per_kg จะอัปเดตราคาเมนูประเภท weighed ให้ตรงกันใน transaction เดียวกัน
"""
import re
import config
from database import db
from services import log_service

_INTERNAL_SETTING_KEYS = frozenset({"members_registry_json", "members_otp_sessions_json"})


def get_setting(key: str, default: str | None = None) -> str | None:
    """ค่าเป็นข้อความ; ไม่มีใน DB -> DEFAULT_SETTINGS -> default"""
    if key in _INTERNAL_SETTING_KEYS:
        return default
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
    if row is not None:
        return row["value"]
    if key in config.DEFAULT_SETTINGS:
        return str(config.DEFAULT_SETTINGS[key])
    return default


def get_int(key: str, default: int = 0) -> int:
    """ค่าเป็นจำนวนเต็ม (แปลงไม่ได้ -> default)"""
    try:
        return int(float(get_setting(key, str(default))))
    except (TypeError, ValueError):
        return default


def get_float(key: str, default: float = 0.0) -> float:
    """ค่าเป็นทศนิยม (แปลงไม่ได้ -> default)"""
    try:
        return float(get_setting(key, str(default)))
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    """ค่าเป็นจริง/เท็จ: '1','true','yes','on' = True"""
    value = get_setting(key, "1" if default else "0")
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def get_all() -> dict[str, str]:
    """ทุกค่าตั้งค่า (รวมค่าเริ่มต้นที่ยังไม่ถูกบันทึก ยกเว้นคีย์ภายในของระบบสมาชิก/OTP) -> dict ข้อความ"""
    result = {k: str(v) for k, v in config.DEFAULT_SETTINGS.items()}
    for row in db.query_all("SELECT key, value FROM settings"):
        if row["key"] in _INTERNAL_SETTING_KEYS:
            continue
        result[row["key"]] = row["value"]
    return result


def get_shop_info(conn=None) -> dict:
    """ดึงข้อมูลร้านสำหรับแสดงบนใบเสร็จจากตาราง settings (พร้อมค่าเริ่มต้นที่ปลอดภัย)"""
    def _val(k: str) -> str:
        row = db.query_one("SELECT value FROM settings WHERE key = ?", (k,), conn=conn)
        if row is not None:
            return str(row["value"])
        return str(config.DEFAULT_SETTINGS.get(k, ""))

    shop_name = _val("shop_name").strip() or config.APP_NAME
    tax_id = _val("shop_tax_id").strip()
    tax_id_enabled = _val("shop_tax_id_enabled").strip().lower() in ("1", "true", "yes", "on")
    address = _val("shop_address").strip()
    subdistrict = _val("shop_subdistrict").strip()
    district = _val("shop_district").strip()
    province = _val("shop_province").strip()
    postal_code = _val("shop_postal_code").strip()
    phone = _val("shop_phone").strip()

    # สร้างบรรทัดที่อยู่ 1 (ที่อยู่ + ต. + อ.)
    addr_parts = []
    if address:
        addr_parts.append(address)
    if subdistrict:
        addr_parts.append(subdistrict if subdistrict.startswith(("ต.", "ตำบล", "แขวง")) else f"ต.{subdistrict}")
    if district:
        addr_parts.append(district if district.startswith(("อ.", "อำเภอ", "เขต")) else f"อ.{district}")
    address_line1 = " ".join(addr_parts).strip()

    # สร้างบรรทัดที่อยู่ 2 (จ. + รหัสไปรษณีย์)
    prov_parts = []
    if province:
        prov_parts.append(province if province.startswith(("จ.", "จังหวัด", "กรุงเทพ")) else f"จ.{province}")
    if postal_code:
        prov_parts.append(postal_code)
    address_line2 = " ".join(prov_parts).strip()

    phone_line = ""
    if phone:
        phone_line = phone if phone.startswith("โทร") else f"โทร.{phone}"

    return {
        "shop_name": shop_name,
        "shop_tax_id": tax_id,
        "shop_tax_id_enabled": tax_id_enabled,
        "shop_address": address,
        "shop_subdistrict": subdistrict,
        "shop_district": district,
        "shop_province": province,
        "shop_postal_code": postal_code,
        "shop_phone": phone,
        "address_line1": address_line1,
        "address_line2": address_line2,
        "phone_line": phone_line,
    }


def _validate_and_sync(key: str, value: str, user_id: int | None, conn) -> str:
    """ตรวจสอบความถูกต้องของคีย์ตั้งค่าที่สำคัญ และซิงก์ข้อมูลที่เกี่ยวข้อง"""
    if key in _INTERNAL_SETTING_KEYS:
        raise ValueError("ไม่อนุญาตให้แก้ไขคีย์ภายในระบบโดยตรง")
    if key == "promptpay_id":
        from services import qr_service
        clean_id, _ = qr_service.validate_promptpay_id(value)
        return clean_id
    if key == "promptpay_name":
        name = value.strip()
        if not name:
            raise ValueError("กรุณากรอกชื่อบัญชี PromptPay สำหรับตรวจสอบ")
        return name
    if key == "stock_low_threshold":
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError("เกณฑ์สต๊อกใกล้หมดต้องเป็นตัวเลข")
        if v < 0:
            raise ValueError("เกณฑ์สต๊อกใกล้หมดต้องไม่ติดลบ")
        return f"{v:g}"
    if key == "weigh_price_per_kg":
        try:
            v = round(float(value), 2)
        except (TypeError, ValueError):
            raise ValueError("ราคาชั่งกิโลต่อกิโลกรัมต้องเป็นตัวเลข")
        if v <= 0:
            raise ValueError("ราคาชั่งกิโลต่อกิโลกรัมต้องมากกว่า 0")
        db.execute(
            "UPDATE menu_items SET price = ? WHERE item_type = ?",
            (v, config.MENU_TYPE_WEIGHED), conn=conn,
        )
        return f"{v:g}"
    if key == "shop_name":
        name = (value or "").strip()
        if not name:
            raise ValueError("กรุณากรอกชื่อร้าน")
        return name
    if key == "shop_tax_id":
        clean = (value or "").strip().replace("-", "").replace(" ", "")
        if clean and (not clean.isdigit() or len(clean) != 13):
            raise ValueError("เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลข 13 หลัก (หรือเว้นว่างไว้หากไม่มี)")
        return clean
    if key == "shop_postal_code":
        clean = (value or "").strip()
        if clean and (not clean.isdigit() or len(clean) != 5):
            raise ValueError("รหัสไปรษณีย์ต้องเป็นตัวเลข 5 หลัก (หรือเว้นว่างไว้)")
        return clean
    if key == "shop_phone":
        clean = (value or "").strip()
        if clean and not re.match(r"^[0-9\-\s\+()]{6,20}$", clean):
            raise ValueError("รูปแบบเบอร์โทรศัพท์ร้านไม่ถูกต้อง")
        return clean
    if key in ("shop_address", "shop_subdistrict", "shop_district", "shop_province"):
        return (value or "").strip()
    return value


def set_setting(key: str, value, user_id: int | None = None, conn=None) -> None:
    """บันทึกค่า (แปลงเป็นข้อความ; bool -> '1'/'0') และ log ถ้าค่าเปลี่ยนจริง"""
    def _do(c) -> None:
        raw = "1" if value is True else "0" if value is False else str(value)
        new = _validate_and_sync(key, raw, user_id, c)
        old = db.query_one("SELECT value FROM settings WHERE key = ?", (key,), conn=c)
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, new, db.now_str()), conn=c,
        )
        if old is None or old["value"] != new:
            log_service.log_action(
                "setting_change", f"แก้ตั้งค่า {key}: {old['value'] if old else '(ค่าเริ่มต้น)'} -> {new}",
                user_id=user_id, ref_type="setting", conn=c,
            )

    if conn is not None:
        _do(conn)
    else:
        with db.transaction() as c:
            _do(c)


def set_many(values: dict, user_id: int | None = None) -> None:
    """บันทึกหลายค่าใน transaction เดียว"""
    with db.transaction() as conn:
        for key, value in values.items():
            set_setting(key, value, user_id=user_id, conn=conn)
