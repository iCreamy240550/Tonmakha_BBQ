"""services/member_service.py — ระบบสมาชิกฝั่งลูกค้า (สมัครสมาชิก 2 ขั้นด้วย OTP, เข้าสู่ระบบด้วยอีเมล+รหัสผ่าน,
ลืมรหัสผ่าน 2 ขั้นด้วย OTP, เก็บ/ใช้โค้ดส่วนลด, ประวัติการทำรายการ) และการดูรายชื่อสมาชิกสำหรับเจ้าของร้าน

หมายเหตุ:
- เก็บข้อมูลสมาชิกแบบถาวรในตาราง settings (key = 'members_registry_json') เพื่อรักษาโครงสร้าง 17 ตารางตามเดิม
- รหัสผ่านของสมาชิกถูกแฮชด้วย bcrypt เก็บในฟิลด์ password_hash เท่านั้น (ไม่มีการเก็บรหัสผ่านข้อความธรรมดา)
- ยืนยันตัวตนด้วยรหัส OTP ทางอีเมลจริงผ่าน services/otp_service.py และ services/email_service.py
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

import config
from database import db
from services import auth_service, checkout_service, log_service, otp_service, promo_service

MEMBERS_SETTING_KEY = "members_registry_json"
OTP_SETTING_KEY = otp_service.OTP_SETTING_KEY

DEMO_MEMBER_EMAILS = frozenset({"somchai@gmail.com", "praewa.google@gmail.com"})
GENERIC_LOGIN_ERROR = "อีเมลหรือรหัสผ่านไม่ถูกต้อง"
RESET_START_MESSAGE = "หากอีเมลนี้อยู่ในระบบสมาชิก ระบบได้ส่งรหัส OTP สำหรับตั้งรหัสผ่านใหม่ไปให้แล้ว"

_PHONE_DIGITS_RE = re.compile(r"^0[2345689]\d{7,8}$")

_login_rate_lock = threading.Lock()
_member_login_failures: dict[tuple[str, str], list[float]] = {}
_member_login_lockouts: dict[tuple[str, str], float] = {}
_dummy_bcrypt_hash: str | None = None


class TooManyRequestsError(ValueError):
    """ข้อผิดพลาดเมื่อทำรายการเกินอัตราที่กำหนด (HTTP 429)"""
    status_code = 429


def _get_dummy_bcrypt_hash() -> str:
    global _dummy_bcrypt_hash
    if not _dummy_bcrypt_hash:
        _dummy_bcrypt_hash = auth_service.hash_password("tonmakha-dummy-password-for-timing")
    return _dummy_bcrypt_hash


def reset_member_login_rate_limits() -> None:
    with _login_rate_lock:
        _member_login_failures.clear()
        _member_login_lockouts.clear()


def _check_member_login_lockout(client_ip: str, email: str, now: float | None = None) -> None:
    key = ((client_ip or "unknown").strip(), (email or "").strip().lower())
    ts = float(now if now is not None else time.time())
    with _login_rate_lock:
        locked_until = _member_login_lockouts.get(key)
        if locked_until and ts < locked_until:
            remain = max(1, int(round((locked_until - ts) / 60)))
            raise TooManyRequestsError(
                f"คุณกรอกรหัสผ่านผิดเกินกำหนด กรุณารออีกประมาณ {remain} นาทีแล้วลองใหม่"
            )
        if locked_until and ts >= locked_until:
            _member_login_lockouts.pop(key, None)
            _member_login_failures.pop(key, None)


def _record_member_login_failure(client_ip: str, email: str, now: float | None = None) -> None:
    key = ((client_ip or "unknown").strip(), (email or "").strip().lower())
    ts = float(now if now is not None else time.time())
    window = float(getattr(config, "LOGIN_WINDOW_SECONDS", 600))
    max_attempts = int(getattr(config, "LOGIN_MAX_ATTEMPTS", 5))
    lockout_sec = float(getattr(config, "LOGIN_LOCKOUT_SECONDS", 300))
    with _login_rate_lock:
        attempts = [t for t in _member_login_failures.get(key, []) if ts - t < window]
        attempts.append(ts)
        _member_login_failures[key] = attempts
        if len(attempts) >= max_attempts:
            _member_login_lockouts[key] = ts + lockout_sec


def _clear_member_login_failures(client_ip: str, email: str) -> None:
    key = ((client_ip or "unknown").strip(), (email or "").strip().lower())
    with _login_rate_lock:
        _member_login_failures.pop(key, None)
        _member_login_lockouts.pop(key, None)


DEFAULT_SAMPLE_HISTORY = [
    {
        "id": "INV-20261018-04",
        "table_name": "โต๊ะ 4",
        "visited_at": "2026-10-18 19:20:00",
        "total": 633.70,
        "bill": {
            "weigh_entries": [
                {
                    "id": 901,
                    "name_snapshot": "หมูสามชั้น + หมูสไลซ์",
                    "weight_grams": 1600,
                    "price_per_kg": 299.0,
                    "amount": 478.40,
                }
            ],
            "orders": [
                {
                    "id": 88,
                    "status": "served",
                    "items": [
                        {"id": 1, "name_snapshot": "ผักรวม", "quantity": 2, "line_total": 80.0},
                        {"id": 2, "name_snapshot": "น้ำเปล่า", "quantity": 2, "line_total": 30.0},
                    ],
                }
            ],
            "subtotal": 588.40,
            "discount": 50.0,
            "promo_name": "โค้ดสมาชิก TONMAKHA50",
            "service_charge_percent": 10,
            "service_charge": 53.84,
            "vat_percent": 7,
            "vat": 41.46,
            "total": 633.70,
            "payment_method": "cash",
            "payment_method_th": "เงินสด",
            "amount_received": 700.0,
            "change_amount": 66.30,
            "paid_at": "2026-10-18 20:45:00",
        },
    },
    {
        "id": "INV-20261010-02",
        "table_name": "โต๊ะ 2",
        "visited_at": "2026-10-10 18:15:00",
        "total": 469.62,
        "bill": {
            "weigh_entries": [
                {
                    "id": 850,
                    "name_snapshot": "เนื้อวัวสไลซ์",
                    "weight_grams": 1000,
                    "price_per_kg": 299.0,
                    "amount": 299.0,
                }
            ],
            "orders": [
                {
                    "id": 64,
                    "status": "served",
                    "items": [
                        {"id": 1, "name_snapshot": "วุ้นเส้น", "quantity": 2, "line_total": 40.0},
                        {"id": 2, "name_snapshot": "โค้ก", "quantity": 3, "line_total": 60.0},
                    ],
                }
            ],
            "subtotal": 399.0,
            "discount": 0.0,
            "promo_name": None,
            "service_charge_percent": 10,
            "service_charge": 39.90,
            "vat_percent": 7,
            "vat": 30.72,
            "total": 469.62,
            "payment_method": "transfer",
            "payment_method_th": "โอน/PromptPay",
            "amount_received": 469.62,
            "change_amount": 0.0,
            "paid_at": "2026-10-10 19:40:00",
        },
    },
    {
        "id": "INV-20261002-07",
        "table_name": "โต๊ะ 7",
        "visited_at": "2026-10-02 20:05:00",
        "total": 868.39,
        "bill": {
            "weigh_entries": [
                {
                    "id": 790,
                    "name_snapshot": "หมูสามชั้น + เนื้อวัวสไลซ์",
                    "weight_grams": 2200,
                    "price_per_kg": 299.0,
                    "amount": 657.80,
                }
            ],
            "orders": [
                {
                    "id": 41,
                    "status": "served",
                    "items": [
                        {"id": 1, "name_snapshot": "เบียร์ช้าง", "quantity": 2, "line_total": 140.0},
                        {"id": 2, "name_snapshot": "ไข่ไก่", "quantity": 4, "line_total": 40.0},
                    ],
                }
            ],
            "subtotal": 837.80,
            "discount": 100.0,
            "promo_name": "โค้ดสมาชิก PARTY100",
            "service_charge_percent": 10,
            "service_charge": 73.78,
            "vat_percent": 7,
            "vat": 56.81,
            "total": 868.39,
            "payment_method": "cash",
            "payment_method_th": "เงินสด",
            "amount_received": 1000.0,
            "change_amount": 131.61,
            "paid_at": "2026-10-02 21:50:00",
        },
    },
]

DEFAULT_MEMBERS = [
    {
        "id": 1,
        "name": "สมชาย สายหมูกระทะ",
        "email": "somchai@gmail.com",
        "phone": "081-234-5678",
        "password": "123456",
        "provider": "password",
        "demo": True,
        "email_verified": True,
        "claimed_promos": ["TONMAKHA50"],
        "created_at": "2026-10-01 12:00:00",
        "sample_history": DEFAULT_SAMPLE_HISTORY,
    },
    {
        "id": 2,
        "name": "แพรวา ชอบกินหมู",
        "email": "praewa.google@gmail.com",
        "phone": "089-888-7766",
        "password": "",
        "provider": "google",
        "demo": True,
        "email_verified": True,
        "claimed_promos": [],
        "created_at": "2026-10-12 18:00:00",
        "sample_history": [
            {
                "id": "INV-20261015-01",
                "table_name": "โต๊ะ 1",
                "visited_at": "2026-10-15 18:45:00",
                "total": 528.12,
                "bill": {
                    "weigh_entries": [
                        {
                            "id": 701,
                            "name_snapshot": "หมูสามชั้น + หมูสไลซ์",
                            "weight_grams": 1300,
                            "price_per_kg": 299.0,
                            "amount": 388.70,
                        }
                    ],
                    "orders": [
                        {
                            "id": 50,
                            "status": "served",
                            "items": [
                                {"id": 1, "name_snapshot": "ผักรวม", "quantity": 1, "line_total": 40.0},
                                {"id": 2, "name_snapshot": "โค้ก", "quantity": 1, "line_total": 20.0},
                            ],
                        }
                    ],
                    "subtotal": 448.70,
                    "discount": 0.0,
                    "promo_name": None,
                    "service_charge_percent": 10,
                    "service_charge": 44.87,
                    "vat_percent": 7,
                    "vat": 34.55,
                    "total": 528.12,
                    "payment_method": "transfer",
                    "payment_method_th": "โอน/PromptPay",
                    "amount_received": 528.12,
                    "change_amount": 0.0,
                    "paid_at": "2026-10-15 20:10:00",
                },
            }
        ],
    },
]


def _is_demo_enabled() -> bool:
    return bool(int(getattr(config, "MEMBER_DEMO_ACCOUNTS", 0) or 0))


def _ensure_session_member_cols(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(table_sessions)").fetchall()}
    if "member_id" not in cols:
        conn.execute("ALTER TABLE table_sessions ADD COLUMN member_id INTEGER")
    if "applied_promo_id" not in cols:
        conn.execute("ALTER TABLE table_sessions ADD COLUMN applied_promo_id INTEGER")


def _migrate_member_records(members: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """ย้ายฟิลด์ password ข้อความธรรมดาเป็น password_hash (bcrypt) และทำเครื่องหมาย demo=True ให้บัญชีตัวอย่าง"""
    changed = False
    for m in members:
        if not isinstance(m, dict):
            continue
        email_lower = str(m.get("email") or "").strip().lower()
        if "password" in m:
            raw_pw = str(m.pop("password") or "")
            if raw_pw and not m.get("password_hash"):
                m["password_hash"] = auth_service.hash_password(raw_pw)
            elif "password_hash" not in m:
                m["password_hash"] = ""
            changed = True
        elif "password_hash" not in m:
            m["password_hash"] = ""
            changed = True

        if "demo" not in m and email_lower in DEMO_MEMBER_EMAILS:
            m["demo"] = True
            changed = True
    return members, changed


def _load_raw_members(conn=None) -> list[dict[str, Any]]:
    otp_service.cleanup_legacy_otp_entries(conn=conn)
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (MEMBERS_SETTING_KEY,), conn=conn)
    if row is not None and row["value"]:
        try:
            data = json.loads(row["value"])
            if isinstance(data, list):
                data, changed = _migrate_member_records(data)
                if changed:
                    _save_raw_members(data, conn=conn)
                return data
        except Exception:
            pass

    # ทะเบียนใหม่: เพิ่ม DEFAULT_MEMBERS เฉพาะเมื่อเปิด MEMBER_DEMO_ACCOUNTS=1 เท่านั้น
    if _is_demo_enabled():
        initial = json.loads(json.dumps(DEFAULT_MEMBERS))
        initial, _ = _migrate_member_records(initial)
    else:
        initial = []
    _save_raw_members(initial, conn=conn)
    return initial


def _save_raw_members(members: list[dict[str, Any]], conn=None) -> None:
    raw = json.dumps(members, ensure_ascii=False)
    now = db.now_str()

    def _do(c):
        c.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (MEMBERS_SETTING_KEY, raw, now),
        )

    if conn is not None:
        _do(conn)
    else:
        with db.transaction() as c:
            _do(c)


def _validate_thai_phone(phone: str) -> str:
    clean = (phone or "").strip()
    if not clean:
        raise ValueError("กรุณากรอกเบอร์โทรศัพท์")
    normalized = re.sub(r"[\s\-()]", "", clean)
    if normalized.startswith("+66"):
        normalized = "0" + normalized[3:]
    elif normalized.startswith("66") and len(normalized) in (10, 11):
        normalized = "0" + normalized[2:]
    if not _PHONE_DIGITS_RE.match(normalized):
        raise ValueError("รูปแบบเบอร์โทรศัพท์ไม่ถูกต้อง (กรุณากรอกเบอร์ไทย 9–10 หลัก เช่น 081-234-5678)")
    return clean


def _validate_member_password(password: str, email: str) -> None:
    pw = password or ""
    min_len = int(getattr(config, "MEMBER_MIN_PASSWORD_LENGTH", 8) or 8)
    max_bytes = int(getattr(config, "MEMBER_MAX_PASSWORD_BYTES", 72) or 72)
    if len(pw) < min_len:
        raise ValueError(f"รหัสผ่านต้องมีความยาวอย่างน้อย {min_len} ตัวอักษร")
    if len(pw.encode("utf-8")) > max_bytes:
        raise ValueError(f"รหัสผ่านต้องมีความยาวไม่เกิน {max_bytes} ไบต์")
    if pw.strip().lower() == (email or "").strip().lower():
        raise ValueError("รหัสผ่านต้องไม่ซ้ำกับอีเมลของคุณ")


def _build_member_history(member: dict, conn=None) -> list[dict]:
    """รวมประวัติการทำรายการจากบิลจริงในฐานข้อมูล (ที่ผูกกับ member_id นี้เท่านั้น) + ประวัติตัวอย่างของสมาชิก"""
    mid = int(member["id"])
    history: list[dict] = []

    try:
        rows = db.query_all(
            "SELECT b.id AS bill_id, b.session_id, b.paid_at, b.total, "
            "t.table_no, t.name AS table_name, s.started_at "
            "FROM bills b "
            "JOIN table_sessions s ON s.id = b.session_id "
            "JOIN tables t ON t.id = s.table_id "
            "WHERE s.member_id = ? "
            "ORDER BY b.id DESC",
            (mid,),
            conn=conn,
        )
        for r in rows:
            sid = r["session_id"]
            b_detail = checkout_service.get_bill_detail(sid)
            if b_detail is None:
                continue
            paid_date = (r["paid_at"] or "")[:10].replace("-", "") or "20261025"
            t_no = r["table_no"] or 0
            inv_code = f"INV-{paid_date}-{int(r['bill_id']):02d}"
            tbl_name = "สั่งกลับบ้าน" if t_no == 0 else (r["table_name"] or f"โต๊ะ {t_no}")
            history.append({
                "id": inv_code,
                "session_id": sid,
                "table_name": tbl_name,
                "visited_at": r["paid_at"] or r["started_at"],
                "total": float(b_detail["total"]),
                "bill": b_detail,
            })
    except Exception:
        pass

    for sh in member.get("sample_history") or []:
        history.append(sh)
    return history


def _public_member(member: dict | None, include_history: bool = True, conn=None) -> dict | None:
    if not member:
        return None
    if member.get("demo") and not _is_demo_enabled():
        return None
    out = {
        "id": int(member["id"]),
        "name": member["name"],
        "email": member["email"],
        "phone": member.get("phone") or "-",
        "provider": member.get("provider") or "password",
        "email_verified": bool(member.get("email_verified", True)),
        "claimed_promos": list(member.get("claimed_promos") or []),
        "created_at": member.get("created_at") or "",
    }
    if include_history:
        out["history"] = _build_member_history(member, conn=conn)
    return out


def get_member(member_id: int | None, include_history: bool = True, conn=None) -> dict | None:
    if not member_id:
        return None
    members = _load_raw_members(conn=conn)
    found = next((m for m in members if int(m["id"]) == int(member_id)), None)
    return _public_member(found, include_history=include_history, conn=conn)


def get_member_password_hash(member_id: int | None, conn=None) -> str | None:
    """คืนค่า password_hash ของสมาชิกสำหรับคำนวณลายนิ้วมือคุกกี้ (mfp)
    หากไม่พบสมาชิก บัญชีไม่มีรหัสผ่าน หรือเป็นบัญชีตัวอย่างที่ถูกปิดใช้งาน จะคืน None
    """
    if not member_id:
        return None
    members = _load_raw_members(conn=conn)
    found = next((m for m in members if int(m["id"]) == int(member_id)), None)
    if not found:
        return None
    if found.get("demo") and not _is_demo_enabled():
        return None
    pw_hash = found.get("password_hash") or ""
    return pw_hash if pw_hash else None


def bind_member_to_session(session_id: int | None, member_id: int | None, conn=None) -> None:
    """ผูกหรือยกเลิกการผูกสมาชิกเข้ากับรอบโต๊ะปัจจุบัน"""
    if not session_id:
        return

    def _do(c):
        _ensure_session_member_cols(c)
        if member_id is None:
            c.execute(
                "UPDATE table_sessions SET member_id = NULL, applied_promo_id = NULL WHERE id = ?",
                (int(session_id),),
            )
        else:
            c.execute(
                "UPDATE table_sessions SET member_id = ? WHERE id = ?",
                (int(member_id), int(session_id)),
            )

    if conn is not None:
        _do(conn)
    else:
        with db.transaction() as c:
            _do(c)


def set_session_applied_promo(session_id: int | None, promo_id: int | None, conn=None) -> None:
    """บันทึกโปรโมชันที่สมาชิกกดเลือกใช้ในรอบโต๊ะปัจจุบัน"""
    if not session_id:
        return

    def _do(c):
        _ensure_session_member_cols(c)
        c.execute(
            "UPDATE table_sessions SET applied_promo_id = ? WHERE id = ?",
            (int(promo_id) if promo_id is not None else None, int(session_id)),
        )

    if conn is not None:
        _do(conn)
    else:
        with db.transaction() as c:
            _do(c)


def get_session_member_state(session_id: int | None, conn=None) -> dict:
    """อ่าน member_id และ applied_promo_id ของรอบโต๊ะ"""
    if not session_id:
        return {"member_id": None, "applied_promo_id": None}
    try:
        row = db.query_one("SELECT * FROM table_sessions WHERE id = ?", (int(session_id),), conn=conn)
        if row is None:
            return {"member_id": None, "applied_promo_id": None}
        d = dict(row)
        return {
            "member_id": d.get("member_id"),
            "applied_promo_id": d.get("applied_promo_id"),
        }
    except Exception:
        return {"member_id": None, "applied_promo_id": None}


def send_otp(email: str, now: float | None = None) -> dict:
    """ขั้นที่ 1 ของการสมัครสมาชิก: ตรวจว่าอีเมลยังไม่ถูกใช้งาน แล้วส่งรหัส OTP (purpose='signup') ทางอีเมล"""
    clean_email = otp_service.validate_email_format(email)
    with db.transaction() as conn:
        members = _load_raw_members(conn=conn)
        existing = next((m for m in members if str(m.get("email") or "").strip().lower() == clean_email), None)
        if existing is not None:
            # หากเป็นบัญชีตัวอย่างแต่ปิดโหมดบัญชีตัวอย่างไว้ ก็ถือว่าอีเมลนี้สงวนไว้/มีในทะเบียนแล้ว
            if not existing.get("demo") or _is_demo_enabled():
                raise ValueError("อีเมลนี้สมัครสมาชิกแล้ว กรุณาเข้าสู่ระบบ")
            raise ValueError("อีเมลนี้สมัครสมาชิกแล้ว กรุณาเข้าสู่ระบบ")

    return otp_service.request_otp(clean_email, purpose="signup", now=now)


def login_member(
    identifier: str,
    password: str,
    session_id: int | None = None,
    client_ip: str = "local",
    now: float | None = None,
) -> dict:
    """เข้าสู่ระบบสมาชิกด้วย 'อีเมล + รหัสผ่าน' เท่านั้น
    - คืนข้อความผิดพลาดเดียวกันทุกกรณี ("อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    - ทำ bcrypt เทียบกับแฮชหลอกเมื่อไม่พบอีเมลเพื่อกัน timing attack
    - จำกัดการกรอกผิดต่อ (IP + อีเมล) ตามค่า config.LOGIN_MAX_ATTEMPTS / LOGIN_WINDOW_SECONDS / LOGIN_LOCKOUT_SECONDS
    """
    ident = (identifier or "").strip().lower()
    pw = password or ""

    _check_member_login_lockout(client_ip, ident or "empty", now=now)

    if not ident or not pw or "@" not in ident:
        auth_service.verify_password(pw or "invalid", _get_dummy_bcrypt_hash())
        _record_member_login_failure(client_ip, ident or "empty", now=now)
        raise ValueError(GENERIC_LOGIN_ERROR)

    with db.transaction() as conn:
        members = _load_raw_members(conn=conn)
        found = next(
            (m for m in members if str(m.get("email") or "").strip().lower() == ident),
            None,
        )

        if found is None:
            auth_service.verify_password(pw, _get_dummy_bcrypt_hash())
            _record_member_login_failure(client_ip, ident, now=now)
            raise ValueError(GENERIC_LOGIN_ERROR)

        is_demo = bool(found.get("demo"))
        provider = str(found.get("provider") or "password").strip().lower()
        pw_hash = str(found.get("password_hash") or "")

        if (is_demo and not _is_demo_enabled()) or provider != "password" or not pw_hash:
            auth_service.verify_password(pw, _get_dummy_bcrypt_hash())
            _record_member_login_failure(client_ip, ident, now=now)
            raise ValueError(GENERIC_LOGIN_ERROR)

        if not auth_service.verify_password(pw, pw_hash):
            _record_member_login_failure(client_ip, ident, now=now)
            raise ValueError(GENERIC_LOGIN_ERROR)

        _clear_member_login_failures(client_ip, ident)
        if session_id:
            bind_member_to_session(session_id, found["id"], conn=conn)
        log_service.log_action(
            "member_login",
            f"สมาชิกเข้าสู่ระบบ: {found['name']} ({found['email']})",
            actor="ลูกค้า",
            ref_type="table_session" if session_id else "member",
            ref_id=session_id or found["id"],
            conn=conn,
        )
        return _public_member(found, include_history=True, conn=conn)


def signup_member(
    name: str,
    email: str,
    phone: str,
    password: str,
    password_confirm: str,
    otp_code: str,
    session_id: int | None = None,
    now: float | None = None,
) -> dict:
    """ขั้นที่ 2 ของการสมัครสมาชิก: ตรวจสอบข้อมูล รหัสผ่าน เบอร์โทร และรหัส OTP 6 หลัก แล้วสร้างบัญชีใหม่"""
    clean_name = (name or "").strip()
    clean_email = (email or "").strip().lower()
    clean_phone = (phone or "").strip()
    pw = password or ""
    pw_conf = password_confirm or ""
    clean_otp = (otp_code or "").strip()

    if not clean_name or not clean_email or not clean_phone or not pw or not pw_conf:
        raise ValueError("กรุณากรอกข้อมูลชื่อ อีเมล เบอร์โทร และรหัสผ่านให้ครบทุกช่อง")
    clean_email = otp_service.validate_email_format(clean_email)
    clean_phone = _validate_thai_phone(clean_phone)
    _validate_member_password(pw, clean_email)
    if pw != pw_conf:
        raise ValueError("รหัสผ่านและยืนยันรหัสผ่านไม่ตรงกัน")

    # ตรวจสอบก่อนว่าอีเมลยังไม่ซ้ำ
    with db.transaction() as conn:
        members = _load_raw_members(conn=conn)
        if any(str(m.get("email") or "").strip().lower() == clean_email for m in members):
            raise ValueError("อีเมลนี้สมัครสมาชิกแล้ว กรุณาเข้าสู่ระบบ")

    # ตรวจสอบและใช้รหัส OTP (purpose='signup') แบบอะตอมมิก
    otp_service.verify_and_consume_otp(clean_email, clean_otp, purpose="signup", now=now)

    with db.transaction() as conn:
        members = _load_raw_members(conn=conn)
        if any(str(m.get("email") or "").strip().lower() == clean_email for m in members):
            raise ValueError("อีเมลนี้สมัครสมาชิกแล้ว กรุณาเข้าสู่ระบบ")

        next_id = max((int(m["id"]) for m in members), default=0) + 1
        new_member = {
            "id": next_id,
            "name": clean_name,
            "email": clean_email,
            "phone": clean_phone,
            "password_hash": auth_service.hash_password(pw),
            "provider": "password",
            "email_verified": True,
            "demo": False,
            "claimed_promos": [],
            "created_at": db.now_str(),
            "sample_history": [],
        }
        members.append(new_member)
        _save_raw_members(members, conn=conn)

        if session_id:
            bind_member_to_session(session_id, next_id, conn=conn)
        log_service.log_action(
            "member_signup",
            f"สมัครสมาชิกใหม่: {clean_name} ({clean_email})",
            actor="ลูกค้า",
            ref_type="table_session" if session_id else "member",
            ref_id=session_id or next_id,
            conn=conn,
        )
        return _public_member(new_member, include_history=True, conn=conn)


def request_password_reset(email: str, now: float | None = None) -> dict:
    """ขั้นที่ 1 ของการลืมรหัสผ่าน: ส่งรหัส OTP (purpose='reset') เฉพาะเมื่อมีบัญชีสมาชิก
    แต่ตอบกลับด้วยข้อความและโครงสร้างเดียวกันเสมอเพื่อไม่เปิดเผยว่าอีเมลใดเป็นสมาชิก
    """
    clean_email = otp_service.validate_email_format(email)
    with db.transaction() as conn:
        members = _load_raw_members(conn=conn)
        found = next(
            (m for m in members if str(m.get("email") or "").strip().lower() == clean_email),
            None,
        )
        can_reset = (
            found is not None
            and (not found.get("demo") or _is_demo_enabled())
            and str(found.get("provider") or "password").strip().lower() == "password"
        )

    if can_reset:
        otp_service.request_otp(clean_email, purpose="reset", now=now)

    return {
        "email": otp_service.mask_email(clean_email),
        "expires_in_minutes": otp_service.OTP_EXPIRES_MINUTES,
        "cooldown_seconds": otp_service.OTP_RESEND_COOLDOWN_SECONDS,
        "message": RESET_START_MESSAGE,
    }


def reset_member_password(
    email: str,
    otp_code: str,
    new_password: str,
    new_password_confirm: str,
    now: float | None = None,
) -> dict:
    """ขั้นที่ 2 ของการลืมรหัสผ่าน: ตรวจสอบรหัส OTP (purpose='reset') และตั้งรหัสผ่านใหม่"""
    clean_email = otp_service.validate_email_format(email)
    pw = new_password or ""
    pw_conf = new_password_confirm or ""
    clean_otp = (otp_code or "").strip()

    if not pw or not pw_conf:
        raise ValueError("กรุณากรอกรหัสผ่านใหม่และยืนยันรหัสผ่านให้ครบถ้วน")
    _validate_member_password(pw, clean_email)
    if pw != pw_conf:
        raise ValueError("รหัสผ่านใหม่และยืนยันรหัสผ่านไม่ตรงกัน")

    # ตรวจสอบและใช้รหัส OTP (purpose='reset')
    otp_service.verify_and_consume_otp(clean_email, clean_otp, purpose="reset", now=now)

    with db.transaction() as conn:
        members = _load_raw_members(conn=conn)
        found = next(
            (m for m in members if str(m.get("email") or "").strip().lower() == clean_email),
            None,
        )
        if found is None or (found.get("demo") and not _is_demo_enabled()):
            raise ValueError("ไม่สามารถตั้งรหัสผ่านใหม่ได้ กรุณาตรวจสอบข้อมูลอีกครั้ง")

        found.pop("password", None)
        found["password_hash"] = auth_service.hash_password(pw)
        found["provider"] = "password"
        _save_raw_members(members, conn=conn)

        log_service.log_action(
            "member_password_reset",
            f"สมาชิกตั้งรหัสผ่านใหม่สำเร็จ ({found['email']})",
            actor="ลูกค้า",
            ref_type="member",
            ref_id=found["id"],
            conn=conn,
        )

    _clear_member_login_failures("local", clean_email)
    return {
        "ok": True,
        "message": "ตั้งรหัสผ่านใหม่สำเร็จ กรุณาเข้าสู่ระบบด้วยรหัสผ่านใหม่ของคุณ",
    }


def claim_member_promo(member_id: int, code: str) -> dict:
    """สมาชิกกดเก็บโค้ดส่วนลด"""
    clean_code = (code or "").strip().upper()
    if not clean_code:
        raise ValueError("กรุณาระบุโค้ดส่วนลด")
    promo = promo_service.get_promo_by_code(clean_code)
    if promo is None or not promo["active"]:
        raise ValueError("ไม่พบโค้ดส่วนลดนี้ หรือโปรโมชั่นปิดใช้งานแล้ว")

    with db.transaction() as conn:
        members = _load_raw_members(conn=conn)
        found = next((m for m in members if int(m["id"]) == int(member_id)), None)
        if found is None or (found.get("demo") and not _is_demo_enabled()):
            raise ValueError("ไม่พบบัญชีสมาชิก กรุณาเข้าสู่ระบบใหม่")
        claimed = list(found.get("claimed_promos") or [])
        if promo["code"] not in claimed:
            claimed.append(promo["code"])
            found["claimed_promos"] = claimed
            _save_raw_members(members, conn=conn)
        return _public_member(found, include_history=True, conn=conn)


def apply_member_promo(
    member_id: int,
    code: str | None,
    session_id: int | None,
    subtotal: float = 0.0,
) -> dict:
    """สมาชิกกดใช้โค้ดส่วนลด (หรือส่ง code=None/'' เพื่อยกเลิกการใช้โค้ด)"""
    clean_code = (code or "").strip().upper()
    if not clean_code:
        if session_id:
            set_session_applied_promo(session_id, None)
        return {"applied_promo_code": None, "applied_promo_id": None}

    promo = promo_service.get_promo_by_code(clean_code)
    if promo is None or not promo["active"]:
        raise ValueError("ไม่พบโค้ดส่วนลดนี้ หรือโปรโมชั่นปิดใช้งานแล้ว")
    if not promo_service.is_in_period(promo):
        raise ValueError(f"โค้ด \"{clean_code}\" ไม่อยู่ในช่วงเวลาที่ใช้ได้")
    if subtotal > 0 and subtotal < float(promo["min_amount"] or 0):
        raise ValueError(f"โค้ด \"{clean_code}\" ต้องมียอดอาหารขั้นต่ำ {promo['min_amount']:,.2f} บาท")

    with db.transaction() as conn:
        members = _load_raw_members(conn=conn)
        found = next((m for m in members if int(m["id"]) == int(member_id)), None)
        if found is None or (found.get("demo") and not _is_demo_enabled()):
            raise ValueError("ไม่พบบัญชีสมาชิก กรุณาเข้าสู่ระบบใหม่")
        claimed = list(found.get("claimed_promos") or [])
        if promo["code"] not in claimed:
            claimed.append(promo["code"])
            found["claimed_promos"] = claimed
            _save_raw_members(members, conn=conn)
        if session_id:
            bind_member_to_session(session_id, member_id, conn=conn)
            set_session_applied_promo(session_id, promo["id"], conn=conn)

    return {
        "applied_promo_code": promo["code"],
        "applied_promo_id": promo["id"],
        "promo": promo,
    }


def list_member_promotions_for_customer() -> list[dict]:
    """คืนรายการโปรโมชั่นสำหรับสมาชิกที่เปิดใช้งานและอยู่ในช่วงเวลาสำหรับแสดงในแท็บ 🎁 โปรโมชันสมาชิก"""
    out = []
    for p in promo_service.list_promos(include_inactive=False, target="member"):
        if not promo_service.is_in_period(p):
            continue
        out.append({
            "id": p["id"],
            "code": p["code"],
            "title": p["name"],
            "description": p["description"],
            "discount_type": p["promo_type"],
            "discount_value": p["value"],
            "min_subtotal": p["min_amount"],
            "label": p["label"],
        })
    return out


def list_members_with_active_status() -> list[dict]:
    """คืนรายชื่อสมาชิกทั้งหมดสำหรับเจ้าของร้าน (แสดงเฉพาะ ชื่อ, อีเมล, เบอร์โทร และสถานะกำลังใช้งาน)
    โดยเรียงสมาชิกที่กำลังกินอยู่ (มีรอบโต๊ะสถานะ pending / open / awaiting_payment) ไว้บนสุดเสมอ
    ไม่คืน password, password_hash หรือข้อมูล OTP เด็ดขาด"""
    with db.transaction() as conn:
        _ensure_session_member_cols(conn)
        members = _load_raw_members(conn=conn)
        active_rows = db.query_all(
            "SELECT s.id AS session_id, s.status, s.member_id, t.table_no, t.name AS table_name "
            "FROM table_sessions s "
            "JOIN tables t ON t.id = s.table_id "
            "WHERE s.status IN ('pending', 'open', 'awaiting_payment') AND s.member_id IS NOT NULL "
            "ORDER BY s.id DESC",
            conn=conn,
        )

    active_by_member: dict[int, dict] = {}
    for r in active_rows:
        mid = int(r["member_id"])
        if mid not in active_by_member:
            active_by_member[mid] = dict(r)

    result = []
    for m in members:
        mid = int(m["id"])
        act = active_by_member.get(mid)
        is_eating = act is not None
        table_label = f"โต๊ะ {act['table_no']}" if act and act.get("table_no") else None
        status_text = f"กำลังใช้งาน ({table_label})" if is_eating and table_label else ("กำลังใช้งาน" if is_eating else "ไม่ได้ใช้งาน")
        result.append({
            "id": mid,
            "name": m["name"],
            "email": m["email"],
            "phone": m.get("phone") or "-",
            "is_active_dining": is_eating,
            "table_no": act["table_no"] if act else None,
            "table_label": table_label,
            "status_text": status_text,
        })

    # เรียงสมาชิกที่กำลังใช้งานอยู่ขึ้นบนสุด ตามด้วยชื่อ/รหัส
    result.sort(key=lambda x: (0 if x["is_active_dining"] else 1, x["id"]))
    return result
