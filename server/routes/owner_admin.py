"""server/routes/owner_admin.py — API หน้าเจ้าของร้าน:
โปรโมชั่น, จัดการโต๊ะ/QR, ผู้ใช้, ตั้งค่า, ประวัติการใช้งาน, สำรองข้อมูล
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from server.deps import require_owner
from server.helpers import (
    ACTION_BY_TH,
    action_text,
    detect_lan_ip,
    fmt_datetime,
    fmt_qty,
    human_size,
    parse_date,
    parse_int,
    parse_number,
    parse_percent,
    status_color,
    who_text,
)
from services import (
    auth_service,
    backup_service,
    log_service,
    member_service,
    promo_service,
    qr_service,
    settings_service,
    shop_service,
    table_service,
)

MAX_MINUTES = 1440
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def qr_file_for(table_no: int) -> Path:
    return Path(config.QR_DIR) / f"table_{table_no}.png"


def url_is_local(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "").lower() in LOCAL_HOSTS
    except ValueError:
        return True


def normalize_base_url(text: str) -> str:
    t = (text or "").strip().rstrip("/")
    if not t:
        raise ValueError("กรุณากรอกลิงก์เว็บลูกค้า")
    parsed = urlparse(t)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("ลิงก์ต้องขึ้นต้นด้วย http:// หรือ https:// เช่น http://192.168.1.50:8080")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("ใส่เฉพาะที่อยู่เว็บ (ไม่ต้องมี /... ต่อท้าย) เช่น http://192.168.1.50:8080")
    return t


router = APIRouter(prefix="/api/owner", tags=["owner_admin"])


class PromoRequest(BaseModel):
    name: str
    promo_type: str = "percent"
    value: float | str
    min_amount: float | str = 0
    start_at: str | None = ""
    end_at: str | None = ""
    active: bool = True
    target: str = "general"
    code: str | None = None
    description: str | None = None


class PromoToggleRequest(BaseModel):
    active: bool


def _period_text(p: dict) -> str:
    start, end = (p["start_at"] or "")[:10], (p["end_at"] or "")[:10]
    if not start and not end:
        return "ไม่จำกัด"
    return f"{start or '...'} ถึง {end or '...'}"


@router.get("/promos")
def list_promos(_user: dict = Depends(require_owner)) -> dict:
    promo_service.ensure_default_member_promos()
    promos = promo_service.list_promos(include_inactive=True)
    usable = 0
    general_promos = []
    member_promos = []
    general_usable = 0
    member_usable = 0
    for p in promos:
        in_period = promo_service.is_in_period(p)
        p["in_period"] = in_period
        p["period_text"] = _period_text(p)
        if not p["active"]:
            p["status_text"] = "ปิดใช้งาน"
            p["status_kind"] = "neutral"
        elif not in_period:
            p["status_text"] = "นอกช่วงเวลา"
            p["status_kind"] = "warning"
        else:
            p["status_text"] = "ใช้ได้"
            p["status_kind"] = "success"
            usable += 1
            if p.get("target") == "member":
                member_usable += 1
            else:
                general_usable += 1
        if p.get("target") == "member":
            member_promos.append(p)
        else:
            general_promos.append(p)
    members = member_service.list_members_with_active_status()
    active_members = sum(1 for m in members if m.get("is_active_dining"))
    return {
        "promos": promos,
        "general_promos": general_promos,
        "member_promos": member_promos,
        "general_subtitle": f"{len(general_promos)} โปร · ใช้ได้ตอนนี้ {general_usable} โปร",
        "member_subtitle": f"{len(member_promos)} โปร · ใช้ได้ตอนนี้ {member_usable} โปร",
        "subtitle": f"ทั้งหมด {len(promos)} โปร (ทั่วไป {len(general_promos)} · สมาชิก {len(member_promos)}) · ใช้ได้ตอนนี้ {usable} โปร",
        "member_count": len(members),
        "active_member_count": active_members,
    }


@router.get("/members")
def list_owner_members(_user: dict = Depends(require_owner)) -> dict:
    members = member_service.list_members_with_active_status()
    active_count = sum(1 for m in members if m.get("is_active_dining"))
    return {
        "members": members,
        "total": len(members),
        "active_dining_count": active_count,
        "subtitle": f"สมาชิกทั้งหมด {len(members)} คน · กำลังใช้งานที่ร้าน {active_count} คน",
    }


@router.post("/promos")
def create_promo(body: PromoRequest, user: dict = Depends(require_owner)) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise ValueError("กรุณาใส่ชื่อโปรโมชั่น")
    value = parse_number(str(body.value), "ค่าส่วนลด", minimum=0)
    if value <= 0:
        raise ValueError("ค่าส่วนลดต้องมากกว่า 0")
    if body.promo_type == "percent" and value > 100:
        raise ValueError("ส่วนลดเปอร์เซ็นต์ต้องไม่เกิน 100")
    min_amount = parse_number(str(body.min_amount or ""), "ยอดขั้นต่ำ", minimum=0, allow_empty=True)
    start = parse_date(body.start_at or "", "วันเริ่ม")
    end = parse_date(body.end_at or "", "วันสิ้นสุด")
    if start and end and start > end:
        raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")

    p = promo_service.add_promo(
        name,
        body.promo_type,
        value,
        min_amount,
        start or None,
        end or None,
        user_id=user["id"],
        target=body.target,
        code=body.code,
        description=body.description,
    )
    if not body.active:
        p = promo_service.update_promo(p["id"], active=False, user_id=user["id"])
    return {"promo": p, "message": "เพิ่มโปรแล้ว"}


@router.patch("/promos/{promo_id}")
def update_promo(promo_id: int, body: PromoRequest, user: dict = Depends(require_owner)) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise ValueError("กรุณาใส่ชื่อโปรโมชั่น")
    value = parse_number(str(body.value), "ค่าส่วนลด", minimum=0)
    if value <= 0:
        raise ValueError("ค่าส่วนลดต้องมากกว่า 0")
    if body.promo_type == "percent" and value > 100:
        raise ValueError("ส่วนลดเปอร์เซ็นต์ต้องไม่เกิน 100")
    min_amount = parse_number(str(body.min_amount or ""), "ยอดขั้นต่ำ", minimum=0, allow_empty=True)
    start = parse_date(body.start_at or "", "วันเริ่ม")
    end = parse_date(body.end_at or "", "วันสิ้นสุด")
    if start and end and start > end:
        raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")

    p = promo_service.update_promo(
        promo_id,
        name=name,
        promo_type=body.promo_type,
        value=value,
        min_amount=min_amount,
        start_at=start,
        end_at=end,
        active=bool(body.active),
        user_id=user["id"],
        target=body.target,
        code=body.code,
        description=body.description,
    )
    return {"promo": p, "message": "บันทึกโปรแล้ว (บิลที่ปิดไปแล้วไม่เปลี่ยน)"}


@router.post("/promos/{promo_id}/toggle")
def toggle_promo(promo_id: int, body: PromoToggleRequest, user: dict = Depends(require_owner)) -> dict:
    p = promo_service.update_promo(promo_id, active=bool(body.active), user_id=user["id"])
    msg = "เปิดใช้งานโปรแล้ว" if body.active else "ปิดใช้งานโปรแล้ว"
    return {"promo": p, "message": msg}


class TableCreateRequest(BaseModel):
    table_no: int | str
    name: str | None = ""


class TableUpdateRequest(BaseModel):
    name: str | None = None
    active: bool | None = None


@router.get("/tables_manage")
def list_tables_manage(_user: dict = Depends(require_owner)) -> dict:
    live = {t["id"]: t for t in table_service.list_tables_with_status()}
    tables = []
    for t in table_service.list_tables(include_inactive=True):
        t_copy = dict(t)
        t_copy.pop("secret_key", None)
        status_key = live[t["id"]]["status"] if t["id"] in live else "inactive"
        status_th = live[t["id"]]["status_th"] if t["id"] in live else "ปิดใช้งาน"
        url = qr_service.build_url(t["table_no"], t["secret_key"])
        has_qr = qr_file_for(t["table_no"]).exists()
        t_copy.update({
            "status_key": status_key,
            "status_th": status_th,
            "status_color": "#868e96" if status_key == "inactive" else status_color(status_key),
            "qr_url": url,
            "url_is_local": url_is_local(url),
            "has_qr_file": has_qr,
            "qr_status_text": "สร้างแล้ว" if has_qr else "ยังไม่สร้าง",
            "qr_image_endpoint": f"/api/owner/tables_manage/{t['id']}/qr_image",
        })
        tables.append(t_copy)
    active = sum(1 for t in tables if t["active"])
    suggested_no = max((t["table_no"] for t in tables), default=0) + 1
    return {
        "tables": tables,
        "suggested_no": suggested_no,
        "subtitle": f"{len(tables)} โต๊ะ (ใช้งาน {active})",
    }


@router.post("/tables_manage")
def add_new_table(body: TableCreateRequest, user: dict = Depends(require_owner)) -> dict:
    no = parse_int(str(body.table_no), "เลขโต๊ะ", minimum=1)
    t = table_service.add_table(no, (body.name or "").strip() or None, user_id=user["id"])
    t.pop("secret_key", None)
    return {"table": t, "message": f"เพิ่มโต๊ะ {no} แล้ว"}


@router.patch("/tables_manage/{table_id}")
def update_existing_table(table_id: int, body: TableUpdateRequest, user: dict = Depends(require_owner)) -> dict:
    t = table_service.update_table(table_id, name=body.name, active=body.active, user_id=user["id"])
    t.pop("secret_key", None)
    msg = "บันทึกแล้ว"
    if body.name is not None and body.active is None:
        msg = "เปลี่ยนชื่อแล้ว"
    elif body.active is not None:
        msg = "เปิดใช้งานโต๊ะแล้ว" if body.active else "ปิดใช้งานโต๊ะแล้ว"
    return {"table": t, "message": msg}


@router.post("/tables_manage/{table_id}/regenerate_secret")
def regenerate_table_secret(table_id: int, user: dict = Depends(require_owner)) -> dict:
    t = table_service.regenerate_secret(table_id, user_id=user["id"])
    if qr_file_for(t["table_no"]).exists():
        qr_service.generate_qr_image(table_id)
    t.pop("secret_key", None)
    return {"table": t, "message": "เปลี่ยนรหัสลับแล้ว"}


@router.post("/tables_manage/{table_id}/qr")
def generate_table_qr(table_id: int, _user: dict = Depends(require_owner)) -> dict:
    t = table_service.get_table(table_id)
    if t is None:
        raise ValueError("ไม่พบโต๊ะ")
    path = qr_service.generate_qr_image(table_id)
    return {
        "path": str(path),
        "message": f"สร้าง QR โต๊ะ {t['table_no']} แล้ว",
    }


@router.post("/tables_manage/qr_all")
def generate_all_tables_qr(_user: dict = Depends(require_owner)) -> dict:
    paths = qr_service.generate_all_qr()
    return {
        "count": len(paths),
        "message": f"สร้าง QR แล้ว {len(paths)} โต๊ะ (ไฟล์อยู่ที่โฟลเดอร์ QR)",
    }


@router.get("/tables_manage/{table_id}/qr_image")
def get_table_qr_image(table_id: int, download: bool = False, _user: dict = Depends(require_owner)):
    t = table_service.get_table(table_id)
    if t is None:
        raise HTTPException(status_code=404, detail="ไม่พบโต๊ะ")
    path = qr_file_for(t["table_no"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="ยังไม่มีรูป QR")
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="table_{t["table_no"]}.png"'
    return FileResponse(path=str(path), media_type="image/png", headers=headers)


class UserCreateRequest(BaseModel):
    username: str
    display_name: str = ""
    role: str = config.ROLE_STAFF
    password: str
    password_confirm: str | None = None


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    active: bool | None = None


class UserPasswordRequest(BaseModel):
    password: str
    password_confirm: str | None = None


@router.get("/users")
def list_all_users(current_user: dict = Depends(require_owner)) -> dict:
    users = auth_service.list_users(include_inactive=True)
    for u in users:
        u["is_me"] = u["id"] == current_user["id"]
        u["role_th"] = "เจ้าของร้าน" if u["role"] == config.ROLE_OWNER else "พนักงาน"
        u["created_at_fmt"] = fmt_datetime(u["created_at"])
        u["status_text"] = ("ใช้งาน (คุณ)" if u["is_me"] else "ใช้งาน") if u["active"] else "ปิดบัญชี"
    active = sum(1 for u in users if u["active"])
    return {
        "users": users,
        "min_password_length": config.MIN_PASSWORD_LENGTH,
        "subtitle": f"{len(users)} บัญชี (ใช้งาน {active})",
    }


@router.post("/users")
def create_new_user(body: UserCreateRequest, current_user: dict = Depends(require_owner)) -> dict:
    username = (body.username or "").strip()
    if not username:
        raise ValueError("กรุณากรอกชื่อผู้ใช้")
    if body.password_confirm is not None and body.password != body.password_confirm:
        raise ValueError("รหัสผ่านทั้งสองช่องไม่ตรงกัน")
    u = auth_service.create_user(
        username,
        body.password,
        (body.display_name or "").strip() or username,
        body.role,
        by_user_id=current_user["id"],
    )
    return {"user": u, "message": f"เพิ่มผู้ใช้ {u['username']} แล้ว"}


@router.patch("/users/{user_id}")
def edit_existing_user(user_id: int, body: UserUpdateRequest, current_user: dict = Depends(require_owner)) -> dict:
    target = auth_service.get_user(user_id)
    if target is None:
        raise ValueError("ไม่พบผู้ใช้")
    if user_id == current_user["id"]:
        if body.role is not None and body.role != target["role"]:
            raise ValueError("ลดสิทธิ์บัญชีที่กำลังล็อกอินอยู่ไม่ได้")
        if body.active is False:
            raise ValueError("ปิดบัญชีที่กำลังล็อกอินอยู่ไม่ได้")
    u = auth_service.update_user(
        user_id,
        display_name=body.display_name,
        role=body.role,
        active=body.active,
        by_user_id=current_user["id"],
    )
    msg = "บันทึกแล้ว"
    if body.active is not None and body.display_name is None and body.role is None:
        msg = "เปิดบัญชีแล้ว" if body.active else "ปิดบัญชีแล้ว"
    return {"user": u, "message": msg}


@router.post("/users/{user_id}/password")
def reset_user_password(user_id: int, body: UserPasswordRequest, current_user: dict = Depends(require_owner)) -> dict:
    target = auth_service.get_user(user_id)
    if target is None:
        raise ValueError("ไม่พบผู้ใช้")
    if body.password_confirm is not None and body.password != body.password_confirm:
        raise ValueError("รหัสผ่านทั้งสองช่องไม่ตรงกัน")
    auth_service.change_password(user_id, body.password, by_user_id=current_user["id"])
    return {"ok": True, "message": f"เปลี่ยนรหัสผ่านของ {target['username']} แล้ว"}


class SettingsSaveRequest(BaseModel):
    shop_name: str
    shop_tax_id: str = ""
    shop_tax_id_enabled: bool = False
    shop_address: str = ""
    shop_subdistrict: str = ""
    shop_district: str = ""
    shop_province: str = ""
    shop_postal_code: str = ""
    shop_phone: str = ""
    public_base_url: str
    promptpay_id: str
    promptpay_name: str
    weigh_price_per_kg: float | str
    alert_pending_minutes: int | str
    alert_idle_open_minutes: int | str
    alert_snooze_minutes: int | str
    stock_low_threshold: float | str
    service_charge_enabled: bool = False
    service_charge_percent: float | str = 10
    vat_enabled: bool = False
    vat_percent: float | str = 7


@router.get("/settings")
def get_settings_data(_user: dict = Depends(require_owner)) -> dict:
    s = settings_service
    shop = s.get_shop_info()
    ip = detect_lan_ip()
    lan_url = f"http://{ip}:{config.WEB_PORT}" if ip else None
    return {
        "shop": shop,
        "public_base_url": s.get_setting("public_base_url", "") or "",
        "lan_url": lan_url,
        "promptpay_id": s.get_setting("promptpay_id", config.DEFAULT_PROMPTPAY_ID) or config.DEFAULT_PROMPTPAY_ID,
        "promptpay_name": s.get_setting("promptpay_name", config.DEFAULT_PROMPTPAY_NAME) or config.DEFAULT_PROMPTPAY_NAME,
        "weigh_price_per_kg": fmt_qty(s.get_float("weigh_price_per_kg", config.DEFAULT_WEIGH_PRICE_PER_KG)),
        "alert_pending_minutes": str(s.get_int("alert_pending_minutes", 5)),
        "alert_idle_open_minutes": str(s.get_int("alert_idle_open_minutes", 10)),
        "alert_snooze_minutes": str(s.get_int("alert_snooze_minutes", 5)),
        "stock_low_threshold": fmt_qty(s.get_float("stock_low_threshold", config.DEFAULT_STOCK_LOW_THRESHOLD)),
        "service_charge_enabled": s.get_bool("service_charge_enabled"),
        "service_charge_percent": f"{s.get_float('service_charge_percent', 10):g}",
        "vat_enabled": s.get_bool("vat_enabled"),
        "vat_percent": f"{s.get_float('vat_percent', 7):g}",
    }


@router.put("/settings")
def save_settings_data(body: SettingsSaveRequest, user: dict = Depends(require_owner)) -> dict:
    shop_name = (body.shop_name or "").strip()
    if not shop_name:
        raise ValueError("กรุณากรอกชื่อร้าน")
    tax_id = (body.shop_tax_id or "").strip().replace("-", "").replace(" ", "")
    if tax_id and (not tax_id.isdigit() or len(tax_id) != 13):
        raise ValueError("เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลข 13 หลัก (หรือเว้นว่างไว้หากไม่มี)")
    postal = (body.shop_postal_code or "").strip()
    if postal and (not postal.isdigit() or len(postal) != 5):
        raise ValueError("รหัสไปรษณีย์ต้องเป็นตัวเลข 5 หลัก (หรือเว้นว่างไว้)")

    clean_pp_id, _ = qr_service.validate_promptpay_id(body.promptpay_id)
    pp_name = (body.promptpay_name or "").strip()
    if not pp_name:
        raise ValueError("กรุณากรอกชื่อบัญชีเจ้าของร้านสำหรับตรวจสอบ")
    weigh_rate = parse_number(str(body.weigh_price_per_kg), "ราคาชั่งกิโล", minimum=1, maximum=100000)
    stock_thresh = parse_number(str(body.stock_low_threshold), "เกณฑ์สต๊อกใกล้หมด", minimum=0, maximum=100000)

    old_url = settings_service.get_setting("public_base_url", "") or ""
    new_url = normalize_base_url(body.public_base_url)

    values = {
        "shop_name": shop_name,
        "shop_tax_id": tax_id,
        "shop_tax_id_enabled": bool(body.shop_tax_id_enabled),
        "shop_address": (body.shop_address or "").strip(),
        "shop_subdistrict": (body.shop_subdistrict or "").strip(),
        "shop_district": (body.shop_district or "").strip(),
        "shop_province": (body.shop_province or "").strip(),
        "shop_postal_code": postal,
        "shop_phone": (body.shop_phone or "").strip(),
        "public_base_url": new_url,
        "promptpay_id": clean_pp_id,
        "promptpay_name": pp_name,
        "weigh_price_per_kg": weigh_rate,
        "alert_pending_minutes": parse_int(str(body.alert_pending_minutes), "เวลารอยืนยัน", minimum=1, maximum=MAX_MINUTES),
        "alert_idle_open_minutes": parse_int(str(body.alert_idle_open_minutes), "เวลาโต๊ะเงียบ", minimum=1, maximum=MAX_MINUTES),
        "alert_snooze_minutes": parse_int(str(body.alert_snooze_minutes), "เวลาเตือนซ้ำ", minimum=1, maximum=MAX_MINUTES),
        "stock_low_threshold": stock_thresh,
        "service_charge_enabled": bool(body.service_charge_enabled),
        "service_charge_percent": parse_percent(str(body.service_charge_percent), "อัตราค่าบริการ"),
        "vat_enabled": bool(body.vat_enabled),
        "vat_percent": parse_percent(str(body.vat_percent), "อัตราภาษีมูลค่าเพิ่ม"),
    }
    settings_service.set_many(values, user_id=user["id"])
    url_changed = new_url != old_url
    return {
        "ok": True,
        "url_changed": url_changed,
        "url_changed_notice": (
            "คุณเปลี่ยนลิงก์เว็บลูกค้าแล้ว\nQR ที่พิมพ์ไว้เดิมจะยังชี้ไปลิงก์เก่า — "
            "ไปหน้า \"จัดการโต๊ะ/QR\" กด \"สร้าง QR ทุกโต๊ะ\" แล้วพิมพ์ติดโต๊ะใหม่"
            if url_changed else None
        ),
        "message": "บันทึกการตั้งค่าแล้ว",
    }


PAGE_SIZE = 100


@router.get("/logs")
def get_activity_logs(
    action: str | None = None,
    user_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    offset: int = 0,
    _user: dict = Depends(require_owner),
) -> dict:
    f = parse_date(date_from or "", "วันที่เริ่ม")
    t = parse_date(date_to or "", "วันที่สิ้นสุด")
    if f and t and f > t:
        raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")

    act_code = action if action else None
    if act_code and act_code in ACTION_BY_TH:
        act_code = ACTION_BY_TH[act_code]

    filters = {
        "action": act_code,
        "user_id": user_id,
        "date_from": f or None,
        "date_to": t or None,
    }
    total = log_service.count_logs(**filters)
    if offset >= total and offset > 0:
        offset = max(0, ((total - 1) // PAGE_SIZE) * PAGE_SIZE)
    rows = log_service.get_logs(limit=PAGE_SIZE, offset=offset, **filters)
    for r in rows:
        r["created_at_fmt"] = fmt_datetime(r["created_at"])
        r["who"] = who_text(r)
        r["action_th"] = action_text(r["action"])

    users = auth_service.list_users(include_inactive=True)
    user_options = []
    seen_labels = set()
    for u in users:
        label = u["display_name"]
        if label in seen_labels:
            label = f"{label} ({u['username']})"
        seen_labels.add(label)
        user_options.append({"id": u["id"], "label": label})

    action_options = [{"code": ACTION_BY_TH[th], "label": th} for th in sorted(ACTION_BY_TH)]
    first = offset + 1 if total else 0
    last = min(offset + PAGE_SIZE, total)

    return {
        "rows": rows,
        "total": total,
        "offset": offset,
        "page_size": PAGE_SIZE,
        "subtitle": f"ทั้งหมด {total:,} รายการ",
        "page_label": f"แสดง {first:,}–{last:,} จาก {total:,}",
        "has_prev": offset > 0,
        "has_next": offset + PAGE_SIZE < total,
        "user_options": user_options,
        "action_options": action_options,
    }


CONFIRM_WORD = "กู้คืน"


class RestoreBackupRequest(BaseModel):
    confirm_text: str = ""


def _restore_blockers() -> str | None:
    if shop_service.is_open():
        return "ร้านยังเปิดอยู่ — ปิดร้านก่อน"
    n = shop_service.active_session_count()
    if n > 0:
        return f"ยังมีโต๊ะค้าง {n} โต๊ะ — เคลียร์ที่หน้าโต๊ะก่อน"
    return None


@router.get("/backups")
def list_backups_state(_user: dict = Depends(require_owner)) -> dict:
    backups = backup_service.list_backups()
    out = []
    for i, b in enumerate(backups):
        out.append({
            "id": i,
            "filename": b["filename"],
            "kind": b["kind"],
            "kind_th": b["kind_th"],
            "size_bytes": b["size_bytes"],
            "size_text": human_size(b["size_bytes"]),
            "created_at": b["created_at"],
            "created_at_fmt": fmt_datetime(b["created_at"]),
            "download_url": f"/api/owner/backups/{b['filename']}/download",
        })
    latest = fmt_datetime(out[0]["created_at"]) if out else "ยังไม่มี"
    blocker = _restore_blockers()
    return {
        "backups": out,
        "subtitle": f"{len(out)} ไฟล์ · สำรองล่าสุด {latest}",
        "can_restore": blocker is None,
        "restore_blocker": blocker,
        "restore_status_text": (
            f"สถานะการกู้คืน: ยังกู้คืนไม่ได้ ({blocker})"
            if blocker
            else "สถานะการกู้คืน: พร้อม (ร้านปิดและไม่มีโต๊ะค้าง)"
        ),
    }


@router.post("/backups")
def create_manual_backup(user: dict = Depends(require_owner)) -> dict:
    info = backup_service.create_backup(user["id"])
    return {
        "filename": info["filename"],
        "size_bytes": info["size_bytes"],
        "size_text": human_size(info["size_bytes"]),
        "message": f"สำรองแล้ว: {info['filename']} ({human_size(info['size_bytes'])})",
    }


@router.delete("/backups/{filename}")
def delete_backup_file(filename: str, user: dict = Depends(require_owner)) -> dict:
    backup_service.delete_backup(filename, user["id"])
    return {"ok": True, "message": "ลบไฟล์สำรองแล้ว"}


@router.post("/backups/{filename}/restore")
def restore_from_backup(filename: str, body: RestoreBackupRequest, user: dict = Depends(require_owner)) -> dict:
    blocker = _restore_blockers()
    if blocker:
        raise ValueError(f"กู้คืนไม่ได้: {blocker}")
    if (body.confirm_text or "").strip() != CONFIRM_WORD:
        raise ValueError(f"พิมพ์ไม่ตรง ({CONFIRM_WORD}) — ยกเลิกการกู้คืน")
    result = backup_service.restore_backup(filename, user["id"])
    msg = (
        f"กู้คืนข้อมูลเรียบร้อย\nข้อมูลก่อนกู้คืนถูกสำรองไว้ที่ {result['filename']}\n"
        "ร้านถูกตั้งเป็น \"ปิด\" — ระบบจะพาไปหน้าล็อกอินใหม่ (ข้อมูลผู้ใช้อาจเปลี่ยน)\n"
        "แนะนำให้ปิดแล้วเปิดโปรแกรมอีกครั้ง (รวมเว็บมือถือถ้ารันแยก)"
    )
    if result.get("active_sessions"):
        msg += f"\n\nมีโต๊ะค้างจากไฟล์สำรอง {result['active_sessions']} โต๊ะ — ให้พนักงานเคลียร์ที่หน้าโต๊ะ"
    return {
        "prerestore_filename": result["filename"],
        "active_sessions": result.get("active_sessions", 0),
        "message": msg,
    }


@router.get("/backups/{filename}/download")
def download_backup_file(filename: str, _user: dict = Depends(require_owner)):
    p = backup_service._safe_path(filename)
    return FileResponse(
        path=str(p),
        filename=p.name,
        media_type="application/x-sqlite3",
    )
