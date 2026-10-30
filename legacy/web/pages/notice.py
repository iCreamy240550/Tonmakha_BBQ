"""web/pages/notice.py — ข้อความแจ้งลูกค้า (เมนูหมด / ยกเลิกรายการ / พนักงานส่งข้อความ)

- show_unread(snap): เด้งข้อความที่ยังไม่อ่านขึ้นจอแล้วทำเครื่องหมายว่าอ่านแล้ว (เรียกจาก timer ของหน้าหลัก)
- render(snap): ประวัติข้อความทั้งหมดของรอบ (แท็บ "ข้อความ")
"""
from __future__ import annotations

from nicegui import ui

from web import components, session


def show_unread(snap: dict | None) -> int:
    """แสดง toast ของข้อความที่ยังไม่อ่าน (เก่าสุดก่อน) แล้ว mark_read -> จำนวนที่แสดง"""
    if not snap or not snap.get("unread"):
        return 0
    shown = []
    for n in snap["unread"]:
        ui.notify(n["message"], type=components.NOTICE_NOTIFY_TYPES.get(n["kind"], "info"),
                  position="top", timeout=8000, close_button="ปิด")
        shown.append(n["id"])
    session.mark_notices_read(shown)
    return len(shown)


def render(snap: dict) -> None:
    """ประวัติข้อความ (ใหม่สุดก่อน)"""
    notices = snap.get("notices") or []
    if not notices:
        components.message_card("notifications_none", "ยังไม่มีข้อความ",
                                "ข้อความจากร้าน เช่น เมนูหมด จะแสดงที่นี่", color="grey")
        return
    for n in notices:
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-start no-wrap gap-3"):
                ui.icon(components.NOTICE_ICONS.get(n["kind"], "info"),
                        color=components.NOTICE_NOTIFY_TYPES.get(n["kind"], "info")).classes("text-2xl")
                with ui.column().classes("gap-0"):
                    ui.label(n["message"]).classes("text-base")
                    ui.label(components.fmt_time(n["created_at"])).classes("text-xs text-grey-7")
