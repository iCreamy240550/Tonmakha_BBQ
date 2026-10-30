"""ui/staff/kitchen_page.py — หน้าจอครัว: ออเดอร์ที่ยังไม่เสิร์ฟของทุกโต๊ะ 2 คอลัมน์ (ใหม่ / กำลังทำ) ตัวใหญ่ เห็นชัด

รีเฟรชทุก 3 วินาที ; มีออเดอร์ใหม่เข้า -> เล่นเสียงเตือนสั้น ๆ
"""
from __future__ import annotations

import customtkinter as ctk

from services import order_service
from ui.alert_center import play_alert_sound
from ui.theme import COLORS, ORDER_STATUS_COLORS, font
from ui.widgets import BasePage, EmptyState, OrderCard, PageHeader, ask_reason


class Page(BasePage):
    title = "หน้าจอครัว"
    auto_refresh_ms = 3000

    def build(self) -> None:
        self._signature = None
        self._seen_ids: set[int] | None = None
        self.header = PageHeader(self, "หน้าจอครัว", "")
        self.header.pack(fill="x", padx=24, pady=(18, 8))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        body.grid_columnconfigure((0, 1), weight=1, uniform="k")
        body.grid_rowconfigure(1, weight=1)
        self.columns: dict[str, ctk.CTkScrollableFrame] = {}
        for col, (status, title) in enumerate((("new", "ออเดอร์ใหม่"), ("preparing", "กำลังทำ"))):
            ctk.CTkLabel(body, text=title, font=font(22, True), text_color="#ffffff",
                         fg_color=ORDER_STATUS_COLORS[status], corner_radius=8).grid(
                row=0, column=col, sticky="ew", padx=6, pady=(0, 6), ipady=6)
            frame = ctk.CTkScrollableFrame(body, fg_color="transparent")
            frame.grid(row=1, column=col, sticky="nsew", padx=6)
            self.columns[status] = frame

    def on_show(self, **params) -> None:
        self._seen_ids = None   # เปิดหน้าใหม่ไม่เล่นเสียงของออเดอร์ที่มีอยู่แล้ว
        self._signature = None
        self.refresh()

    def refresh(self) -> None:
        orders = order_service.list_active_orders()
        ids = {o["id"] for o in orders if o["status"] == "new"}
        if self._seen_ids is not None and (ids - self._seen_ids):
            play_alert_sound(self)
        self._seen_ids = ids
        n_new = sum(1 for o in orders if o["status"] == "new")
        self.header.set_subtitle(f"ใหม่ {n_new} · กำลังทำ {len(orders) - n_new}")
        signature = tuple((o["id"], o["status"], tuple((i["id"], i["status"]) for i in o["items"])) for o in orders)
        if signature == self._signature:
            return
        self._signature = signature
        for status, frame in self.columns.items():
            for c in frame.winfo_children():
                c.destroy()
            mine = [o for o in orders if o["status"] == status]
            if not mine:
                EmptyState(frame, "ไม่มีออเดอร์").pack(pady=40)
            for o in mine:
                OrderCard(frame, o, on_status=self.set_status, on_cancel_order=self.cancel_order, big=True).pack(
                    fill="x", padx=4, pady=6)

    def set_status(self, order: dict, new_status: str) -> None:
        ok, _ = self.call(order_service.set_order_status, order["id"], new_status, self.user_id)
        if ok:
            self._signature = None
            self.refresh()

    def cancel_order(self, order: dict) -> None:
        reason = ask_reason(self, f"เหตุผลที่ยกเลิกออเดอร์ โต๊ะ {order['table_no']} (ลูกค้าจะได้รับแจ้ง)", title="ยกเลิกออเดอร์")
        if reason is None:
            return
        ok, _ = self.call(order_service.cancel_order, order["id"], reason, self.user_id, success="ยกเลิกออเดอร์แล้ว")
        if ok:
            self._signature = None
            self.refresh()
