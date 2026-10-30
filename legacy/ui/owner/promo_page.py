"""ui/owner/promo_page.py — โปรโมชั่น/ส่วนลด (เจ้าของ)

ตารางโปรทั้งหมด (ใหม่สุดก่อน) + เพิ่ม/แก้ไข/เปิด-ปิดใช้งาน ; ไม่มีลบ (บิลเก่าอ้างอิงอยู่)
- ชนิด: ลดเป็น % (0-100) หรือ ลดเป็นบาท ; ยอดขั้นต่ำ ; ช่วงวันที่ (ว่าง = ไม่จำกัด) รูปแบบ ปี-เดือน-วัน
- การจัดแนวตาราง: ทุกคอลัมน์ชิดซ้าย ยกเว้นคอลัมน์ "สถานะ" จัดกึ่งกลางตามข้อกำหนดใน PDF
"""
from __future__ import annotations

import customtkinter as ctk

from services import promo_service
from ui.owner._common import OwnerPage, parse_date, parse_number
from ui.theme import COLORS, font, money
from ui.widgets import ActionButton, BaseDialog, DataTable, LabeledEntry, PageHeader, StatusBadge, confirm

TYPE_LABELS = {"percent": "ลดเป็น %", "fixed": "ลดเป็นบาท"}


def _period_text(p: dict) -> str:
    start, end = (p["start_at"] or "")[:10], (p["end_at"] or "")[:10]
    if not start and not end:
        return "ไม่จำกัด"
    return f"{start or '...'} ถึง {end or '...'}"


class PromoDialog(BaseDialog):
    """เพิ่ม/แก้โปร -> result = dict(name, promo_type, value, min_amount, start_at, end_at[, active])"""
    def __init__(self, parent, promo: dict | None = None):
        super().__init__(parent, "แก้ไขโปรโมชั่น" if promo else "เพิ่มโปรโมชั่น", width=460)
        self.promo = promo
        self.promo_type = promo["promo_type"] if promo else "percent"
        self.name = LabeledEntry(self.body, "ชื่อโปรโมชั่น", placeholder="เช่น ลด 10% วันพุธ")
        self.name.pack(fill="x")
        ctk.CTkLabel(self.body, text="ชนิดส่วนลด", font=font(14), text_color=COLORS["text_muted"]).pack(anchor="w", pady=(8, 0))
        self.type_seg = ctk.CTkSegmentedButton(self.body, values=list(TYPE_LABELS.values()), font=font(14),
                                               command=self._on_type, selected_color=COLORS["primary"],
                                               selected_hover_color=COLORS["primary_hover"])
        self.type_seg.set(TYPE_LABELS[self.promo_type])
        self.type_seg.pack(fill="x", pady=(2, 0))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        row.grid_columnconfigure((0, 1), weight=1, uniform="p")
        self.value = LabeledEntry(row, self._value_label(), placeholder="0")
        self.value.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.value_caption = next((w for w in self.value.winfo_children() if isinstance(w, ctk.CTkLabel)), None)
        self.min_amount = LabeledEntry(row, "ยอดขั้นต่ำ (บาท)", placeholder="0")
        self.min_amount.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        dates = ctk.CTkFrame(self.body, fg_color="transparent")
        dates.pack(fill="x", pady=(8, 0))
        dates.grid_columnconfigure((0, 1), weight=1, uniform="d")
        self.start = LabeledEntry(dates, "เริ่มวันที่ (ว่าง = ทันที)", placeholder="2026-10-01")
        self.start.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.end = LabeledEntry(dates, "ถึงวันที่ (ว่าง = ไม่จำกัด)", placeholder="2026-10-31")
        self.end.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.active = ctk.CTkSwitch(self.body, text="เปิดใช้งานโปรนี้", font=font(15), progress_color=COLORS["success"])
        self.active.pack(anchor="w", pady=(12, 0))
        self.active.select()
        self.error = ctk.CTkLabel(self.body, text="", font=font(13), text_color=COLORS["danger"], wraplength=400,
                                  justify="left")
        self.error.pack(anchor="w", pady=(6, 0))
        if promo:
            self.name.set(promo["name"])
            self.value.set(f"{promo['value']:g}")
            self.min_amount.set(f"{promo['min_amount']:g}")
            self.start.set((promo["start_at"] or "")[:10])
            self.end.set((promo["end_at"] or "")[:10])
            if not promo["active"]:
                self.active.deselect()
        self.add_buttons("บันทึก", "ยกเลิก", on_confirm=self._submit)

    def _value_label(self) -> str:
        return "ลดกี่ % (1-100)" if self.promo_type == "percent" else "ลดกี่บาท"

    def _on_type(self, label: str) -> None:
        self.promo_type = next(k for k, v in TYPE_LABELS.items() if v == label)
        if self.value_caption is not None:
            self.value_caption.configure(text=self._value_label())

    def _submit(self) -> None:
        try:
            name = self.name.get()
            if not name:
                raise ValueError("กรุณาใส่ชื่อโปรโมชั่น")
            value = parse_number(self.value.get(), "ค่าส่วนลด", minimum=0)
            if value <= 0:
                raise ValueError("ค่าส่วนลดต้องมากกว่า 0")
            if self.promo_type == "percent" and value > 100:
                raise ValueError("ส่วนลดเปอร์เซ็นต์ต้องไม่เกิน 100")
            min_amount = parse_number(self.min_amount.get(), "ยอดขั้นต่ำ", minimum=0, allow_empty=True)
            start = parse_date(self.start.get(), "วันเริ่ม")
            end = parse_date(self.end.get(), "วันสิ้นสุด")
            if start and end and start > end:
                raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")
        except ValueError as e:
            self.error.configure(text=str(e))
            return
        self.close({"name": name, "promo_type": self.promo_type, "value": value, "min_amount": min_amount,
                    "start_at": start, "end_at": end, "active": bool(self.active.get())})


class Page(OwnerPage):
    title = "โปรโมชั่น"

    def build(self) -> None:
        header = PageHeader(self, "โปรโมชั่น", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "+ เพิ่มโปรโมชั่น", self.add_promo, "primary", height=38, width=150).pack(side="right")
        self.table = DataTable(self, columns=[
            {"key": "name", "title": "ชื่อโปร", "weight": 4, "min_width": 160, "anchor": "w"},
            {"key": "label", "title": "ส่วนลด", "weight": 2, "min_width": 85, "anchor": "w"},
            {"key": "min_amount", "title": "ยอดขั้นต่ำ", "weight": 2, "min_width": 95, "anchor": "w",
             "format": lambda v, r: money(v) if v else "-"},
            {"key": "period", "title": "ช่วงเวลา", "weight": 3, "min_width": 150, "anchor": "w", "format": lambda v, r: _period_text(r)},
            {"key": "status", "title": "สถานะ", "weight": 2, "min_width": 100, "anchor": "center",
             "widget": self._status_badge, "sticky": ""},
            {"key": "actions", "title": "จัดการ", "weight": 3, "min_width": 180, "anchor": "w",
             "widget": self._row_actions, "sticky": "w"},
        ], empty_text="ยังไม่มีโปรโมชั่น")
        self.table.pack(fill="both", expand=True, padx=24, pady=(0, 16))

    def on_open(self, **params) -> None:
        self.refresh()

    def refresh(self) -> None:
        promos = promo_service.list_promos(include_inactive=True)
        self.table.set_rows(promos)
        usable = sum(1 for p in promos if p["active"] and promo_service.is_in_period(p))
        self.header.set_subtitle(f"{len(promos)} โปร · ใช้ได้ตอนนี้ {usable} โปร")

    def _status_badge(self, parent, row: dict):
        if not row["active"]:
            return StatusBadge(parent, "ปิดใช้งาน", COLORS["neutral"])
        if not promo_service.is_in_period(row):
            return StatusBadge(parent, "นอกช่วงเวลา", COLORS["warning"])
        return StatusBadge(parent, "ใช้ได้", COLORS["success"])

    def _row_actions(self, parent, row: dict):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        ActionButton(box, "แก้ไข", lambda r=row: self.edit_promo(r), "info", height=30, width=64, size=13).pack(side="left", padx=2)
        ActionButton(box, "เปิดใช้" if not row["active"] else "ปิดใช้", lambda r=row: self.toggle_active(r),
                     "success" if not row["active"] else "ghost", height=30, width=72, size=13).pack(side="left", padx=2)
        return box

    def add_promo(self) -> None:
        d = PromoDialog(self).show()
        if not d:
            return
        ok, p = self.call(promo_service.add_promo, d["name"], d["promo_type"], d["value"], d["min_amount"],
                          d["start_at"] or None, d["end_at"] or None, user_id=self.user_id, success="เพิ่มโปรแล้ว")
        if ok and not d["active"]:
            self.call(promo_service.update_promo, p["id"], active=False, user_id=self.user_id)
        if ok:
            self.refresh()

    def edit_promo(self, row: dict) -> None:
        d = PromoDialog(self, promo=row).show()
        if not d:
            return
        ok, _ = self.call(promo_service.update_promo, row["id"], name=d["name"], promo_type=d["promo_type"],
                          value=d["value"], min_amount=d["min_amount"], start_at=d["start_at"], end_at=d["end_at"],
                          active=d["active"], user_id=self.user_id,
                          success="บันทึกโปรแล้ว (บิลที่ปิดไปแล้วไม่เปลี่ยน)")
        if ok:
            self.refresh()

    def toggle_active(self, row: dict) -> None:
        if row["active"] and not confirm(self, f"ปิดใช้งานโปร \"{row['name']}\" ?\nพนักงานจะเลือกโปรนี้ตอนเช็คเอาท์ไม่ได้",
                                         title="ปิดโปรโมชั่น", confirm_text="ปิดใช้งาน"):
            return
        ok, _ = self.call(promo_service.update_promo, row["id"], active=not row["active"], user_id=self.user_id,
                          success="ปิดใช้งานโปรแล้ว" if row["active"] else "เปิดใช้งานโปรแล้ว")
        if ok:
            self.refresh()
