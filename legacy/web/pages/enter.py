"""web/pages/enter.py — หน้าเข้าจาก QR: /t/<เลขโต๊ะ>?k=<รหัสลับ>

ลำดับตามกติกา (ทำใน qr_service.resolve_scan ฟังก์ชันเดียว): 1) ร้านปิด 2) รหัสผิด 3) สร้างรอบ pending
- **สแกนจริงหลังเบราว์เซอร์เชื่อมต่อแล้วเท่านั้น** (await client.connected()) เพื่อไม่ให้บอตพรีวิวลิงก์
  (เช่น LINE/Facebook) ที่แค่ดึง HTML สร้างรอบ pending หลอกให้พนักงาน
- สแกนสำเร็จแล้วพาไป /s (หน้าหลักของลูกค้า) เพื่อให้รีเฟรช/กดย้อนกลับไม่สแกนซ้ำ
- เครื่องที่ยังมีโต๊ะอื่นค้างอยู่ จะไม่เปิดรอบซ้อน (กันรอบหลุดจากเครื่อง)
"""
from __future__ import annotations

from nicegui import Client, app, ui

from services import qr_service
from web import components, session
from web.pages import closed


async def build(client: Client, table_no: int, k: str = "") -> None:
    components.apply_theme()
    holder = components.page_column()
    with holder:
        components.message_card("qr_code_scanner", "กำลังตรวจสอบ QR...", color="primary", spinner=True)

    await client.connected()

    storage = app.storage.user
    device_id = session.get_device_id(storage)
    outcome = _scan(storage, device_id, table_no, k, _user_agent(client))

    holder.clear()
    with holder:
        if outcome["kind"] == "ok":
            components.message_card("check_circle", "ส่งคำขอแล้ว", "กำลังพาไปหน้าสั่งอาหาร...", color="positive")
            ui.link("ถ้าหน้าไม่เปลี่ยน กดที่นี่", "/s")
            ui.timer(0.3, lambda: ui.navigate.to("/s"), once=True)
        elif outcome["kind"] == "other_table":
            closed.render_other_table(outcome["table_name"])
        elif outcome["code"] == "shop_closed":
            closed.render_shop_closed()
        elif outcome["code"] == "table_busy":
            closed.render_table_busy(outcome.get("message"))
        else:
            closed.render_invalid_qr()


def _user_agent(client: Client) -> str | None:
    try:
        return client.request.headers.get("user-agent")
    except Exception:  # noqa: BLE001 — ไม่มี request ก็ไม่เป็นไร แค่ไม่เก็บ device_info
        return None


def _scan(storage, device_id: str, table_no: int, key: str, user_agent: str | None) -> dict:
    """ตรรกะสแกน (แยกจาก UI) -> {'kind': 'ok'|'other_table'|'fail', 'code', 'message', 'table_name'}"""
    ctx = session.load_context(storage)
    if (ctx and ctx["view"] in (session.VIEW_WAITING, session.VIEW_ORDER, session.VIEW_BILL)
            and ctx["table"] and ctx["table"]["table_no"] != table_no):
        return {"kind": "other_table", "code": "other_table", "message": "", "table_name": ctx["table"]["name"]}
    result = qr_service.resolve_scan(table_no, key, device_id, session.device_info(user_agent))
    if result["ok"]:
        session.remember_session(storage, result["session"]["id"])
        return {"kind": "ok", "code": "ok", "message": result["message"], "table_name": result["table"]["name"]}
    return {"kind": "fail", "code": result["code"], "message": result["message"], "table_name": ""}
