"""ui/staff/shop_control.py — สวิตช์เปิด/ปิดร้านที่แถบบน (App สร้างให้เอง)

ShopControl(master, app) — ป้ายสถานะ + ปุ่มเปิด/ปิดร้าน ; `refresh()` อ่านสถานะจริงจากฐานข้อมูล
ปิดร้านตอนยังมีโต๊ะค้าง: ถามยืนยันก่อนว่าจะปิดทั้งที่มีโต๊ะค้างหรือไม่ (force)
"""
from __future__ import annotations

import traceback

import customtkinter as ctk

from services import shop_service
from ui.theme import COLORS
from ui.widgets import ActionButton, StatusBadge, confirm, show_toast


class ShopControl(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.button = ActionButton(self, "เปิดร้าน", self.toggle, variant="success", height=36, width=110)
        self.button.pack(side="right")
        self.badge = StatusBadge(self, "ร้านปิด", COLORS["neutral"], size=15)
        self.badge.pack(side="right", padx=(0, 10))

    def refresh(self) -> None:
        opened = shop_service.is_open()
        self.badge.set("ร้านเปิด" if opened else "ร้านปิด", COLORS["success"] if opened else COLORS["neutral"])
        self.button.configure(text="ปิดร้าน" if opened else "เปิดร้าน")
        self.button.set_variant("danger" if opened else "success")

    def toggle(self) -> None:
        user_id = self.app.user["id"]
        try:
            if not shop_service.is_open():
                shop_service.open_shop(user_id)
                show_toast(self, "เปิดร้านแล้ว ลูกค้าสแกน QR เข้าโต๊ะได้", "success")
            else:
                if not confirm(self, "ปิดร้านใช่หรือไม่?\nลูกค้าจะสแกน QR เข้าโต๊ะไม่ได้", title="ปิดร้าน",
                               confirm_text="ปิดร้าน", danger=True):
                    return
                try:
                    shop_service.close_shop(user_id)
                except ValueError as e:     # มีโต๊ะค้าง -> ให้เลือก force
                    if not confirm(self, f"{e}\n\nต้องการปิดร้านทั้งที่ยังมีโต๊ะค้างหรือไม่?",
                                   title="มีโต๊ะค้างอยู่", confirm_text="ปิดร้านเลย", danger=True):
                        return
                    shop_service.close_shop(user_id, force=True)
                show_toast(self, "ปิดร้านแล้ว", "success")
        except ValueError as e:
            show_toast(self, str(e), "error")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            show_toast(self, f"ระบบผิดพลาด: {e}", "error")
        self.refresh()
