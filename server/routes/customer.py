"""server/routes/customer.py — API ฝั่งมือถือของลูกค้า (ผ่าน web/session.py เดิมทั้งหมด + ระบบสมาชิก)"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from server import auth as server_auth
from services import member_service, otp_service, promo_service, qr_service
from web import session as web_session

router = APIRouter(prefix="/api/customer", tags=["customer"])


class ScanRequest(BaseModel):
    table_no: int
    k: str = ""


class CartChangeRequest(BaseModel):
    item_id: int
    delta: int


class PlaceOrderRequest(BaseModel):
    note: str | None = None
    cart: dict[int, int] | None = None


class MarkReadRequest(BaseModel):
    notice_ids: list[int]


class MemberLoginRequest(BaseModel):
    identifier: str
    password: str


class MemberOtpRequest(BaseModel):
    email: str


class MemberSignupRequest(BaseModel):
    name: str
    email: str
    phone: str
    password: str
    password_confirm: str
    otp_code: str


class MemberResetStartRequest(BaseModel):
    email: str


class MemberResetVerifyRequest(BaseModel):
    email: str
    otp_code: str
    new_password: str
    new_password_confirm: str


class MemberClaimPromoRequest(BaseModel):
    code: str


class MemberApplyPromoRequest(BaseModel):
    code: str | None = None


def _direct_client_ip(request: Request) -> str:
    """ใช้เฉพาะ request.client.host เท่านั้น ห้ามเชื่อ X-Forwarded-For เด็ดขาด"""
    return (request.client.host if request and request.client else "unknown") or "unknown"


def _set_member_cookie_fields(storage: server_auth.CustomerCookieStorage, member_id: int) -> None:
    storage["member_id"] = int(member_id)
    storage["mfp"] = server_auth.get_member_pw_fingerprint(int(member_id)) or ""


def _clear_member_cookie_fields(storage: server_auth.CustomerCookieStorage) -> None:
    storage.pop("member_id", None)
    storage.pop("mfp", None)
    storage.pop("applied_promo_code", None)


def _sig_string(snap: dict | None, member: dict | None, applied_code: str | None, member_promos: list[dict]) -> str | None:
    sig_tuple = web_session.signature(snap)
    if sig_tuple is None and member is None:
        return None
    extra = (
        sig_tuple,
        member["id"] if member else None,
        tuple(member.get("claimed_promos") or []) if member else (),
        len(member.get("history") or []) if member else 0,
        applied_code,
        tuple((p["id"], p["code"], p["discount_value"], p["min_subtotal"]) for p in member_promos),
    )
    raw = json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _resolve_member_and_promo(storage: server_auth.CustomerCookieStorage, sid: int | None) -> tuple[dict | None, str | None]:
    """ตรวจสอบตัวตนสมาชิกจากคุกกี้ลูกค้าที่เซ็นลายเซ็นและลายนิ้วมือรหัสผ่าน (mfp) เท่านั้น
    ห้ามดึง member_id จาก table_sessions มาให้อุปกรณ์อื่นที่นั่งโต๊ะเดียวกันแต่ไม่ได้ล็อกอินเองเด็ดขาด
    """
    raw_mid = storage.get("member_id")
    mfp = storage.get("mfp")
    member_id: int | None = None
    if isinstance(raw_mid, int) and not isinstance(raw_mid, bool):
        member_id = raw_mid

    member: dict | None = None
    if member_id and server_auth.verify_member_cookie_fingerprint(member_id, mfp):
        member = member_service.get_member(member_id, include_history=True)

    if member is None:
        if raw_mid is not None or mfp is not None or storage.get("applied_promo_code") is not None:
            _clear_member_cookie_fields(storage)
        return None, None

    sess_state = member_service.get_session_member_state(sid) if sid else {"member_id": None, "applied_promo_id": None}
    if sid and not sess_state.get("member_id"):
        member_service.bind_member_to_session(sid, member["id"])

    applied_code = storage.get("applied_promo_code")
    if sid and sess_state.get("applied_promo_id") and sess_state.get("member_id") == member["id"]:
        p = promo_service.get_promo(int(sess_state["applied_promo_id"]))
        if p and p["active"]:
            applied_code = p["code"]
            if storage.get("applied_promo_code") != applied_code:
                storage["applied_promo_code"] = applied_code
        else:
            applied_code = None
            storage.pop("applied_promo_code", None)
    elif applied_code and sid:
        p = promo_service.get_promo_by_code(applied_code)
        if p and p["active"]:
            member_service.set_session_applied_promo(sid, p["id"])
        else:
            applied_code = None
            storage.pop("applied_promo_code", None)

    return member, applied_code


def _build_state_payload(storage: server_auth.CustomerCookieStorage) -> dict:
    ctx = web_session.load_context(storage)
    member_promos = member_service.list_member_promotions_for_customer()
    if ctx is None:
        member, applied_code = _resolve_member_and_promo(storage, None)
        return {
            "has_session": False,
            "context": None,
            "snapshot": None,
            "signature": _sig_string(None, member, applied_code, member_promos),
            "cart": {},
            "cart_lines": [],
            "cart_count": 0,
            "cart_total": 0.0,
            "removed_from_cart": [],
            "member": member,
            "applied_promo_code": applied_code,
            "member_promotions": member_promos,
        }
    sid = ctx["session_id"]
    member, applied_code = _resolve_member_and_promo(storage, sid)
    snap = web_session.get_snapshot(sid)
    if snap is None:
        web_session.forget_session(storage)
        return {
            "has_session": False,
            "context": None,
            "snapshot": None,
            "signature": None,
            "cart": {},
            "cart_lines": [],
            "cart_count": 0,
            "cart_total": 0.0,
            "removed_from_cart": [],
            "member": member,
            "applied_promo_code": applied_code,
            "member_promotions": member_promos,
        }

    if snap.get("session"):
        snap["session"] = {
            k: v for k, v in snap["session"].items()
            if k not in ("cancel_reason",)
        }

    cart = web_session.cart_load(storage, sid)
    removed = []
    if snap["view"] == web_session.VIEW_ORDER:
        removed = web_session.cart_clean(cart, snap["menu"])
        if removed:
            web_session.cart_save(storage, sid, cart)
    lines = web_session.cart_lines(cart, snap["menu"]) if snap["view"] == web_session.VIEW_ORDER else []
    count = web_session.cart_count(cart) if snap["view"] == web_session.VIEW_ORDER else 0
    total = web_session.cart_total(cart, snap["menu"]) if snap["view"] == web_session.VIEW_ORDER else 0.0

    for cat in snap.get("menu") or []:
        for it in cat.get("items") or []:
            it["max_orderable_qty"] = web_session.max_orderable_qty(it)

    return {
        "has_session": True,
        "context": ctx,
        "snapshot": snap,
        "signature": _sig_string(snap, member, applied_code, member_promos),
        "cart": {str(k): v for k, v in cart.items()},
        "cart_lines": lines,
        "cart_count": count,
        "cart_total": total,
        "removed_from_cart": removed,
        "member": member,
        "applied_promo_code": applied_code,
        "member_promotions": member_promos,
    }


@router.post("/scan")
def scan_qr(body: ScanRequest, request: Request, response: Response) -> dict:
    server_auth.check_scan_rate_limit(request)
    storage = server_auth.load_customer_storage(request)
    device_id = web_session.get_device_id(storage)
    user_agent = request.headers.get("user-agent")

    ctx = web_session.load_context(storage)
    if (
        ctx
        and ctx["view"] in (web_session.VIEW_WAITING, web_session.VIEW_ORDER, web_session.VIEW_BILL)
        and ctx["table"]
        and ctx["table"]["table_no"] != body.table_no
    ):
        server_auth.save_customer_storage(response, request, storage)
        return {
            "kind": "other_table",
            "code": "other_table",
            "message": "",
            "table_name": ctx["table"]["name"],
        }

    result = qr_service.resolve_scan(
        body.table_no,
        body.k,
        device_id,
        web_session.device_info(user_agent),
    )
    if result["ok"]:
        web_session.remember_session(storage, result["session"]["id"])
        member, _ = _resolve_member_and_promo(storage, result["session"]["id"])
        if member:
            member_service.bind_member_to_session(result["session"]["id"], member["id"])
        server_auth.save_customer_storage(response, request, storage)
        return {
            "kind": "ok",
            "code": "ok",
            "message": result["message"],
            "table_name": result["table"]["name"],
            "session_id": result["session"]["id"],
        }

    server_auth.save_customer_storage(response, request, storage)
    return {
        "kind": "fail",
        "code": result["code"],
        "message": result["message"],
        "table_name": result["table"]["name"] if result.get("table") else "",
    }


@router.get("/state")
def get_state(request: Request, response: Response) -> dict:
    storage = server_auth.load_customer_storage(request)
    payload = _build_state_payload(storage)
    if storage.dirty:
        server_auth.save_customer_storage(response, request, storage)
    return payload


@router.post("/cart/change")
def change_cart(body: CartChangeRequest, request: Request, response: Response) -> dict:
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    if ctx is None:
        raise ValueError("ไม่พบรายการของโต๊ะนี้ กรุณาสแกน QR ที่โต๊ะอีกครั้ง")
    sid = ctx["session_id"]
    snap = web_session.get_snapshot(sid)
    if snap is None or snap["view"] != web_session.VIEW_ORDER:
        raise ValueError("โต๊ะนี้ไม่ได้อยู่ในสถานะสั่งอาหาร")
    cart = web_session.cart_load(storage, sid)
    warning = None
    try:
        web_session.cart_change_item(cart, snap["menu"], body.item_id, body.delta)
    except ValueError as e:
        warning = str(e)
    web_session.cart_save(storage, sid, cart)
    server_auth.save_customer_storage(response, request, storage)

    state = _build_state_payload(storage)
    state["warning"] = warning
    if warning:
        response.status_code = 400
        state["detail"] = warning
    return state


@router.post("/order")
def submit_order(body: PlaceOrderRequest, request: Request, response: Response) -> dict:
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    if ctx is None:
        raise ValueError("ไม่พบรายการของโต๊ะนี้ กรุณาสแกน QR ที่โต๊ะอีกครั้ง")
    sid = ctx["session_id"]
    device_id = ctx["device_id"]
    cart = web_session.cart_load(storage, sid)
    if body.cart is not None and not cart:
        cart = {int(k): int(v) for k, v in body.cart.items() if int(v) > 0}

    order = web_session.place_order(sid, device_id, cart, note=body.note)
    cart.clear()
    web_session.cart_save(storage, sid, cart)
    server_auth.save_customer_storage(response, request, storage)

    state = _build_state_payload(storage)
    state["order"] = order
    state["message"] = "ส่งออเดอร์ให้ครัวแล้ว"
    return state


@router.post("/cancel")
def cancel_table_request(request: Request, response: Response) -> dict:
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    if ctx is None:
        raise ValueError("ไม่พบรายการของโต๊ะนี้ กรุณาสแกน QR ที่โต๊ะอีกครั้ง")
    web_session.cancel_request(ctx["session_id"], ctx["device_id"])
    state = _build_state_payload(storage)
    if storage.dirty:
        server_auth.save_customer_storage(response, request, storage)
    return state


@router.post("/notices/read")
def mark_notices_read(body: MarkReadRequest, request: Request) -> dict:
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    if ctx is None:
        return {"marked": 0}
    snap = web_session.get_snapshot(ctx["session_id"])
    if snap is None:
        return {"marked": 0}
    valid_ids = {n["id"] for n in (snap.get("notices") or [])} | {n["id"] for n in (snap.get("unread") or [])}
    to_mark = [int(nid) for nid in body.notice_ids if int(nid) in valid_ids]
    if to_mark:
        web_session.mark_notices_read(to_mark)
    return {"marked": len(to_mark)}


# ---------------------------------------------------------------- ระบบสมาชิกฝั่งลูกค้า (Member API)

@router.post("/member/otp")
def request_member_otp(body: MemberOtpRequest, request: Request) -> dict:
    otp_service.check_member_ip_rate_limit(request)
    return member_service.send_otp(body.email)


@router.post("/member/login")
def customer_member_login(body: MemberLoginRequest, request: Request, response: Response) -> dict:
    otp_service.check_member_ip_rate_limit(request)
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    sid = ctx["session_id"] if ctx else None
    member = member_service.login_member(
        body.identifier,
        body.password,
        session_id=sid,
        client_ip=_direct_client_ip(request),
    )
    _set_member_cookie_fields(storage, member["id"])
    server_auth.save_customer_storage(response, request, storage)
    state = _build_state_payload(storage)
    state["message"] = f"เข้าสู่ระบบสำเร็จ ยินดีต้อนรับคุณ {member['name']}"
    return state


@router.post("/member/signup")
def customer_member_signup(body: MemberSignupRequest, request: Request, response: Response) -> dict:
    otp_service.check_member_ip_rate_limit(request)
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    sid = ctx["session_id"] if ctx else None
    member = member_service.signup_member(
        name=body.name,
        email=body.email,
        phone=body.phone,
        password=body.password,
        password_confirm=body.password_confirm,
        otp_code=body.otp_code,
        session_id=sid,
    )
    _set_member_cookie_fields(storage, member["id"])
    server_auth.save_customer_storage(response, request, storage)
    state = _build_state_payload(storage)
    state["message"] = f"สมัครสมาชิกสำเร็จ! ยินดีต้อนรับคุณ {member['name']}"
    return state


@router.post("/member/reset/start")
def customer_member_reset_start(body: MemberResetStartRequest, request: Request) -> dict:
    otp_service.check_member_ip_rate_limit(request)
    return member_service.request_password_reset(body.email)


@router.post("/member/reset/verify")
def customer_member_reset_verify(body: MemberResetVerifyRequest, request: Request) -> dict:
    otp_service.check_member_ip_rate_limit(request)
    return member_service.reset_member_password(
        email=body.email,
        otp_code=body.otp_code,
        new_password=body.new_password,
        new_password_confirm=body.new_password_confirm,
    )


@router.post("/member/logout")
def customer_member_logout(request: Request, response: Response) -> dict:
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    sid = ctx["session_id"] if ctx else None
    member, _ = _resolve_member_and_promo(storage, sid)
    if sid and member:
        sess_state = member_service.get_session_member_state(sid)
        if sess_state.get("member_id") == member["id"]:
            member_service.bind_member_to_session(sid, None)
    _clear_member_cookie_fields(storage)
    server_auth.save_customer_storage(response, request, storage)
    state = _build_state_payload(storage)
    state["message"] = "ออกจากระบบสมาชิกแล้ว สามารถสั่งอาหารต่อได้ตามปกติ"
    return state


@router.post("/member/promo/claim")
def customer_claim_promo(body: MemberClaimPromoRequest, request: Request, response: Response) -> dict:
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    sid = ctx["session_id"] if ctx else None
    member, _ = _resolve_member_and_promo(storage, sid)
    if not member:
        raise ValueError("กรุณาเข้าสู่ระบบสมาชิกก่อนเก็บโค้ดส่วนลด")
    updated = member_service.claim_member_promo(member["id"], body.code)
    server_auth.save_customer_storage(response, request, storage)
    state = _build_state_payload(storage)
    state["message"] = f"รับโค้ดพิเศษ \"{(body.code or '').strip().upper()}\" สำเร็จ! กด \"ใช้โค้ดส่วนลดนี้\" เพื่อลดราคาได้เลย"
    state["member"] = updated
    return state


@router.post("/member/promo/apply")
def customer_apply_promo(body: MemberApplyPromoRequest, request: Request, response: Response) -> dict:
    storage = server_auth.load_customer_storage(request)
    ctx = web_session.load_context(storage)
    sid = ctx["session_id"] if ctx else None
    member, _ = _resolve_member_and_promo(storage, sid)
    if not member:
        raise ValueError("กรุณาเข้าสู่ระบบสมาชิกก่อนใช้โค้ดส่วนลด")
    snap = web_session.get_snapshot(sid) if sid else None
    subtotal = float(snap["subtotal"]) if snap else 0.0
    res = member_service.apply_member_promo(member["id"], body.code, sid, subtotal=subtotal)
    if res["applied_promo_code"]:
        storage["applied_promo_code"] = res["applied_promo_code"]
        msg = f"ใช้โค้ด \"{res['applied_promo_code']}\" สำเร็จ! ระบบหักส่วนลดให้ในรายการของฉันและบิลแล้ว"
    else:
        storage.pop("applied_promo_code", None)
        msg = "ยกเลิกการใช้โค้ดส่วนลดแล้ว"
    server_auth.save_customer_storage(response, request, storage)
    state = _build_state_payload(storage)
    state["message"] = msg
    return state
