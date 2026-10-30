"""ui/staff/weigh_page.py — หน้าชั่งน้ำหนัก: เลือกโต๊ะ + กรอกน้ำหนัก -> บันทึก (คิดราคาตามอัตรา กิโลกรัมละ 299 บาท จากตั้งค่า)

เปิดจากหน้าโต๊ะด้วย `app.navigate('weigh', session_id=...)` ; เลือกโต๊ะเองได้ (เฉพาะโต๊ะสถานะใช้งาน)
กติกาการชั่งน้ำหนัก:
- การชั่งครั้งแรกของแต่ละโต๊ะในรอบการให้บริการนั้น ต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม (1,000 กรัม)
- หลังจากบันทึกการชั่งครั้งแรกสำเร็จแล้ว การชั่งครั้งถัดไปของโต๊ะเดิมสามารถชั่งน้ำหนักเท่าใดก็ได้
หน่วยกรอก: ขีด (ทศนิยมได้ เช่น 2.5), กรัม, หรือ กิโลกรัม
"""
from __future__ import annotations

import customtkinter as ctk

import config
from services import table_service, weigh_service
from ui.theme import COLORS, baht, fmt_time, font, money, weight_text
from ui.widgets import ActionButton, BasePage, Card, DataTable, PageHeader, ask_reason

UNITS = ["ขีด", "กรัม", "กิโลกรัม"]


def _format_rate_text(rate: float) -> str:
    if rate == int(rate):
        return f"กิโลกรัมละ {int(rate):,} บาท"
    return f"กิโลกรัมละ {rate:,.2f} บาท"


class Page(BasePage):
    title = "ชั่งน้ำหนัก"
    auto_refresh_ms = 6000

    def build(self) -> None:
        self.session_id: int | None = None
        self._tables: dict[str, int] = {}      # ป้ายโต๊ะ -> session_id
        self._rate: float = weigh_service.get_price_per_kg()
        self._saving: bool = False

        PageHeader(self, "ชั่งน้ำหนัก", "เลือกโต๊ะ กรอกน้ำหนัก แล้วกดบันทึก (ชั่งครั้งแรกของแต่ละโต๊ะต้องอย่างน้อย 1 กก.)").pack(fill="x", padx=24, pady=(18, 8))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        body.grid_columnconfigure(0, weight=3, uniform="w")
        body.grid_columnconfigure(1, weight=2, uniform="w")
        body.grid_rowconfigure(0, weight=1)

        # ---- ซ้าย: ฟอร์มชั่ง (เฉพาะเลือกโต๊ะ + อัตราราคา + กรอกน้ำหนัก) ----
        left = Card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        top = ctk.CTkFrame(left, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(top, text="โต๊ะ", font=font(16, True), text_color=COLORS["text"]).pack(side="left")
        self.table_menu = ctk.CTkOptionMenu(
            top, values=["-"], width=220, height=40, font=font(16),
            dropdown_font=font(15), command=self._on_table_picked
        )
        self.table_menu.pack(side="left", padx=12)

        rate_box = ctk.CTkFrame(left, fg_color=COLORS["row_alt"], corner_radius=10, border_width=1, border_color=COLORS["card_border"])
        rate_box.pack(fill="x", padx=18, pady=(4, 12))
        ctk.CTkLabel(rate_box, text="อัตราราคาหมูกระทะชั่งกิโล", font=font(14), text_color=COLORS["text_muted"]).pack(anchor="w", padx=14, pady=(10, 0))
        self.rate_label = ctk.CTkLabel(
            rate_box,
            text=_format_rate_text(self._rate),
            font=font(22, True),
            text_color=COLORS["primary"],
        )
        self.rate_label.pack(anchor="w", padx=14, pady=(2, 10))

        wrow = ctk.CTkFrame(left, fg_color="transparent")
        wrow.pack(fill="x", padx=18, pady=(8, 6))
        ctk.CTkLabel(wrow, text="น้ำหนัก", font=font(16, True), text_color=COLORS["text"]).pack(side="left")
        self.weight_var = ctk.StringVar()
        self.weight_entry = ctk.CTkEntry(
            wrow, textvariable=self.weight_var, width=140, height=48, font=font(24, True),
            justify="right", fg_color=COLORS["input_bg"], border_color=COLORS["input_border"]
        )
        self.weight_entry.pack(side="left", padx=10)
        self.unit = ctk.CTkSegmentedButton(
            wrow, values=UNITS, command=lambda v: self._update_calc(), font=font(15),
            selected_color=COLORS["primary"], selected_hover_color=COLORS["primary_hover"]
        )
        self.unit.set("ขีด")
        self.unit.pack(side="left")
        self.weight_var.trace_add("write", lambda *a: self._update_calc())
        self.weight_entry.bind("<Return>", lambda e: self.save())

        quick = ctk.CTkFrame(left, fg_color="transparent")
        quick.pack(fill="x", padx=18, pady=4)
        for label, kheed in (("+1 ขีด", 1), ("+2 ขีด", 2), ("+5 ขีด", 5), ("+10 ขีด", 10)):
            ActionButton(quick, label, lambda k=kheed: self._add_kheed(k), "ghost", height=34, width=80, size=13).pack(side="left", padx=(0, 6))
        ActionButton(quick, "ล้าง", lambda: self.weight_var.set(""), "ghost", height=34, width=60, size=13).pack(side="left")

        self.calc_label = ctk.CTkLabel(left, text="", font=font(18, True), text_color=COLORS["text_muted"], justify="left")
        self.calc_label.pack(anchor="w", padx=18, pady=(16, 6))
        self.save_button = ActionButton(left, "บันทึกการชั่ง", self.save, "success", height=52, width=240, size=18)
        self.save_button.pack(anchor="w", padx=18, pady=(6, 18))

        # ---- ขวา: รายการที่ชั่งแล้ว ----
        right = Card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.list_title = ctk.CTkLabel(right, text="รายการที่ชั่งแล้ว", font=font(18, True), text_color=COLORS["text"])
        self.list_title.pack(anchor="w", padx=16, pady=(14, 6))
        self.table = DataTable(right, [
            {"key": "time", "title": "เวลา", "weight": 2, "min_width": 60, "anchor": "w"},
            {"key": "name", "title": "รายการ", "weight": 3, "min_width": 110, "anchor": "w"},
            {"key": "weight", "title": "น้ำหนัก", "weight": 2, "min_width": 85, "anchor": "w"},
            {"key": "amount", "title": "บาท", "weight": 2, "min_width": 80, "anchor": "w"},
            {"key": "act", "title": "จัดการ", "weight": 2, "min_width": 75, "anchor": "w", "widget": self._cancel_button},
        ], row_height=38, font_size=13, empty_text="ยังไม่มีรายการชั่ง")
        self.table.pack(fill="both", expand=True, padx=10)
        self.total_label = ctk.CTkLabel(right, text="รวม 0.00 บาท", font=font(22, True), text_color=COLORS["primary"])
        self.total_label.pack(anchor="e", padx=18, pady=10)

    # ---------- ข้อมูล ----------
    def on_show(self, session_id: int | None = None, **params) -> None:
        if session_id is not None:
            self.session_id = session_id
        self.refresh()
        self.weight_entry.focus_set()

    def refresh(self) -> None:
        self._rate = weigh_service.get_price_per_kg()
        self.rate_label.configure(text=_format_rate_text(self._rate))
        self._load_tables()
        self._load_entries()
        self._update_calc()

    def _load_tables(self) -> None:
        rows = [t for t in table_service.list_tables_with_status() if t["status"] == config.SESSION_OPEN]
        self._tables = {f"โต๊ะ {t['table_no']}": t["session_id"] for t in rows}
        labels = list(self._tables) or ["(ไม่มีโต๊ะที่ใช้งาน)"]
        self.table_menu.configure(values=labels)
        current = next((l for l, sid in self._tables.items() if sid == self.session_id), None)
        if current is None:
            self.session_id = next(iter(self._tables.values()), None)
            current = next(iter(self._tables), labels[0])
        self.table_menu.set(current)

    def _on_table_picked(self, label: str) -> None:
        self.session_id = self._tables.get(label)
        self._load_entries()
        self._update_calc()

    def _load_entries(self) -> None:
        if self.session_id is None:
            self.table.set_rows([])
            self.total_label.configure(text="รวม 0.00 บาท")
            return
        rows = [{"id": e["id"], "time": fmt_time(e["created_at"]), "name": e["name_snapshot"],
                 "weight": weight_text(e["weight_grams"]), "amount": money(e["amount"]), "entry": e}
                for e in weigh_service.list_entries(self.session_id)]
        self.table.set_rows(rows)
        self.total_label.configure(text=f"รวม {baht(weigh_service.session_total(self.session_id))}")

    def _cancel_button(self, parent, row):
        return ActionButton(parent, "ยกเลิก", lambda: self.cancel_entry(row["entry"]), "ghost", height=26, width=64, size=12)

    # ---------- กรอกน้ำหนัก ----------
    def _grams(self) -> int | None:
        text = self.weight_var.get().strip().replace(",", "")
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        if value <= 0 or value != value:
            return None
        u = self.unit.get()
        if u == "ขีด":
            return weigh_service.kheed_to_grams(value)
        if u == "กิโลกรัม":
            return weigh_service.kg_to_grams(value)
        return int(round(value))

    def _add_kheed(self, kheed: float) -> None:
        text = self.weight_var.get().strip()
        try:
            current = float(text) if text else 0.0
        except ValueError:
            current = 0.0
        u = self.unit.get()
        if u == "กรัม":
            delta = kheed * 100
        elif u == "กิโลกรัม":
            delta = kheed / 10.0
        else:
            delta = kheed
        self.weight_var.set(f"{round(current + delta, 4):g}")

    def _update_calc(self) -> None:
        grams = self._grams()
        rate = self._rate
        rate_txt = _format_rate_text(rate)
        first_weigh = weigh_service.is_first_weigh(self.session_id) if self.session_id else True
        if grams is None:
            hint = " (การชั่งครั้งแรกต้องอย่างน้อย 1 กก.)" if first_weigh else ""
            self.calc_label.configure(
                text=f"อัตรา {rate_txt} — กรอกน้ำหนักเพื่อดูราคา{hint}",
                text_color=COLORS["text_muted"],
            )
            return
        amount = weigh_service.calc_amount(grams, rate)
        if first_weigh and grams < weigh_service.MIN_FIRST_WEIGH_GRAMS:
            self.calc_label.configure(
                text=f"น้ำหนัก {weight_text(grams)} ({grams:,} กรัม) = {baht(amount)}\n"
                     f"⚠️ {weigh_service.FIRST_WEIGH_ERROR_MSG}",
                text_color=COLORS["danger"],
            )
            return
        self.calc_label.configure(
            text=f"น้ำหนัก {weight_text(grams)} ({grams:,} กรัม)\n"
                 f"{rate_txt}  =  {baht(amount)}",
            text_color=COLORS["text"],
        )

    # ---------- บันทึก/ยกเลิก ----------
    def save(self) -> None:
        if self._saving:
            return
        if self.session_id is None:
            self.toast("ยังไม่ได้เลือกโต๊ะ", "error")
            return
        grams = self._grams()
        if grams is None:
            self.toast("กรุณากรอกน้ำหนักเป็นตัวเลขมากกว่า 0", "error")
            return
        # ตรวจสอบเงื่อนไขชั่งครั้งแรกใน UI ก่อนเรียก service
        if weigh_service.is_first_weigh(self.session_id) and grams < weigh_service.MIN_FIRST_WEIGH_GRAMS:
            self.toast(weigh_service.FIRST_WEIGH_ERROR_MSG, "error")
            self._update_calc()
            return
        self._saving = True
        try:
            ok, entry = self.call(weigh_service.add_entry, self.session_id, None, grams, self.user_id)
            if ok:
                self.toast(f"บันทึกแล้ว: {entry['name_snapshot']} {weight_text(grams)} = {baht(entry['amount'])}", "success")
                self.weight_var.set("")
                self._load_entries()
                self._update_calc()
                if self.app.alert_center:
                    self.app.alert_center.refresh_view()
                self.weight_entry.focus_set()
        finally:
            self._saving = False

    def cancel_entry(self, entry: dict) -> None:
        reason = ask_reason(self, f"เหตุผลที่ยกเลิก {entry['name_snapshot']} {weight_text(entry['weight_grams'])}",
                            title="ยกเลิกรายการชั่ง")
        if reason is None:
            return
        ok, _ = self.call(weigh_service.cancel_entry, entry["id"], reason, self.user_id, success="ยกเลิกรายการชั่งแล้ว")
        if ok:
            self._load_entries()
            self._update_calc()
            if self.app.alert_center:
                self.app.alert_center.refresh_view()
