"""ui/alert_center.py — ศูนย์แจ้งเตือนด่วน: โต๊ะเงียบ และ สต๊อกใกล้หมด/สินค้าหมด (แถบแดงใต้แถบบน)

AlertCenter(master, user_provider, on_change=None)
- start() เริ่มตรวจทันที แล้วตรวจซ้ำทุก config.ALERT_CHECK_INTERVAL_SECONDS วินาที ; stop() หยุด
- มีแจ้งเตือน active -> แถบแดงโผล่พร้อมปุ่มจัดการตามประเภทแจ้งเตือน ; ไม่มี -> ซ่อนเอง
  - แจ้งเตือนโต๊ะเงียบ: ปุ่ม ไปเช็คแล้ว / ปล่อยไว้ / ยกเลิกโต๊ะ
  - แจ้งเตือนสต๊อกใกล้หมด/สินค้าหมด: ป้ายระดับ + ปุ่ม รับทราบแล้ว / เตือนซ้ำทีหลัง
- แจ้งเตือนใหม่ -> เล่นเสียงครั้งเดียว (pop_sound_alerts) ; on_change() ถูกเรียกเมื่อรายการเปลี่ยน/กดปุ่ม
- `refresh_view()` โหลดรายการ active ใหม่โดยไม่ตรวจเงื่อนไข
"""
from __future__ import annotations

import sys
import threading
import traceback

import customtkinter as ctk

import config
from services import alert_service
from ui.theme import COLORS, font
from ui.widgets import confirm, show_toast

MAX_VISIBLE_ROWS = 5


def play_alert_sound(widget) -> None:
    """เสียงเตือนสั้น ๆ (Windows = บี๊บ 3 ครั้งใน thread แยก ; ระบบอื่น = bell)"""
    if sys.platform.startswith("win"):
        def _beep():
            try:
                import winsound
                for _ in range(3):
                    winsound.Beep(1200, 250)
            except Exception:
                pass
        threading.Thread(target=_beep, daemon=True).start()
    else:
        try:
            widget.bell()
        except Exception:
            pass


class AlertCenter(ctk.CTkFrame):
    def __init__(self, master, user_provider, on_change=None, show_fn=None, hide_fn=None):
        """show_fn/hide_fn = วิธีแสดง/ซ่อนแถบในเลย์เอาต์ของ App (ไม่ส่ง = pack/pack_forget)"""
        super().__init__(master, fg_color=COLORS["alert_bg"], corner_radius=0)
        self._show_fn = show_fn or (lambda: self.pack(fill="x"))
        self._hide_fn = hide_fn or self.pack_forget
        self._user_provider = user_provider      # callable -> user dict | None
        self._on_change = on_change
        self._job = None
        self._running = False
        self._alerts: list[dict] = []

    # ----- วงจรตรวจ -----
    def start(self) -> None:
        self._running = True
        self._tick()

    def stop(self) -> None:
        self._running = False
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self) -> None:
        self._job = None
        if not self._running:
            return
        changed = False
        try:
            result = alert_service.check_alerts()
            changed = bool(result["new"] or result["woken"] or result["cleared"])
            if alert_service.pop_sound_alerts():
                play_alert_sound(self)
        except Exception:  # noqa: BLE001 — ตรวจพลาดครั้งหนึ่งไม่ควรทำแอปล่ม
            traceback.print_exc()
        self.refresh_view(notify=changed)
        self._job = self.after(config.ALERT_CHECK_INTERVAL_SECONDS * 1000, self._tick)

    # ----- แสดงผล -----
    def refresh_view(self, notify: bool = False) -> None:
        try:
            alerts = alert_service.list_active_alerts()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return
        if [(a["id"], a["message"]) for a in alerts] != [(a["id"], a["message"]) for a in self._alerts]:
            notify = True
        self._alerts = alerts
        self._render()
        if notify and self._on_change:
            self._on_change()

    @property
    def count(self) -> int:
        return len(self._alerts)

    def _render(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        if not self._alerts:
            self._hide_fn()
            return
        self._show_fn()
        stock_cnt = sum(1 for a in self._alerts if a.get("is_stock_alert"))
        table_cnt = len(self._alerts) - stock_cnt
        parts = []
        if table_cnt:
            parts.append(f"โต๊ะเงียบ {table_cnt}")
        if stock_cnt:
            parts.append(f"สต๊อก {stock_cnt}")
        detail_txt = " · ".join(parts) if parts else f"{len(self._alerts)} รายการ"
        head = ctk.CTkLabel(
            self,
            text=f"แจ้งเตือนด่วน ({detail_txt})",
            font=font(14, True),
            text_color=COLORS["alert_text"],
        )
        head.pack(anchor="w", padx=16, pady=(8, 0))

        for alert in self._alerts[:MAX_VISIBLE_ROWS]:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            badge_txt = alert.get("kind_th") or "แจ้งเตือน"
            badge_bg = "#5c0f0f" if alert["kind"] == alert_service.KIND_OUT_OF_STOCK else "#e67700"
            ctk.CTkLabel(
                row,
                text=badge_txt,
                font=font(12, True),
                fg_color=badge_bg,
                text_color="#ffffff",
                corner_radius=6,
                padx=8,
                pady=2,
            ).pack(side="left", padx=(4, 6))
            ctk.CTkLabel(
                row,
                text=alert["message"],
                font=font(16, True),
                text_color=COLORS["alert_text"],
                anchor="w",
            ).pack(side="left", padx=4)

            if alert.get("is_stock_alert"):
                buttons = (
                    ("รับทราบแล้ว", self._checked, "#2f9e44", "#278a3a"),
                    ("ปล่อยไว้", self._snooze, "#e67700", "#c96600"),
                )
            else:
                buttons = (
                    ("ไปเช็คแล้ว", self._checked, "#2f9e44", "#278a3a"),
                    ("ปล่อยไว้", self._snooze, "#e67700", "#c96600"),
                    ("ยกเลิกโต๊ะ", self._cancel_table, "#5c0f0f", "#450b0b"),
                )
            for text, handler, fg, hover in buttons:
                ctk.CTkButton(
                    row,
                    text=text,
                    width=96,
                    height=32,
                    font=font(14, True),
                    fg_color=fg,
                    hover_color=hover,
                    text_color="#ffffff",
                    command=lambda h=handler, a=alert: h(a),
                ).pack(side="right", padx=3)

        if len(self._alerts) > MAX_VISIBLE_ROWS:
            ctk.CTkLabel(
                self,
                text=f"และอีก {len(self._alerts) - MAX_VISIBLE_ROWS} รายการ",
                font=font(13),
                text_color=COLORS["alert_text"],
            ).pack(anchor="w", padx=16, pady=(0, 6))
        else:
            ctk.CTkFrame(self, fg_color="transparent", height=4).pack()

    # ----- ปุ่มพนักงาน -----
    def _act(self, fn, alert: dict, success: str) -> None:
        user = self._user_provider()
        if not user:
            return
        try:
            fn(alert["id"], user["id"])
            show_toast(self, success, "success")
        except ValueError as e:
            show_toast(self, str(e), "error")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            show_toast(self, f"ระบบผิดพลาด: {e}", "error")
        self.refresh_view(notify=True)

    def _checked(self, alert: dict) -> None:
        if alert.get("is_stock_alert"):
            msg = f"รับทราบแจ้งเตือนสต๊อก {alert.get('stock_name') or ''} แล้ว".strip()
        else:
            msg = f"บันทึกว่าไปเช็คโต๊ะ {alert['table_no']} แล้ว"
        self._act(alert_service.mark_checked, alert, msg)

    def _snooze(self, alert: dict) -> None:
        if alert.get("is_stock_alert"):
            msg = f"พักแจ้งเตือนสต๊อก {alert.get('stock_name') or ''} ไว้ก่อน จะเตือนอีกครั้ง".strip()
        else:
            msg = f"ปล่อยโต๊ะ {alert['table_no']} ไว้ก่อน จะเตือนอีกครั้ง"
        self._act(alert_service.snooze, alert, msg)

    def _cancel_table(self, alert: dict) -> None:
        if alert.get("is_stock_alert"):
            return
        if confirm(
            self,
            f"ยกเลิกโต๊ะ {alert['table_no']} ใช่หรือไม่?\n(ใช้เมื่อไม่มีลูกค้าจริง/สแกนมั่ว)",
            title="ยกเลิกโต๊ะ",
            confirm_text="ยกเลิกโต๊ะ",
            danger=True,
        ):
            self._act(alert_service.cancel_table, alert, f"ยกเลิกโต๊ะ {alert['table_no']} แล้ว")
