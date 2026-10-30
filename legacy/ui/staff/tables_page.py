"""ui/staff/tables_page.py — หน้าโต๊ะ: ดูสถานะทุกโต๊ะ ยืนยัน/ยกเลิกโต๊ะที่สแกนเข้ามา ไปชั่ง/ออเดอร์/เช็คบิล/ส่งข้อความ

รีเฟรชทุก 4 วินาที (สร้างการ์ดใหม่เฉพาะเมื่อข้อมูลเปลี่ยน)
"""
from __future__ import annotations

import customtkinter as ctk

import config
from services import notice_service, order_service, table_service, weigh_service
from ui.theme import COLORS, baht, duration_text, font, minutes_since, status_color
from ui.widgets import ActionButton, BasePage, Card, PageHeader, StatusBadge, ask_reason, ask_text, confirm

COLUMNS = 4


class Page(BasePage):
    title = "โต๊ะ"
    auto_refresh_ms = 4000

    def build(self) -> None:
        self._signature = None
        self.header = PageHeader(self, "สถานะโต๊ะ", "")
        self.header.pack(fill="x", padx=24, pady=(18, 8))
        legend = ctk.CTkFrame(self.header.right, fg_color="transparent")
        legend.pack()
        for status in (config.TABLE_STATUS_FREE, config.SESSION_PENDING, config.SESSION_OPEN,
                       config.SESSION_AWAITING_PAYMENT):
            StatusBadge(legend, config.SESSION_STATUS_TH[status], status_color(status), size=12).pack(
                side="left", padx=3)
        self.grid_area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_area.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for c in range(COLUMNS):
            self.grid_area.grid_columnconfigure(c, weight=1, uniform="tbl")

    def refresh(self) -> None:
        tables = table_service.list_tables_with_status()
        rows = []
        for t in tables:
            total = 0.0
            if t["status"] in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT):
                total = weigh_service.session_total(t["session_id"]) + order_service.session_total(t["session_id"])
            rows.append((t, round(total, 2), minutes_since(t["started_at"])))
        signature = tuple((t["id"], t["status"], t["session_id"], total, mins) for t, total, mins in rows)
        in_use = sum(1 for t, _, _ in rows if t["status"] != config.TABLE_STATUS_FREE)
        pending = sum(1 for t, _, _ in rows if t["status"] == config.SESSION_PENDING)
        sub = f"ใช้งานอยู่ {in_use}/{len(rows)} โต๊ะ"
        if pending:
            sub += f" · รอยืนยัน {pending} โต๊ะ"
        self.header.set_subtitle(sub)
        if signature == self._signature:
            return
        self._signature = signature
        for child in self.grid_area.winfo_children():
            child.destroy()
        for i, (t, total, _mins) in enumerate(rows):
            card = self._make_card(t, total)
            card.grid(row=i // COLUMNS, column=i % COLUMNS, padx=6, pady=6, sticky="nsew")

    # ---------- การ์ดโต๊ะ ----------
    def _make_card(self, t: dict, total: float) -> Card:
        status = t["status"]
        color = status_color(status)
        card = Card(self.grid_area, border_width=3 if status == config.SESSION_PENDING else 1,
                    border_color=color if status != config.TABLE_STATUS_FREE else COLORS["card_border"])
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(head, text=f"โต๊ะ {t['table_no']}", font=font(22, True), text_color=COLORS["text"]).pack(side="left")
        StatusBadge(head, t["status_th"], color, size=13).pack(side="right")
        if t.get("name") and t["name"] != str(t["table_no"]):
            ctk.CTkLabel(card, text=t["name"], font=font(13), text_color=COLORS["text_muted"]).pack(anchor="w", padx=12)
        if status == config.TABLE_STATUS_FREE:
            ctk.CTkLabel(card, text="ว่าง", font=font(15), text_color=COLORS["text_muted"]).pack(
                anchor="w", padx=12, pady=(14, 22))
            return card
        info = f"นั่งมาแล้ว {duration_text(t['started_at'])}"
        ctk.CTkLabel(card, text=info, font=font(14), text_color=COLORS["text_muted"]).pack(anchor="w", padx=12, pady=(2, 0))
        if status in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT):
            ctk.CTkLabel(card, text=baht(total), font=font(20, True), text_color=COLORS["primary"]).pack(
                anchor="w", padx=12, pady=(2, 0))
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=(8, 12))
        sid = t["session_id"]
        if status == config.SESSION_PENDING:
            ActionButton(btns, "ยืนยัน", lambda: self.confirm_session(sid), "success", width=90, height=34).pack(side="left")
            ActionButton(btns, "ยกเลิก", lambda: self.cancel_session(t), "danger", width=90, height=34).pack(side="left", padx=6)
        elif status == config.SESSION_OPEN:
            ActionButton(btns, "ชั่ง", lambda: self.app.navigate("weigh", session_id=sid), "primary", width=62, height=34).pack(side="left")
            ActionButton(btns, "ออเดอร์", lambda: self.app.navigate("orders", session_id=sid), "info", width=76, height=34).pack(side="left", padx=4)
            ActionButton(btns, "เช็คบิล", lambda: self.app.navigate("checkout", session_id=sid), "success", width=76, height=34).pack(side="left")
            more = ctk.CTkFrame(card, fg_color="transparent")
            more.pack(fill="x", padx=10, pady=(0, 10))
            ActionButton(more, "ส่งข้อความ", lambda: self.send_message(t), "ghost", width=100, height=28, size=13).pack(side="left")
            ActionButton(more, "ยกเลิกโต๊ะ", lambda: self.cancel_session(t), "ghost", width=100, height=28, size=13).pack(side="left", padx=4)
        elif status == config.SESSION_AWAITING_PAYMENT:
            ActionButton(btns, "ไปชำระเงิน", lambda: self.app.navigate("checkout", session_id=sid), "info", width=150, height=36).pack(side="left")
        return card

    # ---------- การกระทำ ----------
    def _after_change(self) -> None:
        self._signature = None
        self.refresh()
        if self.app.alert_center:
            self.app.alert_center.refresh_view(notify=False)

    def confirm_session(self, session_id: int) -> None:
        ok, _ = self.call(table_service.confirm_session, session_id, self.user_id, success="ยืนยันโต๊ะแล้ว ลูกค้าสั่งอาหารได้")
        if ok:
            self._after_change()

    def cancel_session(self, t: dict) -> None:
        if t["status"] == config.SESSION_PENDING:
            if not confirm(self, f"ยกเลิกโต๊ะ {t['table_no']} ใช่หรือไม่?\n(ใช้เมื่อไม่มีลูกค้าจริง/สแกนมั่ว)",
                           title="ยกเลิกโต๊ะ", confirm_text="ยกเลิกโต๊ะ", danger=True):
                return
            reason = "ไม่มีลูกค้าจริง/สแกนมั่ว"
        else:
            reason = ask_reason(self, f"เหตุผลที่ยกเลิกโต๊ะ {t['table_no']}", title="ยกเลิกโต๊ะ")
            if reason is None:
                return
        ok, _ = self.call(table_service.cancel_session, t["session_id"], cancelled_by="staff",
                          user_id=self.user_id, reason=reason, success=f"ยกเลิกโต๊ะ {t['table_no']} แล้ว")
        if ok:
            self._after_change()

    def send_message(self, t: dict) -> None:
        msg = ask_text(self, f"ข้อความถึงลูกค้าโต๊ะ {t['table_no']}", title="ส่งข้อความ", confirm_text="ส่ง")
        if msg:
            self.call(notice_service.send_message, t["session_id"], msg, self.user_id, success="ส่งข้อความแล้ว")
