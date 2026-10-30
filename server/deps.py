"""server/deps.py — FastAPI dependencies สำหรับตรวจสิทธิ์พนักงาน/เจ้าของร้าน และโหลดบริบทของลูกค้า"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

import config
from services import auth_service
from server import auth as server_auth


def require_staff_ip(request: Request) -> None:
    server_auth.enforce_staff_network(request)


def get_current_staff(request: Request, _ip: None = Depends(require_staff_ip)) -> dict:
    token = request.cookies.get(config.STAFF_COOKIE_NAME)
    user = server_auth.verify_staff_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนใช้งาน")
    if not auth_service.has_permission(user, config.ROLE_STAFF):
        raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าใช้งานส่วนนี้")
    return user


def require_staff(user: dict = Depends(get_current_staff)) -> dict:
    return user


def require_owner(user: dict = Depends(get_current_staff)) -> dict:
    if not auth_service.is_owner(user):
        raise HTTPException(status_code=403, detail="หน้านี้สำหรับเจ้าของร้านเท่านั้น")
    return user
