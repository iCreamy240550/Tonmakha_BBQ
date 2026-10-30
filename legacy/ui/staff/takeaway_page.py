"""legacy/ui/staff/takeaway_page.py — หน้าสั่งกลับบ้าน (Takeaway POS) สำหรับอ้างอิงความเข้ากันได้กับ legacy UI"""
from __future__ import annotations

import customtkinter as ctk

from services import takeaway_service, weigh_service
from ui.theme import COLORS, font
from ui.widgets import BasePage


class Page(BasePage):
    def __init__(self, master, app):
        self.weigh_grams = 0
        self.cart_map: dict[int, int] = {}
        super().__init__(master, app)

    def build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(head, text="สั่งกลับบ้าน", font=font(24, True), text_color=COLORS["text"]).pack(anchor="w")

        self.weight_var = ctk.StringVar(value="")
        self.search_var = ctk.StringVar(value="")
        self.total_lbl = ctk.CTkLabel(self, text="รวม 0.00 บาท", font=font(18, True), text_color=COLORS["primary"])
        self.total_lbl.pack(anchor="w", padx=20)

    def refresh(self) -> None:
        cat = takeaway_service.get_takeaway_catalog()
        rate = cat["rate"]
        w_amt = weigh_service.calc_amount(self.weigh_grams, rate) if self.weigh_grams > 0 else 0.0
        self.total_lbl.configure(text=f"รวม {w_amt:,.2f} บาท")
