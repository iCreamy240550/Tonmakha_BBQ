"""server/routes/menu.py — API หน้าเมนูและราคา"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

import config
from server.deps import require_owner
from server.helpers import parse_number
from services import menu_service, stock_service

router = APIRouter(prefix="/api/owner/menu", tags=["menu"])


class CategoryCreateRequest(BaseModel):
    name: str


class CategoryUpdateRequest(BaseModel):
    name: str | None = None
    active: bool | None = None
    sort_order: int | None = None


class CategoryMoveRequest(BaseModel):
    delta: int


class ItemCreateRequest(BaseModel):
    category_id: int
    name: str
    item_type: str = config.MENU_TYPE_NORMAL
    price: float | str
    stock_item_id: int | None = None


class ItemUpdateRequest(BaseModel):
    name: str | None = None
    price: float | str | None = None
    category_id: int | None = None
    stock_item_id: int | None = None
    clear_stock: bool = False
    active: bool | None = None
    sort_order: int | None = None


class SoldOutRequest(BaseModel):
    sold_out: bool


class ItemMoveRequest(BaseModel):
    category_id: int
    delta: int


@router.get("")
def get_menu_management(category_id: int | None = None, _user: dict = Depends(require_owner)) -> dict:
    categories = menu_service.list_categories(include_inactive=True)
    if category_id is not None and not any(c["id"] == category_id for c in categories):
        category_id = None
    stock_items = stock_service.list_items(include_inactive=True)
    stock_names = {s["id"]: s["name"] for s in stock_items}
    items = menu_service.list_items(category_id, include_inactive=True)
    for it in items:
        it["stock_display_name"] = stock_names.get(it["stock_item_id"], "-") if it.get("stock_item_id") else "-"
    active_count = sum(1 for i in items if i["active"])
    return {
        "categories": categories,
        "selected_category_id": category_id,
        "items": items,
        "stock_items": stock_items,
        "subtitle": f"{len(items)} รายการ (ขายอยู่ {active_count})",
    }


@router.post("/categories")
def create_category(body: CategoryCreateRequest, user: dict = Depends(require_owner)) -> dict:
    cat = menu_service.add_category(body.name, user_id=user["id"])
    return {"category": cat, "message": "เพิ่มหมวดแล้ว"}


@router.patch("/categories/{category_id}")
def edit_category(category_id: int, body: CategoryUpdateRequest, user: dict = Depends(require_owner)) -> dict:
    cat = menu_service.update_category(
        category_id,
        name=body.name,
        sort_order=body.sort_order,
        active=body.active,
        user_id=user["id"],
    )
    msg = "บันทึกหมวดแล้ว"
    if body.active is not None:
        msg = "แสดงหมวดแล้ว" if body.active else "ซ่อนหมวดแล้ว"
    elif body.name is not None:
        msg = "เปลี่ยนชื่อแล้ว"
    return {"category": cat, "message": msg}


@router.post("/categories/{category_id}/move")
def move_category(category_id: int, body: CategoryMoveRequest, user: dict = Depends(require_owner)) -> dict:
    cats = menu_service.list_categories(include_inactive=True)
    ids = [c["id"] for c in cats]
    if category_id not in ids:
        raise ValueError("ไม่พบหมวดนี้")
    pos = ids.index(category_id)
    new_pos = pos + int(body.delta)
    if not (0 <= new_pos < len(ids)):
        return {"moved": False}
    ids.insert(new_pos, ids.pop(pos))
    by_id = {c["id"]: c for c in cats}
    for order, cid in enumerate(ids, start=1):
        if by_id[cid]["sort_order"] != order:
            menu_service.update_category(cid, sort_order=order, user_id=user["id"])
    return {"moved": True}


@router.post("/items")
def create_menu_item(body: ItemCreateRequest, user: dict = Depends(require_owner)) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise ValueError("กรุณากรอกชื่อเมนู")
    price = parse_number(str(body.price), "ราคา", minimum=0)
    item = menu_service.add_item(
        body.category_id,
        name,
        body.item_type,
        price,
        stock_item_id=body.stock_item_id,
        user_id=user["id"],
    )
    return {"item": item, "message": "เพิ่มเมนูแล้ว"}


@router.patch("/items/{item_id}")
def edit_menu_item(item_id: int, body: ItemUpdateRequest, user: dict = Depends(require_owner)) -> dict:
    kwargs: dict = {"user_id": user["id"]}
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise ValueError("กรุณากรอกชื่อเมนู")
        kwargs["name"] = name
    if body.price is not None:
        kwargs["price"] = parse_number(str(body.price), "ราคา", minimum=0)
    if body.category_id is not None:
        kwargs["category_id"] = body.category_id
    if body.clear_stock:
        kwargs["stock_item_id"] = None
    elif body.stock_item_id is not None:
        kwargs["stock_item_id"] = body.stock_item_id
    if body.active is not None:
        kwargs["active"] = body.active
    if body.sort_order is not None:
        kwargs["sort_order"] = body.sort_order

    item = menu_service.update_item(item_id, **kwargs)
    msg = "บันทึกเมนูแล้ว"
    if body.active is not None and body.name is None and body.price is None:
        msg = "แสดงเมนูแล้ว" if body.active else "ซ่อนเมนูแล้ว"
    return {"item": item, "message": msg}


@router.post("/items/{item_id}/move")
def move_menu_item(item_id: int, body: ItemMoveRequest, user: dict = Depends(require_owner)) -> dict:
    items = menu_service.list_items(body.category_id, include_inactive=True)
    ids = [i["id"] for i in items]
    if item_id not in ids:
        raise ValueError("ไม่พบเมนูในหมวดนี้")
    pos = ids.index(item_id)
    new_pos = pos + int(body.delta)
    if not (0 <= new_pos < len(ids)):
        return {"moved": False}
    ids.insert(new_pos, ids.pop(pos))
    by_id = {i["id"]: i for i in items}
    for order, iid in enumerate(ids, start=1):
        if by_id[iid]["sort_order"] != order:
            menu_service.update_item(iid, sort_order=order, user_id=user["id"])
    return {"moved": True}


@router.post("/items/{item_id}/sold_out")
def toggle_item_sold_out(item_id: int, body: SoldOutRequest, user: dict = Depends(require_owner)) -> dict:
    item_before = menu_service.get_item(item_id)
    if item_before is None:
        raise ValueError("ไม่พบเมนูนี้")
    menu_service.set_sold_out(item_id, bool(body.sold_out), user_id=user["id"])
    updated = menu_service.get_item(item_id)
    msg = f"{updated['name']} {'ทำเป็นหมดแล้ว (แจ้งโต๊ะที่นั่งอยู่)' if body.sold_out else 'กลับมามีขาย'}"
    return {"item": updated, "message": msg}


@router.post("/items/{item_id}/image")
def upload_menu_image(
    item_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(require_owner),
) -> dict:
    raw = file.file.read(config.MAX_IMAGE_SIZE_BYTES + 1024)
    if len(raw) > config.MAX_IMAGE_SIZE_BYTES:
        raise ValueError(f"ไฟล์รูปภาพมีขนาดใหญ่เกินกำหนด (สูงสุดไม่เกิน {config.MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB)")
    item = menu_service.set_item_image(
        item_id,
        raw,
        original_filename=file.filename or "upload.png",
        user_id=user["id"],
    )
    return {"item": item, "message": "อัปโหลดรูปภาพเมนูแล้ว"}


@router.delete("/items/{item_id}/image")
def remove_menu_image(item_id: int, user: dict = Depends(require_owner)) -> dict:
    item = menu_service.delete_item_image(item_id, user_id=user["id"])
    return {"item": item, "message": "ลบรูปภาพเมนูแล้ว"}


@router.get("/items/{item_id}/delete_impact")
def get_menu_delete_impact(item_id: int, _user: dict = Depends(require_owner)) -> dict:
    return menu_service.get_delete_impact(item_id)


@router.delete("/items/{item_id}")
def delete_menu_item(item_id: int, user: dict = Depends(require_owner)) -> dict:
    return menu_service.delete_item(item_id, user_id=user["id"])
