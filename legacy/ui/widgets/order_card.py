"""ui/widgets/order_card.py — การ์ดออเดอร์ 1 ใบ

OrderCard(master, order, on_status=None, on_cancel_item=None, on_cancel_order=None, big=False)
- order = dict จาก order_service (ต้องมี table_no ถ้าอยากโชว์เลขโต๊ะ)
- แสดงปุ่มดำเนินการทีละปุ่มตามลำดับสถานะ:
  - เมื่อสถานะเป็น 'new' (ใหม่): แสดงปุ่ม 'เริ่มทำ' เพียงปุ่มเดียว
  - เมื่อสถานะเป็น 'preparing' (กำลังทำ): แสดงปุ่ม 'เสิร์ฟแล้ว' เพียงปุ่มเดียว
  - เมื่อสถานะเป็น 'served' (เสิร์ฟแล้ว): ไม่แสดงปุ่มดำเนินการซ้ำ
- นำปุ่ม 'ยกเลิก' รายการ และ 'ยกเลิกออเดอร์' ออกจากหน้า UI ตามข้อกำหนด
"""
from __future__ import annotations

import customtkinter as ctk

import config
from ui.theme import COLORS, ORDER_STATUS_COLORS, duration_text, fmt_time, font
from ui.widgets.basic import ActionButton, Card, StatusBadge

ORDER_STATUS_TH = {"new": "ใหม่", "preparing": "กำลังทำ", "served": "เสิร์ฟแล้ว", "cancelled": "ยกเลิก"}


class OrderCard(Card):
    def __init__(self, master, order: dict, on_status=None, on_cancel_item=None,
                 on_cancel_order=None, big: bool = False):
        super().__init__(master, border_width=2 if order["status"] == "new" else 1,
                         border_color=ORDER_STATUS_COLORS.get(order["status"], COLORS["card_border"])
                         if order["status"] in ("new", "preparing") else COLORS["card_border"])
        self._submitting = False
        size = 20 if big else 15
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))
        table_txt = f"โต๊ะ {order['table_no']}" if order.get("table_no") is not None else f"ออเดอร์ #{order['id']}"
        ctk.CTkLabel(head, text=table_txt, font=font(size + 6, True), text_color=COLORS["text"]).pack(side="left")
        StatusBadge(head, ORDER_STATUS_TH.get(order["status"], order["status"]),
                    ORDER_STATUS_COLORS.get(order["status"], COLORS["neutral"]), size=size - 2).pack(side="right")
        sub = f"#{order['id']} · {fmt_time(order['created_at'])}"
        if order["status"] in ("new", "preparing"):
            sub += f" · รอมา {duration_text(order['created_at'])}"
        sub += " · ลูกค้าสั่ง" if order.get("created_by") is None else " · พนักงานสั่ง"
        ctk.CTkLabel(self, text=sub, font=font(size - 3), text_color=COLORS["text_muted"]).pack(
            anchor="w", padx=14)

        for it in order.get("items", []):
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=1)
            served = it.get("status") == "served"
            ctk.CTkLabel(row, text=f"{it['quantity']} × {it['name_snapshot']}", font=font(size, True),
                         text_color=COLORS["text_muted"] if served else COLORS["text"],
                         anchor="w").pack(side="left")
        if order.get("note"):
            ctk.CTkLabel(self, text=f"หมายเหตุ: {order['note']}", font=font(size - 2),
                         text_color=COLORS["warning"], wraplength=300, justify="left").pack(anchor="w", padx=14, pady=2)

        if on_status and order["status"] in ("new", "preparing"):
            btns = ctk.CTkFrame(self, fg_color="transparent")
            btns.pack(fill="x", padx=14, pady=(8, 12))
            h = 48 if big else 36
            if order["status"] == "new":
                self.action_btn = ActionButton(
                    btns, "เริ่มทำ", lambda: self._handle_status(on_status, order, "preparing"),
                    variant="info", height=h, width=110, size=size - 1
                )
                self.action_btn.pack(side="left")
            elif order["status"] == "preparing":
                self.action_btn = ActionButton(
                    btns, "เสิร์ฟแล้ว", lambda: self._handle_status(on_status, order, "served"),
                    variant="success", height=h, width=120, size=size - 1
                )
                self.action_btn.pack(side="left")
        else:
            ctk.CTkFrame(self, fg_color="transparent", height=8).pack()

    def _handle_status(self, callback, order: dict, next_status: str) -> None:
        if self._submitting:
            return
        self._submitting = True
        try:
            if hasattr(self, "action_btn"):
                self.action_btn.configure(state="disabled")
            callback(order, next_status)
        finally:
            self._submitting = False
