"""server/routes/takeaway.py — API หน้าสั่งกลับบ้าน (Takeaway POS) สำหรับพนักงานและเจ้าของร้าน"""
from __future__ import annotations

import base64
from io import BytesIO

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.deps import require_staff
from server.helpers import money
from services import checkout_service, qr_service, takeaway_service

router = APIRouter(prefix="/api/staff/takeaway", tags=["takeaway"])


class TakeawayItemInput(BaseModel):
    menu_item_id: int
    quantity: int


class TakeawayPreviewRequest(BaseModel):
    weigh_grams: int = 0
    items: list[TakeawayItemInput] = []
    promo_id: int | None = None


class TakeawayPayRequest(BaseModel):
    weigh_grams: int
    items: list[TakeawayItemInput] = []
    payment_method: str
    promo_id: int | None = None
    amount_received: float | str | None = None
    note: str | None = None


def _build_promptpay_info(total: float) -> dict:
    if total <= 0:
        return {
            "valid": False,
            "data_url": None,
            "payload": None,
            "amount": 0.0,
            "amount_text": "0.00",
            "promptpay_id": "",
            "promptpay_name": "",
            "status": "empty",
            "status_th": "ยังไม่มีรายการ",
            "error": None,
        }
    try:
        qr_data = qr_service.generate_promptpay_qr(total)
        buf = BytesIO()
        qr_data["image"].resize((200, 200)).save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return {
            "valid": True,
            "data_url": f"data:image/png;base64,{b64}",
            "payload": qr_data["payload"],
            "amount": qr_data["amount"],
            "amount_text": qr_data["amount_text"],
            "promptpay_id": qr_data["promptpay_id"],
            "promptpay_name": qr_data["promptpay_name"],
            "status": qr_data["status"],
            "status_th": qr_data["status_th"],
            "error": None,
        }
    except ValueError as e:
        return {
            "valid": False,
            "data_url": None,
            "payload": None,
            "amount": total,
            "amount_text": money(total),
            "promptpay_id": "",
            "promptpay_name": "",
            "status": "invalid",
            "status_th": "ข้อมูล PromptPay ไม่ถูกต้อง",
            "error": str(e),
        }


@router.get("")
def get_takeaway_state(_user: dict = Depends(require_staff)) -> dict:
    cat = takeaway_service.get_takeaway_catalog()
    rate = cat["rate"]
    if rate == int(rate):
        rate_text = f"กิโลกรัมละ {int(rate):,} บาท"
    else:
        rate_text = f"กิโลกรัมละ {rate:,.2f} บาท"
    return {
        **cat,
        "rate_text": rate_text,
    }


@router.post("/preview")
def preview_takeaway_bill(body: TakeawayPreviewRequest, _user: dict = Depends(require_staff)) -> dict:
    raw_items = [{"menu_item_id": it.menu_item_id, "quantity": it.quantity} for it in body.items if it.quantity > 0]
    prev = takeaway_service.calculate_preview(
        weigh_grams=body.weigh_grams,
        items=raw_items,
        promo_id=body.promo_id,
    )
    promptpay = _build_promptpay_info(prev["total"]) if prev["total"] > 0 else None
    return {
        **prev,
        "promptpay": promptpay,
    }


@router.post("/pay")
def pay_takeaway_bill(body: TakeawayPayRequest, user: dict = Depends(require_staff)) -> dict:
    raw_items = [{"menu_item_id": it.menu_item_id, "quantity": it.quantity} for it in body.items if it.quantity > 0]
    res = takeaway_service.checkout_takeaway(
        weigh_grams=body.weigh_grams,
        items=raw_items,
        payment_method=body.payment_method,
        user_id=user["id"],
        promo_id=body.promo_id,
        amount_received=body.amount_received if body.amount_received is not None else checkout_service._UNSET,
        note=body.note,
    )
    return {
        **res,
        "message": f"บันทึกสั่งกลับบ้านและชำระเงินเรียบร้อยแล้ว ({res['receipt_info']['method_th']})",
    }
