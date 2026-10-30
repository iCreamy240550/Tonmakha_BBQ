"""server/routes/tables.py — API หน้าโต๊ะของพนักงาน"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import config
from server.deps import require_staff
from server.helpers import duration_text, minutes_since, status_color
from services import notice_service, order_service, table_service, weigh_service

router = APIRouter(prefix="/api/staff/tables", tags=["tables"])


class CancelSessionRequest(BaseModel):
    reason: str | None = None


class SendNoticeRequest(BaseModel):
    message: str = ""


@router.get("")
def list_tables_status(_user: dict = Depends(require_staff)) -> dict:
    tables = table_service.list_tables_with_status()
    out = []
    sig_items = []
    for t in tables:
        total = 0.0
        if t["status"] in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT) and t["session_id"]:
            total = round(
                weigh_service.session_total(t["session_id"]) + order_service.session_total(t["session_id"]),
                2,
            )
        mins = minutes_since(t["started_at"])
        dur = duration_text(t["started_at"]) if t["started_at"] else ""
        item = {
            **t,
            "total": total,
            "minutes_since": mins,
            "duration_text": dur,
            "status_color": status_color(t["status"]),
        }
        out.append(item)
        sig_items.append((t["id"], t["status"], t["session_id"], total, mins))

    in_use = sum(1 for t in out if t["status"] != config.TABLE_STATUS_FREE)
    pending = sum(1 for t in out if t["status"] == config.SESSION_PENDING)
    subtitle = f"ใช้งานอยู่ {in_use}/{len(out)} โต๊ะ"
    if pending:
        subtitle += f" · รอยืนยัน {pending} โต๊ะ"

    raw_sig = json.dumps(sig_items, separators=(",", ":"))
    sig = hashlib.sha1(raw_sig.encode("utf-8")).hexdigest()
    return {
        "tables": out,
        "in_use": in_use,
        "pending": pending,
        "total_tables": len(out),
        "subtitle": subtitle,
        "signature": sig,
    }


@router.post("/{session_id}/confirm")
def confirm_table_session(session_id: int, user: dict = Depends(require_staff)) -> dict:
    session = table_service.confirm_session(session_id, user["id"])
    return {"session": session, "message": "ยืนยันโต๊ะแล้ว ลูกค้าสั่งอาหารได้"}


@router.post("/{session_id}/cancel")
def cancel_table_session(session_id: int, body: CancelSessionRequest, user: dict = Depends(require_staff)) -> dict:
    s = table_service.get_session(session_id)
    if s is None:
        raise ValueError("ไม่พบรอบของโต๊ะนี้")
    t = table_service.get_table(s["table_id"])
    table_no = t["table_no"] if t else session_id

    if s["status"] == config.SESSION_PENDING:
        reason = (body.reason or "").strip() or "ไม่มีลูกค้าจริง/สแกนมั่ว"
    else:
        reason = (body.reason or "").strip()
        if not reason:
            raise ValueError("กรุณาระบุเหตุผล")

    cancelled = table_service.cancel_session(
        session_id,
        cancelled_by="staff",
        user_id=user["id"],
        reason=reason,
    )
    return {"session": cancelled, "message": f"ยกเลิกโต๊ะ {table_no} แล้ว"}


@router.post("/{session_id}/notice")
def send_customer_notice(session_id: int, body: SendNoticeRequest, user: dict = Depends(require_staff)) -> dict:
    nid = notice_service.send_message(session_id, body.message, user["id"])
    return {"notice_id": nid, "message": "ส่งข้อความแล้ว"}
