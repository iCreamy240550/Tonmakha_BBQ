"""ui/widgets/dialogs.py — กล่องโต้ตอบแบบ modal (ยืนยัน / กรอกข้อความ / แจ้งข้อมูล / แจ้งผิดพลาด)

ฟังก์ชันสำเร็จรูป: confirm, ask_text, ask_reason, show_info, show_error
ต้องการหน้าต่างเฉพาะงาน (ฟอร์มหลายช่อง) ให้สืบทอด `BaseDialog` แล้วใส่ widget ใน `self.body`
และเรียก `self.add_buttons(...)`; ปิดด้วย `self.close(result)`; เปิดด้วย `dialog.show()` -> ค่า result
"""
from __future__ import annotations

import customtkinter as ctk

from ui.theme import COLORS, font
from ui.widgets.basic import ActionButton


class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, width: int = 440):
        top = parent.winfo_toplevel()
        super().__init__(top)
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=COLORS["card"])
        self.transient(top)
        self._parent_top = top
        self._width = width
        self.result = None
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=24, pady=(22, 8))
        self.button_row = ctk.CTkFrame(self, fg_color="transparent")
        self.button_row.pack(fill="x", padx=24, pady=(4, 20))

    def add_buttons(self, confirm_text: str = "ตกลง", cancel_text: str | None = "ยกเลิก",
                    variant: str = "primary", on_confirm=None) -> ActionButton:
        """ใส่ปุ่มท้ายกล่อง (ชิดขวา) -> ปุ่มยืนยัน; on_confirm ไม่ส่ง = ปิดด้วย result=True"""
        confirm_btn = ActionButton(self.button_row, confirm_text, on_confirm or (lambda: self.close(True)),
                                   variant=variant, width=120)
        confirm_btn.pack(side="right")
        if cancel_text:
            ActionButton(self.button_row, cancel_text, self.cancel, variant="ghost",
                         width=100).pack(side="right", padx=(0, 10))
        return confirm_btn

    def cancel(self) -> None:
        self.close(None)

    def close(self, result=None) -> None:
        self.result = result
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def show(self):
        """แสดงแบบ modal แล้วรอจนปิด -> result"""
        self.update_idletasks()
        w = self._width
        h = self.winfo_reqheight()
        x = self._parent_top.winfo_rootx() + (self._parent_top.winfo_width() - w) // 2
        y = self._parent_top.winfo_rooty() + (self._parent_top.winfo_height() - h) // 3
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

        def _grab():
            try:
                self.lift()
                self.focus_force()
                self.grab_set()
            except Exception:
                pass
        self.after(80, _grab)
        self.wait_window(self)
        return self.result


def confirm(parent, message: str, title: str = "ยืนยัน", confirm_text: str = "ตกลง",
            cancel_text: str = "ยกเลิก", danger: bool = False) -> bool:
    """ถามยืนยัน -> True/False (danger=True ปุ่มยืนยันเป็นสีแดง)"""
    dlg = BaseDialog(parent, title)
    ctk.CTkLabel(dlg.body, text=message, font=font(16), text_color=COLORS["text"],
                 wraplength=390, justify="left").pack(anchor="w")
    dlg.add_buttons(confirm_text, cancel_text, "danger" if danger else "primary")
    return bool(dlg.show())


def ask_text(parent, prompt: str, title: str = "กรอกข้อมูล", required: bool = True,
             initial: str = "", multiline: bool = False, confirm_text: str = "ตกลง",
             danger: bool = False) -> str | None:
    """ให้กรอกข้อความ -> ข้อความที่ตัดช่องว่างหัวท้ายแล้ว หรือ None ถ้ากดยกเลิก
    required=True จะไม่ยอมให้เว้นว่าง (แสดงข้อความแดงในกล่อง)"""
    dlg = BaseDialog(parent, title)
    ctk.CTkLabel(dlg.body, text=prompt, font=font(16), text_color=COLORS["text"],
                 wraplength=390, justify="left").pack(anchor="w", pady=(0, 8))
    if multiline:
        box = ctk.CTkTextbox(dlg.body, height=90, font=font(15), fg_color=COLORS["input_bg"],
                             border_width=1, border_color=COLORS["input_border"])
        box.pack(fill="x")
        box.insert("1.0", initial)
        get_value = lambda: box.get("1.0", "end").strip()
    else:
        box = ctk.CTkEntry(dlg.body, height=40, font=font(15), fg_color=COLORS["input_bg"],
                           border_color=COLORS["input_border"])
        box.pack(fill="x")
        box.insert(0, initial)
        get_value = lambda: box.get().strip()
    error = ctk.CTkLabel(dlg.body, text="", font=font(13), text_color=COLORS["danger"])
    error.pack(anchor="w", pady=(4, 0))

    def _ok():
        value = get_value()
        if required and not value:
            error.configure(text="กรุณากรอกข้อมูล")
            return
        dlg.close(value)

    dlg.add_buttons(confirm_text, "ยกเลิก", "danger" if danger else "primary", on_confirm=_ok)
    if not multiline:
        box.bind("<Return>", lambda e: _ok())
    dlg.after(150, box.focus_set)
    return dlg.show()


def ask_reason(parent, prompt: str = "เหตุผล", title: str = "ระบุเหตุผล",
               confirm_text: str = "ยืนยัน") -> str | None:
    """ถามเหตุผลที่บังคับกรอก (ใช้กับยกเลิกรายการ/ยกเลิกโต๊ะ ฯลฯ) -> ข้อความ หรือ None"""
    return ask_text(parent, prompt, title=title, required=True, multiline=True,
                    confirm_text=confirm_text, danger=True)


def show_info(parent, message: str, title: str = "แจ้งให้ทราบ") -> None:
    dlg = BaseDialog(parent, title)
    ctk.CTkLabel(dlg.body, text=message, font=font(16), text_color=COLORS["text"],
                 wraplength=390, justify="left").pack(anchor="w")
    dlg.add_buttons("ตกลง", None)
    dlg.show()


def show_error(parent, message: str, title: str = "เกิดข้อผิดพลาด") -> None:
    dlg = BaseDialog(parent, title)
    ctk.CTkLabel(dlg.body, text=message, font=font(16), text_color=COLORS["danger"],
                 wraplength=390, justify="left").pack(anchor="w")
    dlg.add_buttons("ตกลง", None, "danger")
    dlg.show()
