"""web/pages/waiting.py — หน้ารอพนักงานยืนยัน (สถานะ pending) + ปุ่มยกเลิกคำขอ (กติกาข้อ 6)"""
from __future__ import annotations

from nicegui import ui

from web import components, session


def render(ctx: dict, snap: dict, on_change) -> None:
    """ctx = session.load_context ; snap = session.get_snapshot ; on_change() = สั่งรีเฟรชหน้า"""
    card = components.message_card("hourglass_top", "ส่งคำขอแล้ว กรุณารอพนักงานยืนยัน",
                                   "พนักงานจะยืนยันโต๊ะของคุณสักครู่ เมื่อยืนยันแล้วจะสั่งอาหารได้ทันที",
                                   color="warning", spinner=True)
    with card:
        ui.button("ยกเลิกคำขอ", on_click=lambda: _open_confirm(ctx, on_change)).props("outline color=negative")


def _open_confirm(ctx: dict, on_change) -> None:
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-md"):
        ui.label("ยกเลิกคำขอใช้โต๊ะ?").classes("text-lg font-bold")
        ui.label("ถ้ายกเลิก ต้องสแกน QR ใหม่หากต้องการใช้บริการ").classes("text-base text-grey-8")
        with ui.row().classes("w-full justify-end"):
            ui.button("ไม่ยกเลิก", on_click=dlg.close).props("flat")
            ui.button("ยืนยันยกเลิก", on_click=lambda: _do_cancel(dlg, ctx, on_change)).props("color=negative")
    dlg.open()


def _do_cancel(dlg, ctx: dict, on_change) -> None:
    try:
        session.cancel_request(ctx["session_id"], ctx["device_id"])
    except ValueError as e:  # เช่น พนักงานยืนยัน/ยกเลิกไปก่อนแล้ว
        ui.notify(str(e), type="warning")
    dlg.close()
    on_change()
