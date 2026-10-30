"""web/session.py — ตรรกะฝั่งเว็บมือถือลูกค้า (ไม่ import nicegui จึงทดสอบแยกได้)

หน้าที่:
- จำเครื่องลูกค้า (device_id) และรอบของโต๊ะ (session_id) ใน storage ของเบราว์เซอร์ (dict-like)
- โหลด/ตรวจสิทธิ์ว่ารอบนี้เป็นของเครื่องนี้จริง (ลูกค้าไม่ต้องล็อกอิน เห็นได้เฉพาะโต๊ะที่ตัวเองสแกน)
- ตะกร้าสั่งอาหาร (ตรวจสอบสต๊อกคงเหลือและป้องกันการสั่งสินค้าหมด/เกินสต๊อก), ส่งออเดอร์, ยกเลิกคำขอตอน pending
- snapshot ข้อมูลของรอบสำหรับวาดหน้า + signature เพื่อรีเฟรชเฉพาะเมื่อข้อมูลเปลี่ยน

กติกาสำคัญ:
- **ห้ามเรียก table_service.touch_session ตอนลูกค้าแค่เปิดดู** (ไม่งั้นแจ้งเตือนโต๊ะเงียบกรณี B ไม่ทำงาน)
  ฟังก์ชันในไฟล์นี้อ่านอย่างเดียว ยกเว้น place_order / cancel_request / mark_notices_read
- ห้ามเรียก alert_service.check_alerts / pop_sound_alerts จากเว็บ
"""
from __future__ import annotations

import math
import uuid

import config
from services import (checkout_service, menu_service, notice_service, order_service,
                      pricing_service, table_service, weigh_service)

DEVICE_KEY = "device_id"
SESSION_KEY = "session_id"
CART_KEY = "cart"

VIEW_WAITING = "waiting"
VIEW_ORDER = "order"
VIEW_BILL = "bill"
VIEW_CLOSED = "closed"
VIEW_CANCELLED = "cancelled"

VIEW_BY_STATUS = {
    config.SESSION_PENDING: VIEW_WAITING,
    config.SESSION_OPEN: VIEW_ORDER,
    config.SESSION_AWAITING_PAYMENT: VIEW_BILL,
    config.SESSION_CLOSED: VIEW_CLOSED,
    config.SESSION_CANCELLED: VIEW_CANCELLED,
}
TERMINAL_VIEWS = (VIEW_CLOSED, VIEW_CANCELLED)

MAX_QTY = order_service.MAX_QTY_PER_LINE  # 99


# ---------------------------------------------------------------- เครื่อง/รอบที่จำไว้

def get_device_id(storage) -> str:
    """รหัสเครื่องลูกค้า (สร้างครั้งแรกแล้วจำไว้ใน storage ของเบราว์เซอร์)"""
    dev = storage.get(DEVICE_KEY)
    if not isinstance(dev, str) or len(dev) < 16:
        dev = uuid.uuid4().hex
        storage[DEVICE_KEY] = dev
    return dev


def device_info(user_agent: str | None) -> str | None:
    """ข้อความรุ่นเครื่อง/เบราว์เซอร์สำหรับเก็บใน table_sessions.device_info (ตัดที่ 200 ตัวอักษร)"""
    text = (user_agent or "").strip()
    return text[:200] or None


def remember_session(storage, session_id: int) -> None:
    """จำรอบนี้ไว้ (ถ้าเป็นรอบใหม่ ตะกร้าเก่าจะถูกล้าง)"""
    if storage.get(SESSION_KEY) != int(session_id):
        storage.pop(CART_KEY, None)
    storage[SESSION_KEY] = int(session_id)


def forget_session(storage) -> None:
    storage.pop(SESSION_KEY, None)
    storage.pop(CART_KEY, None)


def _safe_table(table: dict | None) -> dict | None:
    if table is None:
        return None
    return {k: v for k, v in table.items() if k != "secret_key"}


def load_context(storage) -> dict | None:
    """รอบที่เครื่องนี้จำไว้ -> {'session_id','device_id','table'(ไม่มี secret_key),'status','view'}
    None ถ้าไม่มี / ไม่พบ / ไม่ใช่ของเครื่องนี้ (จะลบที่จำไว้ให้)"""
    sid = storage.get(SESSION_KEY)
    dev = storage.get(DEVICE_KEY)
    if not isinstance(sid, int) or isinstance(sid, bool) or not dev:
        return None
    s = table_service.get_session(sid)
    if s is None or s.get("device_id") != dev:
        forget_session(storage)
        return None
    table = _safe_table(table_service.get_table(s["table_id"]))
    return {"session_id": sid, "device_id": dev, "table": table, "status": s["status"],
            "view": VIEW_BY_STATUS.get(s["status"], VIEW_CLOSED)}


def require_owner(session_id: int, device_id: str) -> dict:
    """ตรวจว่ารอบนี้เป็นของเครื่องนี้ -> dict รอบ ; ValueError ถ้าไม่ใช่"""
    s = table_service.get_session(session_id)
    if s is None or not device_id or s.get("device_id") != device_id:
        raise ValueError("ไม่พบรายการของโต๊ะนี้ กรุณาสแกน QR ที่โต๊ะอีกครั้ง")
    return s


# ---------------------------------------------------------------- การกระทำของลูกค้า

def cancel_request(session_id: int, device_id: str) -> dict:
    """ลูกค้ายกเลิกคำขอตอน pending (กติกาข้อ 6) -> dict รอบ ; ValueError ถ้าไม่ใช่เจ้าของ/ไม่ใช่ pending"""
    require_owner(session_id, device_id)
    return table_service.cancel_session(session_id, cancelled_by="customer")


def place_order(session_id: int, device_id: str, cart: dict[int, int], note: str | None = None) -> dict:
    """ลูกค้าส่งออเดอร์จากตะกร้า {menu_item_id: จำนวน} -> ออเดอร์ (dict + items)
    ValueError (ข้อความไทยจาก service) ถ้าโต๊ะยังไม่ open / เมนูหมด / สต๊อกไม่พอ ฯลฯ — ทั้งออเดอร์ rollback"""
    require_owner(session_id, device_id)
    items = [{"menu_item_id": int(i), "quantity": int(q)} for i, q in cart.items() if q > 0]
    return order_service.create_order(session_id, items, note=note, user_id=None)


def mark_notices_read(notice_ids: list[int]) -> None:
    """ทำเครื่องหมายว่าลูกค้าเห็นข้อความแล้ว"""
    for nid in notice_ids:
        notice_service.mark_read(nid)


# ---------------------------------------------------------------- ตะกร้าและการตรวจสต๊อก

def max_orderable_qty(item: dict | None) -> int:
    """จำนวนสูงสุดที่ลูกค้าสั่งได้สำหรับเมนูนี้ (พิจารณาประเภทเมนู, สถานะหมด, และสต๊อกคงเหลือ)"""
    if not item or item.get("item_type") != config.MENU_TYPE_NORMAL or item.get("is_sold_out"):
        return 0
    stock_qty = item.get("stock_quantity")
    if stock_qty is not None:
        avail = int(math.floor(max(0.0, float(stock_qty))))
        return max(0, min(MAX_QTY, avail))
    return MAX_QTY


def cart_load(storage, session_id: int) -> dict[int, int]:
    """ตะกร้าที่จำไว้ของรอบนี้ -> {menu_item_id: จำนวน} (ของรอบอื่น/ข้อมูลเพี้ยน = ว่าง)"""
    raw = storage.get(CART_KEY)
    if not isinstance(raw, dict) or raw.get("session_id") != session_id:
        return {}
    cart: dict[int, int] = {}
    for k, v in (raw.get("items") or {}).items():
        try:
            item_id, qty = int(k), int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= qty <= MAX_QTY:
            cart[item_id] = qty
    return cart


def cart_save(storage, session_id: int, cart: dict[int, int]) -> None:
    storage[CART_KEY] = {"session_id": session_id, "items": {str(i): q for i, q in cart.items() if q > 0}}


def _orderable_items(menu: list[dict]) -> dict[int, dict]:
    return {
        it["id"]: it
        for cat in menu
        for it in cat["items"]
        if max_orderable_qty(it) > 0
    }


def cart_change_item(cart: dict[int, int], menu: list[dict], item_id: int, delta: int) -> int:
    """เพิ่ม/ลดจำนวนสินค้าในตะกร้า พร้อมตรวจสอบสถานะสินค้าหมดและจำกัดไม่ให้เกินสต๊อกคงเหลือ
    คืนค่าจำนวนใหม่ในตะกร้า ; หากเพิ่มไม่ได้ (สินค้าหมด/เกินสต๊อก/เป็นเมนูชั่ง) จะ raise ValueError ภาษาไทย"""
    all_items = {it["id"]: it for cat in menu for it in cat["items"]}
    it = all_items.get(item_id)
    if it is None:
        cart.pop(item_id, None)
        raise ValueError("ไม่พบเมนูที่เลือก")
    if it.get("item_type") != config.MENU_TYPE_NORMAL:
        cart.pop(item_id, None)
        raise ValueError(f"{it['name']} เป็นเมนูชั่งกิโล กรุณาสั่งกับพนักงาน")
    max_q = max_orderable_qty(it)
    if max_q <= 0 or it.get("is_sold_out"):
        cart.pop(item_id, None)
        raise ValueError(f"{it['name']} สินค้าหมด ไม่สามารถเพิ่มลงตะกร้าได้")

    cur = cart.get(item_id, 0)
    target = cur + int(delta)
    if delta > 0 and target > max_q:
        cart[item_id] = max_q
        unit_txt = f" {it.get('stock_unit')}" if it.get("stock_unit") else ""
        raise ValueError(f"{it['name']} สั่งได้สูงสุด {max_q}{unit_txt} ตามสต๊อกคงเหลือ")

    new_qty = max(0, min(max_q, target))
    if new_qty > 0:
        cart[item_id] = new_qty
    else:
        cart.pop(item_id, None)
    return new_qty


def cart_clean(cart: dict[int, int], menu: list[dict]) -> list[str]:
    """เอารายการที่สั่งไม่ได้แล้ว (หมด/สต๊อกเป็น 0/ปิดขาย/เป็นเมนูชั่ง) ออกจากตะกร้า (แก้ dict ตรง ๆ)
    -> ชื่อเมนูที่ถูกเอาออก (ไว้แจ้งลูกค้า)"""
    ok = _orderable_items(menu)
    names_all = {it["id"]: it["name"] for cat in menu for it in cat["items"]}
    removed = []
    for item_id in list(cart):
        if item_id not in ok:
            removed.append(names_all.get(item_id, f"เมนู #{item_id}"))
            del cart[item_id]
    return removed


def cart_lines(cart: dict[int, int], menu: list[dict]) -> list[dict]:
    """ตะกร้า -> [{'id','name','price','quantity','line_total','stock_quantity','stock_unit'}] ตามลำดับเมนู"""
    ok = _orderable_items(menu)
    lines = []
    for cat in menu:
        for it in cat["items"]:
            q = cart.get(it["id"], 0)
            if q > 0 and it["id"] in ok:
                lines.append({
                    "id": it["id"],
                    "name": it["name"],
                    "price": it["price"],
                    "quantity": q,
                    "line_total": round(it["price"] * q, 2),
                    "stock_quantity": it.get("stock_quantity"),
                    "stock_unit": it.get("stock_unit"),
                })
    return lines


def cart_count(cart: dict[int, int]) -> int:
    return sum(q for q in cart.values() if q > 0)


def cart_total(cart: dict[int, int], menu: list[dict]) -> float:
    return round(sum(ln["line_total"] for ln in cart_lines(cart, menu)), 2)


# ---------------------------------------------------------------- snapshot สำหรับวาดหน้า

def get_snapshot(session_id: int) -> dict | None:
    """ข้อมูลทั้งหมดที่หน้าลูกค้าต้องใช้ (อ่านอย่างเดียว ไม่ขยับ last_activity) ; None ถ้าไม่พบรอบ"""
    s = table_service.get_session(session_id)
    if s is None:
        return None
    status = s["status"]
    bill = None
    if status in (config.SESSION_AWAITING_PAYMENT, config.SESSION_CLOSED):
        try:
            bill = checkout_service.preview(session_id)
        except ValueError:
            bill = None
    subtotal = round(weigh_service.session_total(session_id) + order_service.session_total(session_id), 2)
    member_discount = 0.0
    member_promo_name = None
    if s.get("applied_promo_id") and subtotal > 0:
        try:
            calc = pricing_service.calc_bill(session_id)
            member_discount = float(calc.get("discount") or 0.0)
            member_promo_name = calc.get("promo_name")
        except Exception:
            pass
    return {
        "session": s,
        "table": _safe_table(table_service.get_table(s["table_id"])),
        "view": VIEW_BY_STATUS.get(status, VIEW_CLOSED),
        "menu": menu_service.get_menu_for_customer() if status == config.SESSION_OPEN else [],
        "weigh_entries": weigh_service.list_entries(session_id),
        "orders": order_service.list_orders(session_id),
        "subtotal": subtotal,
        "member_discount": member_discount,
        "member_promo_name": member_promo_name,
        "notices": notice_service.list_notices(session_id, limit=30),
        "unread": notice_service.list_unread(session_id),
        "bill": bill,
    }


def signature(snap: dict | None):
    """ค่าเปรียบเทียบ (hashable) — เปลี่ยนเมื่อมีอะไรที่ต้องวาดหน้าใหม่ (รวมสต๊อกคงเหลือและรูปภาพเมนู)"""
    if snap is None:
        return None
    bill = snap["bill"]
    return (
        snap["session"]["status"],
        tuple(n["id"] for n in snap["notices"]),
        tuple((o["id"], o["status"], tuple((i["id"], i["status"]) for i in o["items"])) for o in snap["orders"]),
        tuple(w["id"] for w in snap["weigh_entries"]),
        tuple(
            (
                it["id"],
                it["is_sold_out"],
                it["price"],
                it["name"],
                it.get("stock_quantity"),
                it.get("stock_unit"),
                it.get("image_path"),
            )
            for cat in snap["menu"]
            for it in cat["items"]
        ),
        (bill["total"], bill["subtotal"], bill.get("discount")) if bill else None,
        snap.get("member_discount"),
        snap.get("member_promo_name"),
    )
