"""services/otp_service.py — แกนจัดการรหัสยืนยันตัวตน OTP (HMAC-SHA256, ธุรกรรมอะตอมมิก, จำกัดอัตราต่ออีเมลและต่อ IP)

กติกาความปลอดภัย:
- สร้างรหัส 6 หลักด้วยโมดูล secrets เท่านั้น
- เก็บเฉพาะค่าแฮช HMAC-SHA256 (คีย์ OTP_SECRET ผสม purpose + อีเมลตัวพิมพ์เล็ก + รหัส) และเปรียบเทียบด้วย hmac.compare_digest
- ล้างรายการ OTP เก่าที่เก็บรหัสข้อความตรง ๆ (มี key "code") ทิ้งทันทีเมื่อโหลด
- อายุรหัส 10 นาที, กรอกผิดได้สูงสุด 5 ครั้งต่อรหัสแล้วรหัสถูกยกเลิกทันที, ส่งซ้ำต้องเว้น 60 วินาที, ขอได้ไม่เกิน 5 ครั้งต่อชั่วโมงต่ออีเมลต่อ purpose
- รหัสใช้ได้ครั้งเดียว (ลบทิ้งเมื่อยืนยันสำเร็จ), ขอรหัสใหม่แล้วรหัสเก่ายกเลิกทันที, ใช้ข้าม purpose หรือข้ามอีเมลไม่ได้
- จำกัดอัตราต่อ IP ในหน่วยความจำ (ไม่เกิน 10 ครั้งใน 10 นาทีต่อ IP) โดยใช้ request.client.host เท่านั้น (ไม่เชื่อ X-Forwarded-For)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from typing import Any

from fastapi import HTTPException, Request

import config
from database import db
from services import email_service

OTP_SETTING_KEY = "members_otp_sessions_json"

OTP_LENGTH = 6
OTP_EXPIRES_MINUTES = 10
OTP_EXPIRES_SECONDS = OTP_EXPIRES_MINUTES * 60
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_SENDS_PER_HOUR = 5
OTP_HOUR_WINDOW_SECONDS = 3600

IP_RATE_LIMIT_MAX_REQUESTS = 10
IP_RATE_LIMIT_WINDOW_SECONDS = 600  # 10 นาที

VALID_PURPOSES = frozenset({"signup", "reset"})
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_otp_lock = threading.Lock()
_ip_rate_lock = threading.Lock()
_ip_requests: dict[str, list[float]] = {}


def validate_email_format(email: str) -> str:
    clean = (email or "").strip().lower()
    if not clean or len(clean) > 254 or not _EMAIL_RE.match(clean):
        raise ValueError("กรุณากรอกอีเมลให้ถูกต้อง")
    return clean


def mask_email(email: str) -> str:
    """ซ่อนอีเมลบางส่วน เช่น somchai@gmail.com -> so***@gmail.com"""
    clean = (email or "").strip().lower()
    if "@" not in clean:
        return "***"
    local, domain = clean.split("@", 1)
    if len(local) <= 1:
        masked_local = f"{local[:1]}***"
    else:
        masked_local = f"{local[:2]}***"
    return f"{masked_local}@{domain}"


def _get_otp_secret_bytes() -> bytes:
    secret = getattr(config, "OTP_SECRET", "") or ""
    if not secret:
        secret = "fallback-ephemeral-secret"
    return secret.encode("utf-8")


def compute_otp_hash(purpose: str, email: str, otp_code: str) -> str:
    """คำนวณแฮช HMAC-SHA256 จากคีย์ OTP_SECRET ผสม purpose + อีเมลตัวพิมพ์เล็ก + รหัส OTP"""
    clean_purpose = (purpose or "").strip().lower()
    clean_email = (email or "").strip().lower()
    clean_code = (otp_code or "").strip()
    msg = f"{clean_purpose}:{clean_email}:{clean_code}".encode("utf-8")
    return hmac.new(_get_otp_secret_bytes(), msg, hashlib.sha256).hexdigest()


def _session_key(purpose: str, email: str) -> str:
    return f"{purpose.strip().lower()}:{email.strip().lower()}"


def _is_valid_new_entry(key: str, val: Any) -> bool:
    if not isinstance(key, str) or ":" not in key:
        return False
    purpose, _ = key.split(":", 1)
    if purpose not in VALID_PURPOSES:
        return False
    if not isinstance(val, dict):
        return False
    # ห้ามมีคีย์ "code" ที่เก็บรหัสข้อความธรรมดาเด็ดขาด
    if "code" in val:
        return False
    return True


def _load_and_sanitize_otp_map(conn) -> tuple[dict[str, dict[str, Any]], bool]:
    """โหลดข้อมูล OTP จากตาราง settings และลบรายการรูปแบบเก่าที่มี key 'code' ทิ้งทันที"""
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (OTP_SETTING_KEY,), conn=conn)
    if row is None or not row["value"]:
        return {}, False
    try:
        raw_data = json.loads(row["value"])
    except Exception:
        return {}, True
    if not isinstance(raw_data, dict):
        return {}, True

    cleaned: dict[str, dict[str, Any]] = {}
    changed = False
    for k, v in raw_data.items():
        if _is_valid_new_entry(k, v):
            cleaned[k] = v
        else:
            changed = True
    return cleaned, changed


def _save_otp_map(otp_map: dict[str, dict[str, Any]], conn) -> None:
    raw = json.dumps(otp_map, ensure_ascii=False)
    now_str = db.now_str()
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (OTP_SETTING_KEY, raw, now_str),
    )


def cleanup_legacy_otp_entries(conn=None) -> None:
    """ล้างรายการ OTP แบบเก่าที่มี key 'code' ออกจากฐานข้อมูล"""
    def _do(c):
        otp_map, changed = _load_and_sanitize_otp_map(c)
        if changed:
            _save_otp_map(otp_map, c)

    with _otp_lock:
        if conn is not None:
            _do(conn)
        else:
            with db.transaction() as c:
                _do(c)


def check_member_ip_rate_limit(request: Request | None, now: float | None = None) -> None:
    """จำกัดอัตราคำขอทุก endpoint ของ OTP/ล็อกอินสมาชิกรวมกันไม่เกิน 10 ครั้งใน 10 นาทีต่อ IP
    ใช้ request.client.host เท่านั้น ห้ามใช้ X-Forwarded-For เด็ดขาด
    """
    if request is None:
        return
    ip = (request.client.host if request.client else "unknown") or "unknown"
    ts = float(now if now is not None else time.time())
    with _ip_rate_lock:
        history = [t for t in _ip_requests.get(ip, []) if ts - t < IP_RATE_LIMIT_WINDOW_SECONDS]
        if len(history) >= IP_RATE_LIMIT_MAX_REQUESTS:
            _ip_requests[ip] = history
            raise HTTPException(
                status_code=429,
                detail="คุณทำรายการเกินจำนวนครั้งที่กำหนด (สูงสุด 10 ครั้งใน 10 นาที) กรุณารอสักครู่แล้วลองใหม่อีกครั้ง",
            )
        history.append(ts)
        _ip_requests[ip] = history


def reset_ip_rate_limits() -> None:
    with _ip_rate_lock:
        _ip_requests.clear()


def request_otp(
    email: str,
    purpose: str = "signup",
    now: float | None = None,
    send_email: bool = True,
) -> dict[str, Any]:
    """สร้างรหัส OTP 6 หลัก บันทึกเฉพาะแฮชลงฐานข้อมูล และส่งอีเมลจริง
    หากส่งอีเมลไม่สำเร็จ จะลบรายการ OTP ที่เพิ่งสร้างทันที (ไม่ค้างและไม่นับโควตา)
    """
    clean_email = validate_email_format(email)
    clean_purpose = (purpose or "").strip().lower()
    if clean_purpose not in VALID_PURPOSES:
        raise ValueError("ประเภทการขอรหัส OTP ไม่ถูกต้อง")

    ts = float(now if now is not None else time.time())
    skey = _session_key(clean_purpose, clean_email)
    otp_code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = compute_otp_hash(clean_purpose, clean_email, otp_code)

    with _otp_lock:
        with db.transaction() as conn:
            otp_map, _ = _load_and_sanitize_otp_map(conn)
            prev_entry = otp_map.get(skey)
            prev_copy = json.loads(json.dumps(prev_entry)) if prev_entry is not None else None

            sent_list = []
            if isinstance(prev_entry, dict):
                raw_sent = prev_entry.get("sent_timestamps") or []
                sent_list = [float(t) for t in raw_sent if ts - float(t) < OTP_HOUR_WINDOW_SECONDS]

            # ตรวจระยะเวลาขอส่งซ้ำ (Cooldown 60 วินาที)
            if sent_list:
                last_sent = max(sent_list)
                elapsed = ts - last_sent
                if 0 <= elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                    remain = max(1, int(round(OTP_RESEND_COOLDOWN_SECONDS - elapsed)))
                    raise ValueError(f"กรุณารออีก {remain} วินาทีก่อนขอรหัส OTP อีกครั้ง")

            # ตรวจโควตาสูงสุด 5 ครั้งต่อชั่วโมงต่ออีเมลต่อ purpose
            if len(sent_list) >= OTP_MAX_SENDS_PER_HOUR:
                raise ValueError("คุณขอรหัส OTP เกิน 5 ครั้งต่อชั่วโมง กรุณารอสักครู่แล้วลองใหม่อีกครั้ง")

            new_sent_list = sent_list + [ts]
            otp_map[skey] = {
                "code_hash": code_hash,
                "created_at": ts,
                "expires_at": ts + OTP_EXPIRES_SECONDS,
                "attempts": 0,
                "sent_timestamps": new_sent_list,
            }
            _save_otp_map(otp_map, conn)

        if send_email:
            try:
                email_service.send_otp_email(
                    to_email=clean_email,
                    otp_code=otp_code,
                    purpose=clean_purpose,
                    expires_minutes=OTP_EXPIRES_MINUTES,
                )
            except Exception:
                # หากส่งอีเมลล้มเหลว ให้ย้อนคืนสถานะ OTP ทันทีเพื่อไม่ให้ค้างและไม่นับโควตา
                with db.transaction() as conn_rb:
                    rb_map, _ = _load_and_sanitize_otp_map(conn_rb)
                    if prev_copy is None:
                        rb_map.pop(skey, None)
                    else:
                        rb_map[skey] = prev_copy
                    _save_otp_map(rb_map, conn_rb)
                raise

    masked = mask_email(clean_email)
    return {
        "email": masked,
        "expires_in_minutes": OTP_EXPIRES_MINUTES,
        "cooldown_seconds": OTP_RESEND_COOLDOWN_SECONDS,
        "message": f"ส่งรหัสยืนยัน (OTP) ไปที่ {masked} แล้ว กรุณาตรวจสอบกล่องจดหมายของคุณ",
    }


def verify_and_consume_otp(
    email: str,
    otp_code: str,
    purpose: str = "signup",
    now: float | None = None,
) -> bool:
    """ตรวจสอบรหัส OTP แบบอะตอมมิก (BEGIN IMMEDIATE + Lock)
    - หากรหัสถูกต้องและยังไม่หมดอายุ: ลบ code_hash ทิ้งทันที (ใช้ซ้ำไม่ได้) และคืน True
    - หากรหัสผิด: เพิ่ม attempts; เมื่อผิดครบ 5 ครั้งจะยกเลิก code_hash ทันที
    """
    clean_email = validate_email_format(email)
    clean_purpose = (purpose or "").strip().lower()
    if clean_purpose not in VALID_PURPOSES:
        raise ValueError("ประเภทการยืนยันรหัส OTP ไม่ถูกต้อง")

    clean_code = (otp_code or "").strip()
    if not clean_code or not clean_code.isdigit() or len(clean_code) != OTP_LENGTH:
        raise ValueError("กรุณากรอกรหัส OTP 6 หลักให้ถูกต้อง")

    ts = float(now if now is not None else time.time())
    skey = _session_key(clean_purpose, clean_email)
    given_hash = compute_otp_hash(clean_purpose, clean_email, clean_code)

    error_to_raise: str | None = None

    with _otp_lock:
        with db.transaction() as conn:
            otp_map, changed = _load_and_sanitize_otp_map(conn)
            entry = otp_map.get(skey)
            if not isinstance(entry, dict) or not entry.get("code_hash"):
                if changed:
                    _save_otp_map(otp_map, conn)
                error_to_raise = "ไม่พบรหัส OTP ที่ใช้งานได้ กรุณากดขอรหัส OTP ใหม่"
            else:
                expires_at = float(entry.get("expires_at") or 0.0)
                attempts = int(entry.get("attempts") or 0)
                stored_hash = str(entry.get("code_hash") or "")

                if ts > expires_at:
                    # หมดอายุ -> ยกเลิกรหัสทันทีแต่คงประวัติการส่งในชั่วโมงนั้นไว้
                    entry["code_hash"] = None
                    entry["attempts"] = 0
                    otp_map[skey] = entry
                    _save_otp_map(otp_map, conn)
                    error_to_raise = "รหัส OTP หมดอายุแล้ว กรุณาขอรหัส OTP ใหม่"
                elif attempts >= OTP_MAX_ATTEMPTS:
                    entry["code_hash"] = None
                    otp_map[skey] = entry
                    _save_otp_map(otp_map, conn)
                    error_to_raise = "รหัส OTP ถูกยกเลิกเนื่องจากกรอกผิดเกินจำนวนครั้งที่กำหนด กรุณาขอรหัสใหม่"
                elif not hmac.compare_digest(stored_hash, given_hash):
                    attempts += 1
                    entry["attempts"] = attempts
                    if attempts >= OTP_MAX_ATTEMPTS:
                        entry["code_hash"] = None
                        error_to_raise = "คุณกรอกรหัส OTP ผิดครบ 5 ครั้ง รหัสนี้ถูกยกเลิกแล้ว กรุณาขอรหัส OTP ใหม่"
                    else:
                        remain = OTP_MAX_ATTEMPTS - attempts
                        error_to_raise = f"รหัส OTP ไม่ถูกต้อง (ลองได้อีก {remain} ครั้ง)"
                    otp_map[skey] = entry
                    _save_otp_map(otp_map, conn)
                else:
                    # รหัสถูกต้อง -> ลบ code_hash ทันทีเพื่อป้องกันการใช้ซ้ำ (คง sent_timestamps ไว้ตรวจโควตารายชั่วโมง)
                    sent_ts = [
                        float(t)
                        for t in (entry.get("sent_timestamps") or [])
                        if ts - float(t) < OTP_HOUR_WINDOW_SECONDS
                    ]
                    if sent_ts:
                        otp_map[skey] = {
                            "code_hash": None,
                            "created_at": 0.0,
                            "expires_at": 0.0,
                            "attempts": 0,
                            "sent_timestamps": sent_ts,
                        }
                    else:
                        otp_map.pop(skey, None)
                    _save_otp_map(otp_map, conn)

    if error_to_raise:
        raise ValueError(error_to_raise)
    return True
