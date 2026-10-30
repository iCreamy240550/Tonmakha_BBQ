"""server/routes/checkout.py — API หน้าเช็คเอาท์"""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from server.deps import require_staff
from server.helpers import money
from services import checkout_service, promo_service, qr_service, table_service

router = APIRouter(prefix="/api/staff/checkout", tags=["checkout"])


class PayRequest(BaseModel):
    payment_method: str
    promo_id: int | None = None
    amount_received: float | str | None = None
    force: bool = False


class ValidateCashRequest(BaseModel):
    total: float
    amount_received: float | str | None = None


def _build_promptpay_info(total: float) -> dict:
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
def get_checkout_state(
    session_id: int | None = None,
    promo_id: int | None = None,
    _user: dict = Depends(require_staff),
) -> dict:
    rows = [
        t for t in table_service.list_tables_with_status()
        if t["status"] in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT) and t["session_id"]
    ]
    valid_sids = {t["session_id"] for t in rows}
    active_sid = session_id if session_id in valid_sids else None

    bill = None
    available_promos = []
    promptpay = None
    selected_promo_id = None
    if active_sid is not None:
        try:
            base_preview = checkout_service.preview(active_sid, promo_id=None)
            avail = promo_service.list_available(base_preview["subtotal"])
            avail_ids = {p["id"] for p in avail}
            if base_preview.get("promo_id") and base_preview["promo_id"] not in avail_ids:
                mp = promo_service.get_promo(base_preview["promo_id"])
                if mp:
                    avail.insert(0, {**mp, "discount": base_preview.get("discount") or 0.0})
            for p in avail:
                available_promos.append({
                    **p,
                    "display_label": f"{p['name']} ({p['label']}) ลด {money(p['discount'])}",
                })
            valid_pids = {p["id"] for p in available_promos}
            if promo_id is not None and promo_id in valid_pids:
                selected_promo_id = promo_id
                bill = checkout_service.preview(active_sid, promo_id=promo_id)
            else:
                selected_promo_id = base_preview.get("promo_id")
                bill = base_preview
        except ValueError:
            bill = None

        if bill is not None and bill["status"] == config.SESSION_AWAITING_PAYMENT:
            promptpay = _build_promptpay_info(bill["total"])

    return {
        "tables": rows,
        "selected_session_id": active_sid,
        "selected_promo_id": selected_promo_id,
        "available_promos": available_promos,
        "bill": bill,
        "promptpay": promptpay,
    }


@router.post("/validate_cash")
def validate_cash(body: ValidateCashRequest, _user: dict = Depends(require_staff)) -> dict:
    return checkout_service.validate_payment(body.total, "cash", amount_received=body.amount_received)


@router.post("/{session_id}/start")
def start_table_checkout(session_id: int, user: dict = Depends(require_staff)) -> dict:
    bill = checkout_service.start_checkout(session_id, user["id"])
    return {"bill": bill, "message": f"เช็คบิลโต๊ะ {bill['table_no']} แล้ว"}


@router.post("/{session_id}/pay")
def pay_table_bill(session_id: int, body: PayRequest, user: dict = Depends(require_staff)) -> dict:
    paid = checkout_service.pay(
        session_id,
        body.payment_method,
        user["id"],
        promo_id=body.promo_id,
        force=bool(body.force),
        amount_received=body.amount_received if body.amount_received is not None else checkout_service._UNSET,
    )
    receipt_info = checkout_service._extract_receipt_lines_and_totals(paid)
    receipt_text = checkout_service.build_receipt_text(paid)
    return {
        "bill": paid,
        "receipt_info": receipt_info,
        "receipt_text": receipt_text,
        "message": f"โต๊ะ {paid['table_no']} ชำระเงินเรียบร้อยแล้ว ({receipt_info['method_th']})",
    }


@router.get("/{session_id}/receipt")
def get_receipt_data(session_id: int, _user: dict = Depends(require_staff)) -> dict:
    bill = checkout_service.get_bill_detail(session_id)
    if bill is None:
        raise ValueError("ไม่พบบิลสำหรับออกใบเสร็จ")
    receipt_info = checkout_service._extract_receipt_lines_and_totals(bill)
    receipt_text = checkout_service.build_receipt_text(bill)
    return {"bill": bill, "receipt_info": receipt_info, "receipt_text": receipt_text}


@router.post("/{session_id}/export/{fmt}")
def export_receipt_file(session_id: int, fmt: str, _user: dict = Depends(require_staff)) -> dict:
    path = checkout_service.export_receipt(session_id, fmt=fmt)
    return {
        "filename": path.name,
        "path": str(path),
        "download_url": f"/api/staff/checkout/files/{path.name}",
        "message": f"บันทึก {fmt.upper()} แล้ว: {path}",
    }


@router.get("/files/{filename}")
def download_exported_receipt(filename: str, _user: dict = Depends(require_staff)):
    if not filename or Path(filename).name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="ชื่อไฟล์ไม่ถูกต้อง")
    full = (Path(config.EXPORTS_DIR) / filename).resolve()
    exports_root = Path(config.EXPORTS_DIR).resolve()
    if not str(full).startswith(str(exports_root)) or not full.is_file():
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ที่ต้องการดาวน์โหลด")
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else "text/plain; charset=utf-8"
    return FileResponse(path=str(full), filename=filename, media_type=media_type)
