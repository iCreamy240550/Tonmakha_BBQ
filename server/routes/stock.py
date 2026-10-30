"""server/routes/stock.py — API หน้าสต๊อกวัตถุดิบ/สินค้าของเจ้าของร้าน"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.deps import require_owner
from server.helpers import fmt_datetime, fmt_qty, parse_number
from services import stock_service

router = APIRouter(prefix="/api/owner/stock", tags=["stock"])


class StockCreateRequest(BaseModel):
    name: str
    unit: str
    quantity: float | str = 0
    min_quantity: float | str | None = None


class StockUpdateRequest(BaseModel):
    name: str
    unit: str
    min_quantity: float | str | None = None
    active: bool = True


class StockQuantityRequest(BaseModel):
    quantity: float | str
    reason: str = ""


@router.get("")
def list_stock_items(
    include_inactive: bool = False,
    selected_id: int | None = None,
    _user: dict = Depends(require_owner),
) -> dict:
    items = stock_service.list_items(include_inactive=include_inactive)
    default_thresh = stock_service.get_default_low_threshold()
    for it in items:
        it["quantity_fmt"] = f"{fmt_qty(it['quantity'])} {it['unit']}"
        it["min_qty_fmt"] = fmt_qty(it["effective_min_quantity"])
    low = sum(1 for i in items if i["active"] and i["is_low"])
    subtitle = f"{len(items)} รายการ" + (f" · ใกล้หมด/หมด {low} รายการ" if low else "")

    movements = []
    if selected_id is not None and any(i["id"] == selected_id for i in items):
        for m in stock_service.get_movements(selected_id, 100):
            m["created_at_fmt"] = fmt_datetime(m["created_at"])
            m["change_qty_fmt"] = ("+" if m["change_qty"] > 0 else "") + fmt_qty(m["change_qty"])
            m["user_display"] = m.get("user_name") or "ระบบ"
            movements.append(m)

    return {
        "items": items,
        "default_low_threshold": default_thresh,
        "default_low_threshold_fmt": fmt_qty(default_thresh),
        "subtitle": subtitle,
        "movements": movements,
    }


@router.get("/{stock_id}/movements")
def get_item_movements(stock_id: int, _user: dict = Depends(require_owner)) -> dict:
    item = stock_service.get_item(stock_id)
    if item is None:
        raise ValueError("ไม่พบรายการสต๊อก")
    movements = []
    for m in stock_service.get_movements(stock_id, 100):
        m["created_at_fmt"] = fmt_datetime(m["created_at"])
        m["change_qty_fmt"] = ("+" if m["change_qty"] > 0 else "") + fmt_qty(m["change_qty"])
        m["user_display"] = m.get("user_name") or "ระบบ"
        movements.append(m)
    return {"item": item, "movements": movements}


@router.post("")
def create_stock_item(body: StockCreateRequest, user: dict = Depends(require_owner)) -> dict:
    name = (body.name or "").strip()
    unit = (body.unit or "").strip()
    if not name or not unit:
        raise ValueError("กรุณากรอกชื่อและหน่วย")
    default_min = stock_service.get_default_low_threshold()
    min_q = parse_number(str(body.min_quantity or ""), "จุดเตือน", minimum=0, allow_empty=True, default=default_min)
    qty = parse_number(str(body.quantity or ""), "จำนวนตั้งต้น", minimum=0, allow_empty=True, default=0.0)
    item = stock_service.add_item(name, unit, qty, min_q, user_id=user["id"])
    return {"item": item, "message": "เพิ่มรายการสต๊อกแล้ว"}


@router.patch("/{stock_id}")
def update_stock_item(stock_id: int, body: StockUpdateRequest, user: dict = Depends(require_owner)) -> dict:
    name = (body.name or "").strip()
    unit = (body.unit or "").strip()
    if not name or not unit:
        raise ValueError("กรุณากรอกชื่อและหน่วย")
    default_min = stock_service.get_default_low_threshold()
    min_q = parse_number(str(body.min_quantity or ""), "จุดเตือน", minimum=0, allow_empty=True, default=default_min)
    item = stock_service.update_item(
        stock_id,
        name=name,
        unit=unit,
        min_quantity=min_q,
        active=bool(body.active),
        user_id=user["id"],
    )
    return {"item": item, "message": "บันทึกแล้ว"}


@router.post("/{stock_id}/restock")
def restock_item(stock_id: int, body: StockQuantityRequest, user: dict = Depends(require_owner)) -> dict:
    item = stock_service.get_item(stock_id)
    if item is None:
        raise ValueError("ไม่พบรายการสต๊อก")
    qty = parse_number(str(body.quantity), "จำนวน")
    if qty <= 0:
        raise ValueError("จำนวนที่เติมต้องมากกว่า 0")
    reason = (body.reason or "").strip() or "เติมสต๊อก"
    new_qty = stock_service.restock(stock_id, qty, user_id=user["id"], reason=reason)
    return {
        "new_quantity": new_qty,
        "message": f"เติมแล้ว คงเหลือ {fmt_qty(new_qty)} {item['unit']}",
    }


@router.post("/{stock_id}/adjust")
def adjust_item(stock_id: int, body: StockQuantityRequest, user: dict = Depends(require_owner)) -> dict:
    item = stock_service.get_item(stock_id)
    if item is None:
        raise ValueError("ไม่พบรายการสต๊อก")
    qty = parse_number(str(body.quantity), "จำนวน")
    if qty == 0:
        raise ValueError("จำนวนที่ปรับต้องไม่เป็น 0")
    reason = (body.reason or "").strip()
    if not reason:
        raise ValueError("กรุณากรอกเหตุผลที่ปรับสต๊อก")
    new_qty = stock_service.adjust(stock_id, qty, reason, user_id=user["id"])
    return {
        "new_quantity": new_qty,
        "message": f"ปรับแล้ว คงเหลือ {fmt_qty(new_qty)} {item['unit']}",
    }


@router.get("/{stock_id}/delete_impact")
def get_stock_delete_impact(stock_id: int, _user: dict = Depends(require_owner)) -> dict:
    return stock_service.get_delete_impact(stock_id)


@router.delete("/{stock_id}")
def delete_stock_item(stock_id: int, user: dict = Depends(require_owner)) -> dict:
    return stock_service.delete_item(stock_id, user_id=user["id"])
