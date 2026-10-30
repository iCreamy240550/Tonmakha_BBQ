"""server/routes/shop.py — API เปิด/ปิดร้าน และศูนย์แจ้งเตือนด่วน (AlertCenter)"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.deps import require_staff
from services import alert_service, shop_service

router = APIRouter(prefix="/api/staff", tags=["shop_alerts"])


class CloseShopRequest(BaseModel):
    force: bool = False


@router.get("/shop")
def get_shop_status(_user: dict = Depends(require_staff)) -> dict:
    status = shop_service.get_status()
    status["active_sessions"] = shop_service.active_session_count()
    return status


@router.post("/shop/open")
def open_shop(user: dict = Depends(require_staff)) -> dict:
    shop_service.open_shop(user["id"])
    return {
        **shop_service.get_status(),
        "active_sessions": shop_service.active_session_count(),
        "message": "เปิดร้านแล้ว ลูกค้าสแกน QR เข้าโต๊ะได้",
    }


@router.post("/shop/close")
def close_shop(body: CloseShopRequest, user: dict = Depends(require_staff)) -> dict:
    shop_service.close_shop(user["id"], force=bool(body.force))
    return {
        **shop_service.get_status(),
        "active_sessions": shop_service.active_session_count(),
        "message": "ปิดร้านแล้ว",
    }


@router.get("/alerts")
def get_alerts(check: bool = True, pop_sound: bool = True, _user: dict = Depends(require_staff)) -> dict:
    changed = False
    if check:
        res = alert_service.check_alerts()
        changed = bool(res["new"] or res["woken"] or res["cleared"])
    sound_alerts = alert_service.pop_sound_alerts() if pop_sound else []
    alerts = alert_service.list_active_alerts()
    stock_cnt = sum(1 for a in alerts if a.get("is_stock_alert"))
    table_cnt = len(alerts) - stock_cnt
    return {
        "alerts": alerts,
        "count": len(alerts),
        "table_count": table_cnt,
        "stock_count": stock_cnt,
        "play_sound": len(sound_alerts) > 0,
        "sound_alerts": sound_alerts,
        "changed": changed,
    }


@router.post("/alerts/{alert_id}/check")
def mark_alert_checked(alert_id: int, user: dict = Depends(require_staff)) -> dict:
    alert = alert_service.mark_checked(alert_id, user["id"])
    if alert.get("is_stock_alert"):
        msg = f"รับทราบแจ้งเตือนสต๊อก {alert.get('stock_name') or ''} แล้ว".strip()
    else:
        msg = f"บันทึกว่าไปเช็คโต๊ะ {alert['table_no']} แล้ว"
    return {"alert": alert, "message": msg}


@router.post("/alerts/{alert_id}/snooze")
def snooze_alert(alert_id: int, user: dict = Depends(require_staff)) -> dict:
    alert = alert_service.snooze(alert_id, user["id"])
    if alert.get("is_stock_alert"):
        msg = f"พักแจ้งเตือนสต๊อก {alert.get('stock_name') or ''} ไว้ก่อน จะเตือนอีกครั้ง".strip()
    else:
        msg = f"ปล่อยโต๊ะ {alert['table_no']} ไว้ก่อน จะเตือนอีกครั้ง"
    return {"alert": alert, "message": msg}


@router.post("/alerts/{alert_id}/cancel_table")
def cancel_table_from_alert(alert_id: int, user: dict = Depends(require_staff)) -> dict:
    alert = alert_service.cancel_table(alert_id, user["id"])
    return {"alert": alert, "message": f"ยกเลิกโต๊ะ {alert['table_no']} แล้ว"}
