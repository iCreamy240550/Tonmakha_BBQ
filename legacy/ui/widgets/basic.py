"""ui/widgets/basic.py — ชิ้นส่วน UI พื้นฐานที่ใช้ซ้ำทุกหน้า

Card, PageHeader, ActionButton, StatusBadge, LabeledEntry, StatTile, EmptyState
"""
from __future__ import annotations

import customtkinter as ctk

from ui.theme import COLORS, font

_VARIANTS = {   # variant -> (fg, hover, text)
    "primary": (COLORS["primary"], COLORS["primary_hover"], "#ffffff"),
    "success": (COLORS["success"], COLORS["success_hover"], "#ffffff"),
    "danger": (COLORS["danger"], COLORS["danger_hover"], "#ffffff"),
    "info": (COLORS["info"], COLORS["info_hover"], "#ffffff"),
    "neutral": (COLORS["neutral"], COLORS["neutral_hover"], "#ffffff"),
    "ghost": ("transparent", COLORS["row_hover"], COLORS["text"]),
}


class Card(ctk.CTkFrame):
    """กรอบสีขาวมุมมนมีขอบบาง ๆ"""
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", COLORS["card"])
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["card_border"])
        kwargs.setdefault("corner_radius", 12)
        super().__init__(master, **kwargs)


class ActionButton(ctk.CTkButton):
    """ปุ่มมาตรฐาน variant = primary | success | danger | info | neutral | ghost"""
    def __init__(self, master, text: str, command=None, variant: str = "primary",
                 height: int = 40, width: int = 0, size: int = 15, **kwargs):
        fg, hover, txt = _VARIANTS[variant]
        if variant == "ghost":
            kwargs.setdefault("border_width", 1)
            kwargs.setdefault("border_color", COLORS["input_border"])
        super().__init__(master, text=text, command=command, fg_color=fg, hover_color=hover,
                         text_color=txt, height=height, width=width or 140,
                         font=font(size, True), corner_radius=8, **kwargs)

    def set_variant(self, variant: str) -> None:
        fg, hover, txt = _VARIANTS[variant]
        self.configure(fg_color=fg, hover_color=hover, text_color=txt)


class StatusBadge(ctk.CTkLabel):
    """ป้ายสีมุมมน เช่น สถานะโต๊ะ"""
    def __init__(self, master, text: str = "", color: str = COLORS["neutral"], size: int = 13, **kwargs):
        super().__init__(master, text=text, fg_color=color, text_color="#ffffff",
                         font=font(size, True), corner_radius=12, padx=12, pady=2, **kwargs)

    def set(self, text: str, color: str) -> None:
        self.configure(text=text, fg_color=color)


class PageHeader(ctk.CTkFrame):
    """หัวหน้า: ชื่อหน้า + คำอธิบายรอง; `self.right` คือที่วางปุ่ม/ตัวกรองมุมขวา"""
    def __init__(self, master, title: str, subtitle: str | None = None):
        super().__init__(master, fg_color="transparent", height=1)   # height=1: กันกรอบว่างสูง 200 ตามค่าเริ่มต้นของ CTkFrame
        left = ctk.CTkFrame(self, fg_color="transparent", height=1)
        left.pack(side="left")
        ctk.CTkLabel(left, text=title, font=font(24, True), text_color=COLORS["text"]).pack(anchor="w")
        self.subtitle_label = None
        if subtitle is not None:    # '' = ยังไม่มีข้อความแต่สร้างช่องไว้ให้ set_subtitle
            self.subtitle_label = ctk.CTkLabel(left, text=subtitle, font=font(14),
                                               text_color=COLORS["text_muted"])
            self.subtitle_label.pack(anchor="w")
        self.right = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        self.right.pack(side="right")

    def set_subtitle(self, text: str) -> None:
        if self.subtitle_label is not None:
            self.subtitle_label.configure(text=text)


class LabeledEntry(ctk.CTkFrame):
    """ช่องกรอกพร้อมป้ายชื่อด้านบน; `.get()` `.set(v)` `.entry` ; show='*' สำหรับรหัสผ่าน"""
    def __init__(self, master, label: str, show: str | None = None, placeholder: str = "",
                 width: int = 0, **kwargs):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=label, font=font(14), text_color=COLORS["text_muted"]).pack(anchor="w")
        opts = {"show": show} if show else {}
        self.entry = ctk.CTkEntry(self, height=42, font=font(16), placeholder_text=placeholder,
                                  fg_color=COLORS["input_bg"], border_color=COLORS["input_border"],
                                  text_color=COLORS["text"], width=width or 200, **opts, **kwargs)
        self.entry.pack(fill="x", pady=(2, 0))

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, value: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, value)

    def clear(self) -> None:
        self.entry.delete(0, "end")


class StatTile(Card):
    """การ์ดตัวเลขสรุป เช่น ยอดขายวันนี้; `.set(value, hint=None)`"""
    def __init__(self, master, title: str, value: str = "-", color: str = COLORS["text"]):
        super().__init__(master)
        ctk.CTkLabel(self, text=title, font=font(14), text_color=COLORS["text_muted"]).pack(
            anchor="w", padx=16, pady=(12, 0))
        self.value_label = ctk.CTkLabel(self, text=value, font=font(28, True), text_color=color)
        self.value_label.pack(anchor="w", padx=16)
        self.hint_label = ctk.CTkLabel(self, text="", font=font(12), text_color=COLORS["text_muted"])
        self.hint_label.pack(anchor="w", padx=16, pady=(0, 10))

    def set(self, value: str, hint: str | None = None) -> None:
        self.value_label.configure(text=value)
        self.hint_label.configure(text=hint or "")


class EmptyState(ctk.CTkLabel):
    """ข้อความกลาง ๆ เมื่อไม่มีข้อมูล"""
    def __init__(self, master, text: str = "ไม่มีข้อมูล"):
        super().__init__(master, text=text, font=font(16), text_color=COLORS["text_muted"])
