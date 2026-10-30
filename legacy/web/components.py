"""web/components.py — ชิ้นส่วน UI ที่ใช้ร่วมกันทุกหน้าของเว็บลูกค้า (NiceGUI)

หมายเหตุ: ใช้ API ของ NiceGUI พร้อมกำหนดฟอนต์หลักทั้งระบบเป็น Prompt (ดึงจากไฟล์ local /fonts/Prompt-*.ttf)
ฟังก์ชัน format (money/baht/weight_text/fmt_time) คัดลอกพฤติกรรมจาก ui/theme.py
โดยตั้งใจ เพราะ ui/theme.py ต้อง import customtkinter ซึ่งเว็บไม่ควรพึ่ง
"""
from __future__ import annotations

from nicegui import ui

import config

# สีตามชื่อสีของ Quasar (ui.colors) — โทนเดียวกับแอป PC
BRAND_COLORS = {
    "primary": "#e8590c",
    "secondary": "#2b2118",
    "accent": "#7a6d60",
    "positive": "#2f9e44",
    "negative": "#e03131",
    "warning": "#f08c00",
    "info": "#1c7ed6",
}

# ข้อความสถานะรอบสำหรับลูกค้า (ไม่ใช้ SESSION_STATUS_TH ของพนักงานตรง ๆ)
CUSTOMER_STATUS_TH = {
    config.SESSION_PENDING: "รอพนักงานยืนยัน",
    config.SESSION_OPEN: "สั่งอาหารได้",
    config.SESSION_AWAITING_PAYMENT: "รอชำระเงิน",
    config.SESSION_CLOSED: "ชำระแล้ว",
    config.SESSION_CANCELLED: "ยกเลิกแล้ว",
}
CUSTOMER_STATUS_COLOR = {
    config.SESSION_PENDING: "warning",
    config.SESSION_OPEN: "positive",
    config.SESSION_AWAITING_PAYMENT: "info",
    config.SESSION_CLOSED: "grey",
    config.SESSION_CANCELLED: "negative",
}
ORDER_STATUS_CUSTOMER_TH = {"new": "รับออเดอร์แล้ว", "preparing": "กำลังทำ", "served": "เสิร์ฟแล้ว", "cancelled": "ยกเลิก"}
ORDER_STATUS_COLOR = {"new": "info", "preparing": "warning", "served": "positive", "cancelled": "grey"}

# ไอคอน (Material icons) ตามชนิดข้อความแจ้งลูกค้า
NOTICE_ICONS = {"sold_out": "block", "item_cancelled": "cancel", "staff_message": "campaign", "info": "info"}
NOTICE_NOTIFY_TYPES = {"sold_out": "warning", "item_cancelled": "negative", "staff_message": "info", "info": "info"}

LOGO_URL = "/logo.png"  # server.py ลงทะเบียนไฟล์โลโก้ไฟล์เดียว (ไม่เปิดโฟลเดอร์ assets เพราะมี QR ลับ)

PROMPT_FONT_HEAD_HTML = """
<style>
@font-face {
    font-family: 'Prompt';
    src: url('/fonts/Prompt-Regular.ttf') format('truetype');
    font-weight: 400;
    font-style: normal;
    font-display: swap;
}
@font-face {
    font-family: 'Prompt';
    src: url('/fonts/Prompt-Bold.ttf') format('truetype');
    font-weight: 700;
    font-style: normal;
    font-display: swap;
}
html, body, .q-app, .nicegui-content, button, input, optgroup, select, textarea,
.q-btn, .q-field, .q-card, .q-badge, .q-dialog, .q-notification {
    font-family: 'Prompt', sans-serif !important;
}
</style>
"""


# ---------------------------------------------------------------- จัดรูปแบบข้อความ

def money(value) -> str:
    """1234.5 -> '1,234.50'"""
    return f"{float(value or 0):,.2f}"


def baht(value) -> str:
    """1234.5 -> '1,234.50 บาท'"""
    return f"{money(value)} บาท"


def weight_text(grams) -> str:
    """1500 -> '1.5 กก. (15 ขีด)' ; 300 -> '3 ขีด'"""
    g = float(grams or 0)
    kheed_txt = f"{g / (config.GRAMS_PER_KG / config.KHEED_PER_KG):g}"
    if g >= config.GRAMS_PER_KG:
        return f"{g / config.GRAMS_PER_KG:g} กก. ({kheed_txt} ขีด)"
    return f"{kheed_txt} ขีด"


def fmt_time(text: str | None) -> str:
    """'2026-10-10 18:05:33' -> '18:05'"""
    return text[11:16] if text and len(text) >= 16 else ""


def fmt_datetime(text: str | None) -> str:
    """'2026-10-10 18:05:33' -> '10/10/2026 18:05'"""
    if not text or len(text) < 16:
        return ""
    return f"{text[8:10]}/{text[5:7]}/{text[0:4]} {text[11:16]}"


# ---------------------------------------------------------------- โครงหน้า

def apply_theme() -> None:
    """ตั้งสีแบรนด์ พื้นหลังหน้า และฟอนต์ Prompt — เรียกต้นฟังก์ชันของทุกหน้า"""
    ui.colors(**BRAND_COLORS)
    if hasattr(ui, "add_head_html"):
        ui.add_head_html(PROMPT_FONT_HEAD_HTML)
    q_body = ui.query("body").classes("bg-orange-50")
    if hasattr(q_body, "style"):
        q_body.style("font-family: 'Prompt', sans-serif;")


def page_column():
    """กล่องเนื้อหากลางจอ กว้างสุดแบบมือถือ — ใช้เป็น `with page_column():`"""
    return ui.column().classes("w-full max-w-md mx-auto p-3 gap-3 items-stretch")


def header(table_name: str, status: str | None = None) -> None:
    """แถบหัวหน้า: โลโก้ + ชื่อร้าน + ชื่อโต๊ะ + ป้ายสถานะ (status = ค่าสถานะรอบในฐานข้อมูล)"""
    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.row().classes("items-center no-wrap gap-2"):
                if config.LOGO_PATH.exists():
                    ui.image(LOGO_URL).classes("w-10 h-10")
                with ui.column().classes("gap-0"):
                    ui.label(config.APP_NAME_SHORT).classes("text-xs text-grey-7")
                    ui.label(table_name).classes("text-lg font-bold")
            if status:
                ui.badge(CUSTOMER_STATUS_TH.get(status, status),
                         color=CUSTOMER_STATUS_COLOR.get(status, "grey"))


def message_card(icon: str, title: str, text: str | None = None, color: str = "grey",
                 spinner: bool = False):
    """การ์ดข้อความกลางจอ (ร้านปิด/QR ผิด/รอยืนยัน ฯลฯ) -> card (ใส่ปุ่มต่อท้ายได้ด้วย `with card:`)"""
    card = ui.card().classes("w-full items-center text-center gap-2 p-6")
    with card:
        if spinner:
            ui.spinner(size="xl", color=color)
        else:
            ui.icon(icon, color=color).classes("text-6xl")
        ui.label(title).classes("text-xl font-bold")
        if text:
            ui.label(text).classes("text-base text-grey-8")
    return card


def section_title(text: str) -> None:
    ui.label(text).classes("text-base font-bold text-grey-9 mt-1")


def summary_row(label: str, value: str, bold: bool = False, color: str | None = None) -> None:
    """แถว 'ป้าย ........ ค่า' ชิดซ้าย-ขวา"""
    cls = "text-lg font-bold" if bold else "text-base"
    if color:
        cls += f" text-{color}"
    with ui.row().classes("w-full justify-between no-wrap"):
        ui.label(label).classes(cls)
        ui.label(value).classes(cls)


# ---------------------------------------------------------------- รายการ/บิล

def lines_block(weigh_entries: list[dict], orders: list[dict]) -> None:
    """รายการชั่ง + รายการสั่ง (ที่ไม่ยกเลิก) แบบสรุปบรรทัดละรายการ — ใช้ในบิล"""
    for w in weigh_entries:
        summary_row(f"{w['name_snapshot']}  {weight_text(w['weight_grams'])}", money(w["amount"]))
    for o in orders:
        for it in o["items"]:
            summary_row(f"{it['name_snapshot']}  x{it['quantity']}", money(it["line_total"]))


def bill_card(bill: dict, paid: bool = False) -> None:
    """การ์ดบิล — ใช้ได้ทั้งบิลคำนวณสด (awaiting_payment) และบิลที่บันทึกแล้ว (closed, paid=True)
    ฟิลด์ที่อ่าน: subtotal, discount, promo_name, service_charge(+_percent), vat(+_percent), total,
    weigh_entries, orders, (paid) payment_method_th, amount_received, change_amount, paid_at"""
    with ui.card().classes("w-full gap-1"):
        ui.label("ใบเสร็จรับเงิน" if paid else "รายการที่ต้องชำระ").classes("text-base font-bold")
        lines_block(bill.get("weigh_entries") or [], bill.get("orders") or [])
        ui.separator()
        summary_row("รวมเป็นเงินก่อนคิดภาษีและส่วนลด", money(bill["subtotal"]))
        if bill.get("discount"):
            promo = f" ({bill['promo_name']})" if bill.get("promo_name") else ""
            summary_row(f"ส่วนลด{promo}", "-" + money(bill["discount"]), color="positive")
        if bill.get("service_charge"):
            pct = bill.get("service_charge_percent")
            summary_row(f"ค่าบริการ {pct:g}%" if pct else "ค่าบริการ", money(bill["service_charge"]))
        if bill.get("vat"):
            pct = bill.get("vat_percent")
            summary_row(f"ภาษีมูลค่าเพิ่ม {pct:g}%" if pct else "ภาษีมูลค่าเพิ่ม", money(bill["vat"]))
        ui.separator()
        summary_row("ยอดชำระสุทธิ", baht(bill["total"]), bold=True, color="primary")
        if paid:
            if bill.get("payment_method_th"):
                summary_row("ชำระโดย", bill["payment_method_th"])
            if bill.get("payment_method") == "cash":
                if bill.get("amount_received") is not None:
                    summary_row("รับเงินมา", baht(bill["amount_received"]))
                summary_row("เงินทอน", baht(bill.get("change_amount", 0.0)))
            if bill.get("paid_at"):
                summary_row("เวลาชำระ", fmt_datetime(bill["paid_at"]))
