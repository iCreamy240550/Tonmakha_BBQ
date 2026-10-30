"""server/routes/auth.py — API เข้าสู่ระบบ / ออกจากระบบ / ข้อมูลผู้ใช้งานปัจจุบันของพนักงานและเจ้าของร้าน"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import config
from server import auth as server_auth
from server.deps import require_staff, require_staff_ip
from services import auth_service, log_service

router = APIRouter(prefix="/api/staff", tags=["auth"], dependencies=[Depends(require_staff_ip)])


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict:
    username = (body.username or "").strip()
    password = body.password or ""
    if not username or not password:
        raise ValueError("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน")

    server_auth.check_login_rate_limit(request, username)
    user = auth_service.login(username, password)
    if user is None:
        server_auth.record_login_failure(request, username)
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    server_auth.clear_login_failures(request, username)
    server_auth.set_staff_cookie(response, request, user["id"])
    default_page = "dashboard" if user["role"] == config.ROLE_OWNER else "tables"
    return {"user": user, "default_page": default_page}


@router.post("/logout")
def logout(response: Response, user: dict = Depends(require_staff)) -> dict:
    try:
        log_service.log_action("logout", f"{user['display_name']} ออกจากระบบ", user_id=user["id"])
    except Exception:
        pass
    server_auth.clear_staff_cookie(response)
    return {"ok": True}


@router.get("/me")
def get_me(request: Request) -> dict:
    token = request.cookies.get(config.STAFF_COOKIE_NAME)
    user = server_auth.verify_staff_token(token)
    if user is None:
        return {"authenticated": False, "user": None}
    default_page = "dashboard" if user["role"] == config.ROLE_OWNER else "tables"
    return {"authenticated": True, "user": user, "default_page": default_page}
