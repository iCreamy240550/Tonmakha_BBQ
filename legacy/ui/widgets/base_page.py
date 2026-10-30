"""ui/widgets/base_page.py — คลาสแม่ของทุกหน้าในแอป PC (staff/ และ owner/)

วิธีทำหน้าใหม่ (ทุกโมดูลหน้าต้องมีคลาสชื่อ `Page`):

    class Page(BasePage):
        title = "โต๊ะ"                 # แสดงที่แถบบน
        auto_refresh_ms = 5000         # None = ไม่รีเฟรชเอง
        def build(self): ...           # สร้าง widget (เรียกครั้งเดียว) — วางบน self ด้วย pack/grid
        def on_show(self, **params): ...   # ทุกครั้งที่เปิดหน้า (params มาจาก app.navigate(key, **params))
        def refresh(self): ...         # โหลดข้อมูลใหม่ (ถูกเรียกตาม auto_refresh_ms และเมื่อแจ้งเตือนเปลี่ยน)
        def on_hide(self): ...

ตัวช่วย: self.app (App), self.user (ผู้ใช้ที่ล็อกอิน dict), self.toast(text, kind),
         self.call(fn, *args, success=None, **kwargs) -> (ok, result) จับ ValueError แล้วแสดงข้อความไทยให้เอง
"""
from __future__ import annotations

import traceback

import customtkinter as ctk

from ui.theme import COLORS
from ui.widgets.toast import show_toast


class BasePage(ctk.CTkFrame):
    title = ""
    auto_refresh_ms: int | None = None

    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.app = app
        self._active = False
        self._refresh_job = None
        self.build()

    # ----- ให้หน้าลูกเขียนทับ -----
    def build(self) -> None: ...
    def on_show(self, **params) -> None: self.refresh()
    def refresh(self) -> None: ...
    def on_hide(self) -> None: ...

    # ----- ตัวช่วย -----
    @property
    def user(self) -> dict:
        return self.app.user

    @property
    def user_id(self) -> int:
        return self.app.user["id"]

    def toast(self, text: str, kind: str = "info") -> None:
        show_toast(self, text, kind)

    def call(self, fn, *args, success: str | None = None, **kwargs):
        """เรียก service อย่างปลอดภัย -> (True, ผลลัพธ์) หรือ (False, None)
        ValueError (ผิดกติกา) แสดง toast สีแดงด้วยข้อความไทยตรง ๆ ; error อื่นแสดงข้อความทั่วไปและพิมพ์ traceback ลงคอนโซล"""
        try:
            result = fn(*args, **kwargs)
        except ValueError as e:
            self.toast(str(e), "error")
            return False, None
        except Exception as e:  # noqa: BLE001 — กันแอปล่ม แสดงให้ผู้ใช้เห็น
            traceback.print_exc()
            self.toast(f"ระบบผิดพลาด: {e}", "error")
            return False, None
        if success:
            self.toast(success, "success")
        return True, result

    # ----- ภายใน (App เรียก) -----
    def activate(self, **params) -> None:
        self._active = True
        try:
            self.on_show(**params)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.toast(f"เปิดหน้าไม่สำเร็จ: {e}", "error")
        self._schedule()

    def deactivate(self) -> None:
        self._active = False
        self._cancel_schedule()
        self.on_hide()

    def reload(self) -> None:
        """สั่งรีเฟรชทันทีถ้าหน้านี้กำลังแสดง (ใช้เมื่อแจ้งเตือน/ข้อมูลเปลี่ยน)"""
        if self._active:
            self._safe_refresh()

    def _safe_refresh(self) -> None:
        try:
            self.refresh()
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    def _schedule(self) -> None:
        self._cancel_schedule()
        if self._active and self.auto_refresh_ms:
            self._refresh_job = self.after(self.auto_refresh_ms, self._tick)

    def _cancel_schedule(self) -> None:
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None

    def _tick(self) -> None:
        self._refresh_job = None
        if self._active:
            self._safe_refresh()
            self._schedule()
