"""server/routes/weigh.py — API หน้าชั่งน้ำหนัก"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import config
from server.deps import require_staff
from server.helpers import baht, fmt_time, money, weight_text
from services import table_service, weigh_service

router = APIRouter(prefix="/api/staff/weigh", tags=["weigh"])


class AddWeighRequest(BaseModel):
    session_id: int
    weight_grams: int
    menu_item_id: int | None = None


class CancelWeighRequest(BaseModel):
    reason: str = ""


def _format_rate_text(rate: float) -> str:
    if rate == int(rate):
        return f"กิโลกรัมละ {int(rate):,} บาท"
    return f"กิโลกรัมละ {rate:,.2f} บาท"


@router.get("")
def get_weigh_state(session_id: int | None = None, _user: dict = Depends(require_staff)) -> dict:
    rate = weigh_service.get_price_per_kg()
    open_tables = [
        {"table_no": t["table_no"], "name": t["name"], "session_id": t["session_id"], "label": f"โต๊ะ {t['table_no']}"}
        for t in table_service.list_tables_with_status()
        if t["status"] == config.SESSION_OPEN and t["session_id"] is not None
    ]
    valid_sids = {t["session_id"] for t in open_tables}
    active_sid = session_id if session_id in valid_sids else (open_tables[0]["session_id"] if open_tables else None)

    entries = []
    total = 0.0
    first_weigh = True
    if active_sid is not None:
        first_weigh = weigh_service.is_first_weigh(active_sid)
        total = weigh_service.session_total(active_sid)
        for e in weigh_service.list_entries(active_sid):
            entries.append({
                **e,
                "time": fmt_time(e["created_at"]),
                "name": e["name_snapshot"],
                "weight": weight_text(e["weight_grams"]),
                "amount_fmt": money(e["amount"]),
            })

    return {
        "rate": rate,
        "rate_text": _format_rate_text(rate),
        "tables": open_tables,
        "selected_session_id": active_sid,
        "is_first_weigh": first_weigh,
        "min_first_weigh_grams": weigh_service.MIN_FIRST_WEIGH_GRAMS,
        "first_weigh_error_msg": weigh_service.FIRST_WEIGH_ERROR_MSG,
        "entries": entries,
        "total": total,
        "total_text": f"รวม {baht(total)}",
    }


@router.post("")
def add_weigh_entry(body: AddWeighRequest, user: dict = Depends(require_staff)) -> dict:
    entry = weigh_service.add_entry(
        body.session_id,
        body.menu_item_id,
        body.weight_grams,
        user_id=user["id"],
    )
    msg = f"บันทึกแล้ว: {entry['name_snapshot']} {weight_text(entry['weight_grams'])} = {baht(entry['amount'])}"
    return {"entry": entry, "message": msg}


@router.post("/{entry_id}/cancel")
def cancel_weigh_entry(entry_id: int, body: CancelWeighRequest, user: dict = Depends(require_staff)) -> dict:
    entry = weigh_service.cancel_entry(entry_id, body.reason, user["id"])
    return {"entry": entry, "message": "ยกเลิกรายการชั่งแล้ว"}
