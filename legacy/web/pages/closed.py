"""web/pages/closed.py — หน้าทางตัน: ร้านปิด / QR ผิด / โต๊ะไม่ว่าง / ชำระแล้ว / ถูกยกเลิก / ไม่พบรอบ

ทุกฟังก์ชันเป็นแค่ "วาดเนื้อหา" (header วาดโดยผู้เรียก) ไม่มีการเปลี่ยนข้อมูล
"""
from __future__ import annotations

from nicegui import ui

from web import components


def render_shop_closed() -> None:
    """สแกนตอนร้านปิด (กติกาข้อ 1)"""
    components.message_card("storefront", "ร้านปิดอยู่", "ขณะนี้ร้านยังไม่เปิดให้บริการ กรุณาลองใหม่อีกครั้งเมื่อร้านเปิด",
                            color="grey")


def render_invalid_qr() -> None:
    """รหัสลับผิด/โต๊ะไม่มีหรือปิดใช้งาน (กติกาข้อ 2)"""
    components.message_card("qr_code_2", "QR ไม่ถูกต้อง", "กรุณาสแกน QR ที่โต๊ะอีกครั้ง หรือแจ้งพนักงาน", color="negative")


def render_table_busy(message: str | None = None) -> None:
    """โต๊ะมีลูกค้าเครื่องอื่นใช้อยู่แล้ว"""
    components.message_card("event_seat", "โต๊ะนี้มีลูกค้าใช้งานอยู่แล้ว",
                            message or "หากเป็นโต๊ะของคุณ กรุณาแจ้งพนักงาน", color="warning")


def render_other_table(table_name: str) -> None:
    """เครื่องนี้ยังมีโต๊ะอื่นที่ใช้งานอยู่ — ไม่เปิดรอบใหม่ซ้อน แต่ให้กลับไปโต๊ะเดิม"""
    card = components.message_card("swap_horiz", f"คุณกำลังใช้งาน {table_name} อยู่",
                                   "หากต้องการเปลี่ยนโต๊ะ กรุณาแจ้งพนักงาน", color="warning")
    with card:
        ui.button("กลับไปที่โต๊ะของฉัน", on_click=lambda: ui.navigate.to("/s")).props("color=primary")


def render_no_session() -> None:
    """เปิดหน้าลูกค้าโดยยังไม่เคยสแกน"""
    components.message_card("qr_code_scanner", "กรุณาสแกน QR ที่โต๊ะ",
                            "สแกน QR บนโต๊ะของคุณด้วยกล้องมือถือเพื่อเริ่มสั่งอาหาร", color="primary")


def render_paid(snap: dict) -> None:
    """รอบ closed: ขอบคุณ + ใบเสร็จ (กติกาข้อ 5: ต้องสแกนใหม่ถึงเข้าได้)"""
    components.message_card("check_circle", "ชำระเงินเรียบร้อย", "ขอบคุณที่มาใช้บริการค่ะ", color="positive")
    if snap.get("bill"):
        components.bill_card(snap["bill"], paid=True)
    ui.label("หากต้องการสั่งเพิ่ม กรุณาสแกน QR ที่โต๊ะใหม่อีกครั้ง").classes("text-sm text-grey-7 text-center w-full")


def render_cancelled(snap: dict) -> None:
    """รอบ cancelled: ไม่แสดงเหตุผลภายในของพนักงาน บอกแค่ว่าต้องสแกนใหม่"""
    by_customer = (snap.get("session") or {}).get("cancelled_by") == "customer"
    components.message_card("cancel", "ยกเลิกคำขอแล้ว" if by_customer else "คำขอถูกยกเลิก",
                            "หากต้องการใช้บริการ กรุณาสแกน QR ที่โต๊ะอีกครั้ง", color="negative")
