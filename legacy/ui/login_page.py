"""ui/login_page.py — หน้าล็อกอินของพนักงาน/เจ้าของร้าน

LoginPage(master, on_success) — เรียก on_success(user_dict) เมื่อล็อกอินสำเร็จ
"""
from __future__ import annotations

import customtkinter as ctk
from PIL import Image

import config
from services import auth_service
from ui.theme import COLORS, font
from ui.widgets import ActionButton, Card, LabeledEntry


class LoginPage(ctk.CTkFrame):
    def __init__(self, master, on_success):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.on_success = on_success

        card = Card(self, width=420)
        card.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=40, pady=32)

        try:
            img = Image.open(config.LOGO_PATH)
            self._logo = ctk.CTkImage(light_image=img, size=(120, 120))
            ctk.CTkLabel(inner, image=self._logo, text="").pack(pady=(0, 8))
        except Exception:  # ไม่มีโลโก้ก็ใช้งานได้
            pass
        ctk.CTkLabel(inner, text=config.APP_NAME_SHORT, font=font(28, True),
                     text_color=COLORS["primary"]).pack()
        ctk.CTkLabel(inner, text="เข้าสู่ระบบพนักงาน / เจ้าของร้าน", font=font(15),
                     text_color=COLORS["text_muted"]).pack(pady=(0, 18))

        self.username = LabeledEntry(inner, "ชื่อผู้ใช้", width=300)
        self.username.pack(fill="x", pady=(0, 10))
        self.password = LabeledEntry(inner, "รหัสผ่าน", show="*", width=300)
        self.password.pack(fill="x")
        self.error = ctk.CTkLabel(inner, text="", font=font(14), text_color=COLORS["danger"],
                                  wraplength=300)
        self.error.pack(pady=(8, 0))
        self.button = ActionButton(inner, "เข้าสู่ระบบ", self.submit, height=46, width=300, size=17)
        self.button.pack(pady=(8, 0))

        for entry in (self.username.entry, self.password.entry):
            entry.bind("<Return>", lambda e: self.submit())
        self.after(200, self.username.entry.focus_set)

    def submit(self) -> None:
        username, password = self.username.get(), self.password.entry.get()
        if not username or not password:
            self.error.configure(text="กรุณากรอกชื่อผู้ใช้และรหัสผ่าน")
            return
        self.button.configure(state="disabled", text="กำลังตรวจสอบ...")
        self.update_idletasks()
        try:
            user = auth_service.login(username, password)
        except Exception as e:  # noqa: BLE001 — เช่น ฐานข้อมูลยังไม่ถูกสร้าง
            self.error.configure(text=f"เข้าสู่ระบบไม่ได้: {e}")
            self.button.configure(state="normal", text="เข้าสู่ระบบ")
            return
        if user is None:
            self.error.configure(text="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
            self.password.clear()
            self.button.configure(state="normal", text="เข้าสู่ระบบ")
            self.password.entry.focus_set()
            return
        self.on_success(user)
