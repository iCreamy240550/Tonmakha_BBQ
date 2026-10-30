"""web/pages/bill.py — หน้าบิลระหว่างรอชำระ (สถานะ awaiting_payment) ลูกค้าดูอย่างเดียว"""
from __future__ import annotations

from nicegui import ui

from web import components


def render(snap: dict) -> None:
    """snap = session.get_snapshot (ใช้ snap['bill'] = บิลคำนวณสด จาก checkout_service.preview)"""
    components.message_card("receipt_long", "พนักงานกำลังเช็คบิลให้ที่โต๊ะ",
                            "กรุณาชำระเงินกับพนักงาน", color="info")
    bill = snap.get("bill")
    if bill is None:
        ui.label("ยังโหลดบิลไม่ได้ กรุณาสอบถามพนักงาน").classes("text-base text-grey-8 text-center w-full")
        return
    components.bill_card(bill)
    ui.label("ยอดสุทธิอาจเปลี่ยนตามโปรโมชั่นที่พนักงานใช้ตอนชำระเงิน").classes("text-sm text-grey-7 text-center w-full")
