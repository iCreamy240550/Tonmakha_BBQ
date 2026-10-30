"""server/routes/orders.py — API หน้าออเดอร์ของพนักงาน"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import config
from server.deps import require_staff
from server.helpers import ORDER_STATUS_COLORS, duration_text, fmt_time
from services import menu_service, order_service, table_service

router = APIRouter(prefix="/api/staff/orders", tags=["orders"])


class OrderItemInput(BaseModel):
    menu_item_id: int
    quantity: int


class CreateStaffOrderRequest(BaseModel):
    session_id: int
    items: list[OrderItemInput]
    note: str | None = None


class UpdateOrderStatusRequest(BaseModel):
    status: str


class CancelOrderItemRequest(BaseModel):
    reason: str = ""


@router.get("")
def list_staff_orders(
    session_id: int | None = None,
    only_active: bool = True,
    _user: dict = Depends(require_staff),
) -> dict:
    all_tables = table_service.list_tables_with_status()
    usable_tables = [
        {"table_no": t["table_no"], "name": t["name"], "session_id": t["session_id"], "label": f"โต๊ะ {t['table_no']}"}
        for t in all_tables
        if t["status"] in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT) and t["session_id"]
    ]
    tables_by_sid = {t["session_id"]: t for t in all_tables if t["session_id"]}
    valid_sids = {t["session_id"] for t in usable_tables}
    active_sid = session_id if session_id in valid_sids else None

    orders: list[dict] = []
    if only_active and active_sid is None:
        orders = order_service.list_active_orders()
    else:
        sids = [active_sid] if active_sid else list(tables_by_sid)
        for sid in sids:
            t = tables_by_sid.get(sid)
            for o in order_service.list_orders(sid):
                if only_active and o["status"] not in ("new", "preparing"):
                    continue
                o["table_no"] = t["table_no"] if t else None
                orders.append(o)
        orders.sort(key=lambda o: o["id"])

    sig_items = []
    for o in orders:
        o["time_text"] = fmt_time(o["created_at"])
        o["duration_text"] = duration_text(o["created_at"]) if o["status"] in ("new", "preparing") else ""
        o["status_color"] = ORDER_STATUS_COLORS.get(o["status"], "#868e96")
        o["actor_text"] = "ลูกค้าสั่ง" if o.get("created_by") is None else "พนักงานสั่ง"
        sig_items.append((
            o["id"],
            o["status"],
            tuple((i["id"], i["status"], i["quantity"]) for i in o["items"]),
        ))

    normal_menu = [
        m for m in menu_service.list_items()
        if m["item_type"] == config.MENU_TYPE_NORMAL and not m["is_sold_out"]
    ]

    raw_sig = json.dumps(sig_items, separators=(",", ":"))
    sig = hashlib.sha1(raw_sig.encode("utf-8")).hexdigest()
    return {
        "orders": orders,
        "count": len(orders),
        "subtitle": f"{len(orders)} ออเดอร์",
        "tables": usable_tables,
        "selected_session_id": active_sid,
        "only_active": only_active,
        "orderable_menu": normal_menu,
        "signature": sig,
    }


@router.post("")
def create_staff_order(body: CreateStaffOrderRequest, user: dict = Depends(require_staff)) -> dict:
    items = [{"menu_item_id": it.menu_item_id, "quantity": it.quantity} for it in body.items if it.quantity > 0]
    order = order_service.create_order(
        body.session_id,
        items,
        note=(body.note or "").strip() or None,
        user_id=user["id"],
    )
    return {"order": order, "message": "บันทึกออเดอร์แล้ว"}


@router.post("/{order_id}/status")
def change_order_status(order_id: int, body: UpdateOrderStatusRequest, user: dict = Depends(require_staff)) -> dict:
    latest = order_service.get_order(order_id)
    if latest is None:
        raise ValueError("ไม่พบออเดอร์")
    new_status = (body.status or "").strip()
    if new_status == "preparing" and latest["status"] != "new":
        raise ValueError("ออเดอร์นี้ไม่ได้อยู่ในสถานะใหม่แล้ว")
    if new_status == "served" and latest["status"] != "preparing":
        raise ValueError("ต้องกดเริ่มทำออเดอร์ก่อนจึงจะเสิร์ฟได้")
    updated = order_service.set_order_status(order_id, new_status, user["id"])
    return {"order": updated, "message": f"อัปเดตสถานะเป็น {updated['status_th']}"}


@router.post("/items/{order_item_id}/cancel")
def cancel_order_item(order_item_id: int, body: CancelOrderItemRequest, user: dict = Depends(require_staff)) -> dict:
    order = order_service.cancel_item(order_item_id, body.reason, user["id"])
    return {"order": order, "message": "ยกเลิกรายการสั่งแล้ว"}
