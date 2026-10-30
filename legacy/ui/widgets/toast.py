"""ui/widgets/toast.py — ข้อความแจ้งสั้น ๆ มุมขวาล่างของหน้าต่าง หายเองใน 3 วินาที"""
from __future__ import annotations

import customtkinter as ctk

from ui.theme import COLORS, font

_KIND_COLORS = {
    "info": COLORS["sidebar"],
    "success": COLORS["success"],
    "error": COLORS["danger"],
    "warning": COLORS["warning"],
}

_current: dict[int, tuple] = {}   # id(root) -> (label, after_job)


def show_toast(widget, text: str, kind: str = "info", ms: int = 3000) -> None:
    """แสดงข้อความ kind = 'info' | 'success' | 'error' | 'warning' (error อยู่นานกว่าปกติ)"""
    root = widget.winfo_toplevel()
    key = id(root)
    old = _current.pop(key, None)
    if old:
        try:
            root.after_cancel(old[1])
            old[0].destroy()
        except Exception:
            pass
    label = ctk.CTkLabel(root, text=text, font=font(15, True), text_color="#ffffff",
                         fg_color=_KIND_COLORS.get(kind, _KIND_COLORS["info"]),
                         corner_radius=10, padx=18, pady=10, wraplength=520, justify="left")
    label.place(relx=1.0, rely=1.0, x=-24, y=-24, anchor="se")
    label.lift()

    def _hide():
        _current.pop(key, None)
        try:
            label.destroy()
        except Exception:
            pass

    job = root.after(ms * 2 if kind == "error" else ms, _hide)
    _current[key] = (label, job)
