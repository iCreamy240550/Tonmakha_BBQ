"""server/auth.py — ระบบความปลอดภัย: คุกกี้เซ็นลายเซ็น HMAC (พนักงาน/เจ้าของ + ลูกค้า),
ตรวจเครื่อง/IP ที่เข้าหน้าพนักงาน, ตรวจ CSRF Origin, และจำกัดการเดารหัส (Rate Limit)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response

import config
from database import db
from services import settings_service


def get_secret_key() -> bytes:
    """อ่านหรือสร้างรหัสลับจากไฟล์ web_secret.key (ไม่เก็บใน DB ไม่ log)"""
    secret_file = getattr(config, "SECRET_FILE", config.BASE_DIR / "web_secret.key")
    try:
        text = secret_file.read_text(encoding="utf-8").strip()
        if len(text) >= 32:
            return text.encode("utf-8")
    except FileNotFoundError:
        pass
    text = secrets.token_hex(32)
    secret_file.write_text(text, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    return text.encode("utf-8")


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode((text + pad).encode("ascii"))


def sign_payload(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64_encode(raw)
    sig = hmac.new(get_secret_key(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64_encode(sig)}"


def verify_payload(token: str | None) -> dict | None:
    if not token or not isinstance(token, str) or "." not in token:
        return None
    try:
        body, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(get_secret_key(), body.encode("ascii"), hashlib.sha256).digest()
        given_sig = _b64_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, given_sig):
            return None
        data = json.loads(_b64_decode(body).decode("utf-8"))
        if not isinstance(data, dict):
            return None
        exp = data.get("exp")
        if exp is not None and time.time() > float(exp):
            return None
        return data
    except Exception:
        return None


def _password_fingerprint(password_hash: str) -> str:
    return hmac.new(get_secret_key(), (password_hash or "").encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def get_user_pw_fingerprint(user_id: int) -> str | None:
    row = db.query_one("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    if row is None:
        return None
    return _password_fingerprint(row["password_hash"])


def get_member_pw_fingerprint(member_id: int | None) -> str | None:
    """คำนวณลายนิ้วมือรหัสผ่านของสมาชิก (mfp) จาก password_hash ปัจจุบันในทะเบียนสมาชิก"""
    if not member_id:
        return None
    from services import member_service
    pw_hash = member_service.get_member_password_hash(member_id)
    if not pw_hash:
        return None
    return _password_fingerprint(pw_hash)


def verify_member_cookie_fingerprint(member_id: int | None, mfp: str | None) -> bool:
    if not member_id or not mfp or not isinstance(mfp, str):
        return False
    expected = get_member_pw_fingerprint(member_id)
    if not expected:
        return False
    return hmac.compare_digest(mfp, expected)


def create_staff_token(user_id: int, ttl: int = config.STAFF_SESSION_TTL_SECONDS) -> str:
    fp = get_user_pw_fingerprint(user_id) or ""
    now = int(time.time())
    return sign_payload({
        "uid": int(user_id),
        "iat": now,
        "exp": now + int(ttl),
        "pfp": fp,
    })


def verify_staff_token(token: str | None) -> dict | None:
    data = verify_payload(token)
    if not data:
        return None
    uid = data.get("uid")
    if not isinstance(uid, int) or isinstance(uid, bool):
        return None
    row = db.query_one(
        "SELECT id, username, display_name, role, active, created_at, password_hash FROM users WHERE id = ?",
        (uid,),
    )
    if row is None or not row["active"]:
        return None
    if not hmac.compare_digest(data.get("pfp") or "", _password_fingerprint(row["password_hash"])):
        return None
    user = dict(row)
    user.pop("password_hash", None)
    return user


def set_staff_cookie(response: Response, request: Request, user_id: int) -> None:
    token = create_staff_token(user_id)
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key=config.STAFF_COOKIE_NAME,
        value=token,
        max_age=config.STAFF_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=is_https,
        path="/",
    )


def clear_staff_cookie(response: Response) -> None:
    response.delete_cookie(key=config.STAFF_COOKIE_NAME, path="/", samesite="strict", httponly=True)


class CustomerCookieStorage(dict):
    def __init__(self, initial: dict | None = None):
        super().__init__(initial or {})
        self.dirty = False

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.dirty = True

    def __delitem__(self, key):
        super().__delitem__(key)
        self.dirty = True

    def pop(self, key, *args):
        self.dirty = True
        return super().pop(key, *args)

    def clear(self):
        super().clear()
        self.dirty = True


def load_customer_storage(request: Request) -> CustomerCookieStorage:
    token = request.cookies.get(config.CUSTOMER_COOKIE_NAME)
    data = verify_payload(token)
    if not data or not isinstance(data.get("st"), dict):
        return CustomerCookieStorage()
    return CustomerCookieStorage(data["st"])


def save_customer_storage(response: Response, request: Request, storage: CustomerCookieStorage) -> None:
    now = int(time.time())
    clean_state = {
        k: v for k, v in storage.items()
        if k in ("device_id", "session_id", "cart", "member_id", "mfp", "applied_promo_code")
    }
    token = sign_payload({
        "st": clean_state,
        "exp": now + config.CUSTOMER_SESSION_TTL_SECONDS,
    })
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key=config.CUSTOMER_COOKIE_NAME,
        value=token,
        max_age=config.CUSTOMER_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=is_https,
        path="/",
    )


_PROXY_HEADERS = ("x-forwarded-for", "forwarded", "cf-connecting-ip", "x-real-ip")


def is_local_request(request: Request) -> bool:
    for h in _PROXY_HEADERS:
        if request.headers.get(h):
            return False
    client_host = (request.client.host if request.client else "") or ""
    if client_host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True
    try:
        ip = ipaddress.ip_address(client_host)
        return ip.is_loopback
    except ValueError:
        return False


def _allowed_networks() -> list:
    raw_items = list(getattr(config, "STAFF_ALLOWED_NETS", ("127.0.0.1/32", "::1/128")))
    try:
        extra = settings_service.get_setting("staff_allowed_nets", "") or ""
        for part in extra.split(","):
            part = part.strip()
            if part:
                raw_items.append(part)
    except Exception:
        pass
    nets = []
    for item in raw_items:
        item = str(item).strip()
        if not item or item in ("localhost", "testclient"):
            continue
        try:
            if "/" in item:
                nets.append(ipaddress.ip_network(item, strict=False))
            else:
                ip = ipaddress.ip_address(item)
                nets.append(ipaddress.ip_network(f"{ip}/{ip.max_prefixlen}", strict=False))
        except ValueError:
            continue
    return nets


def is_staff_network_allowed(request: Request) -> bool:
    for h in _PROXY_HEADERS:
        if request.headers.get(h):
            return False
    client_host = (request.client.host if request.client else "") or ""
    if client_host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True
    try:
        ip = ipaddress.ip_address(client_host)
        if ip.is_loopback:
            return True
        for net in _allowed_networks():
            if ip in net:
                return True
    except ValueError:
        pass
    return False


def enforce_staff_network(request: Request) -> None:
    if not is_staff_network_allowed(request):
        raise HTTPException(
            status_code=403,
            detail="ไม่อนุญาตให้เข้าหน้าพนักงาน/เจ้าของร้านจากเครือข่ายภายนอก (อนุญาตเฉพาะเครื่องที่รันเซิร์ฟเวอร์)",
        )


_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def verify_csrf_origin(request: Request) -> None:
    if request.method.upper() in _SAFE_METHODS:
        return
    host = (request.headers.get("host") or "").strip().lower()
    origin = (request.headers.get("origin") or "").strip()
    referer = (request.headers.get("referer") or "").strip()

    if origin:
        if origin.lower() == "null":
            raise HTTPException(status_code=403, detail="ปฏิเสธคำขอ: Origin ไม่ถูกต้อง")
        parsed = urlparse(origin)
        origin_host = (parsed.netloc or "").lower()
        if host and origin_host != host:
            raise HTTPException(status_code=403, detail="ปฏิเสธคำขอ: Origin ไม่ตรงกับเซิร์ฟเวอร์")
    elif referer:
        parsed = urlparse(referer)
        ref_host = (parsed.netloc or "").lower()
        if host and ref_host != host:
            raise HTTPException(status_code=403, detail="ปฏิเสธคำขอ: Referer ไม่ตรงกับเซิร์ฟเวอร์")

    ct = (request.headers.get("content-type") or "").lower()
    cl = request.headers.get("content-length")
    has_body = cl not in (None, "0", "")
    if has_body and ct:
        if not (
            ct.startswith("application/json")
            or ct.startswith("multipart/form-data")
        ):
            raise HTTPException(status_code=400, detail="รูปแบบคำขอไม่ถูกต้อง (ต้องเป็น JSON หรือ multipart)")


_login_failures: dict[tuple[str, str], list[float]] = {}
_login_lockouts: dict[tuple[str, str], float] = {}
_scan_attempts: dict[str, list[float]] = {}


def reset_rate_limits() -> None:
    _login_failures.clear()
    _login_lockouts.clear()
    _scan_attempts.clear()
    try:
        from services import member_service, otp_service
        otp_service.reset_ip_rate_limits()
        member_service.reset_member_login_rate_limits()
    except Exception:
        pass


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return (request.client.host if request.client else "unknown") or "unknown"


def check_login_rate_limit(request: Request, username: str) -> None:
    key = (_client_ip(request), (username or "").strip().lower())
    now = time.time()
    locked_until = _login_lockouts.get(key)
    if locked_until and now < locked_until:
        remain = max(1, int(round((locked_until - now) / 60)))
        raise HTTPException(
            status_code=429,
            detail=f"คุณกรอกรหัสผ่านผิดเกินกำหนด กรุณารออีกประมาณ {remain} นาทีแล้วลองใหม่",
        )
    if locked_until and now >= locked_until:
        _login_lockouts.pop(key, None)
        _login_failures.pop(key, None)


def record_login_failure(request: Request, username: str) -> None:
    key = (_client_ip(request), (username or "").strip().lower())
    now = time.time()
    window = config.LOGIN_WINDOW_SECONDS
    attempts = [t for t in _login_failures.get(key, []) if now - t < window]
    attempts.append(now)
    _login_failures[key] = attempts
    if len(attempts) >= config.LOGIN_MAX_ATTEMPTS:
        _login_lockouts[key] = now + config.LOGIN_LOCKOUT_SECONDS


def clear_login_failures(request: Request, username: str) -> None:
    key = (_client_ip(request), (username or "").strip().lower())
    _login_failures.pop(key, None)
    _login_lockouts.pop(key, None)


def check_scan_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    now = time.time()
    window = config.SCAN_WINDOW_SECONDS
    attempts = [t for t in _scan_attempts.get(ip, []) if now - t < window]
    if len(attempts) >= config.SCAN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="สแกน QR ถี่เกินไป กรุณารอสักครู่แล้วลองใหม่อีกครั้ง",
        )
    attempts.append(now)
    _scan_attempts[ip] = attempts
