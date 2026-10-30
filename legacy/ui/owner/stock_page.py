"""ui/owner/stock_page.py — สต๊อกวัตถุดิบ/สินค้า (เจ้าของ)

ซ้าย: รายการสต๊อก (เหลือ/จุดเตือน/สถานะ) · ขวา: ประวัติการเคลื่อนไหวของรายการที่เลือก
- เติมสต๊อก (restock): จาก 0 -> เมนูที่ผูกอยู่กลับมามีขายอัตโนมัติ
- ปรับ +/- (adjust): ต้องใส่เหตุผล (นับสต๊อกจริง/ของเสีย ฯลฯ) ; ถึง 0 -> เมนูที่ผูกหมดอัตโนมัติ
- แก้ชื่อ/หน่วย/จุดเตือน/ปิดใช้
- ลบรายการสต๊อก (delete_item): แยกออกจากปุ่มเติม/ปรับอย่างชัดเจน ตรวจสอบความสัมพันธ์ก่อนลบ แสดงกล่องยืนยันพร้อมผลกระทบ
- การจัดแนวตาราง: ทุกคอลัมน์ชิดซ้าย ยกเว้นคอลัมน์ "สถานะ" จัดกึ่งกลางตามข้อกำหนดใน PDF
"""
from __future__ import annotations

import customtkinter as ctk

from services import stock_service
from ui.owner._common import OwnerPage, fmt_qty, parse_number
from ui.theme import COLORS, fmt_datetime, font
from ui.widgets import ActionButton, BaseDialog, Card, DataTable, LabeledEntry, PageHeader, StatusBadge, confirm


class StockDialog(BaseDialog):
    """เพิ่ม/แก้รายการสต๊อก -> result = dict
    เพิ่ม: name, unit, quantity, min_quantity ; แก้: name, unit, min_quantity, active"""
    def __init__(self, parent, item: dict | None = None):
        super().__init__(parent, "แก้ไขรายการสต๊อก" if item else "เพิ่มรายการสต๊อก", width=460)
        self.item = item
        default_thresh = fmt_qty(stock_service.get_default_low_threshold())
        self.name = LabeledEntry(self.body, "ชื่อ", placeholder="เช่น หมูสามชั้น")
        self.name.pack(fill="x")
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        row.grid_columnconfigure((0, 1), weight=1, uniform="s")
        self.unit = LabeledEntry(row, "หน่วย", placeholder="กก. / ชิ้น / ขวด")
        self.unit.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.min_qty = LabeledEntry(row, f"จุดเตือนเมื่อเหลือไม่เกิน (เริ่มต้น {default_thresh})", placeholder=default_thresh)
        self.min_qty.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        if item is None:
            self.min_qty.set(default_thresh)
            self.qty = LabeledEntry(self.body, "จำนวนตั้งต้น", placeholder="0")
            self.qty.pack(fill="x", pady=(8, 0))
        else:
            self.active = ctk.CTkSwitch(self.body, text="เปิดใช้งานรายการนี้", font=font(15),
                                        progress_color=COLORS["success"])
            self.active.pack(anchor="w", pady=(12, 0))
            self.name.set(item["name"])
            self.unit.set(item["unit"])
            self.min_qty.set(fmt_qty(item["min_quantity"]))
            if item["active"]:
                self.active.select()
            else:
                self.active.deselect()
        self.error = ctk.CTkLabel(self.body, text="", font=font(13), text_color=COLORS["danger"], wraplength=410,
                                  justify="left")
        self.error.pack(anchor="w", pady=(6, 0))
        self.add_buttons("บันทึก", "ยกเลิก", on_confirm=self._submit)

    def _submit(self) -> None:
        try:
            name, unit = self.name.get(), self.unit.get()
            if not name or not unit:
                raise ValueError("กรุณากรอกชื่อและหน่วย")
            default_min = stock_service.get_default_low_threshold()
            data = {
                "name": name,
                "unit": unit,
                "min_quantity": parse_number(
                    self.min_qty.get(), "จุดเตือน", minimum=0, allow_empty=True, default=default_min
                ),
            }
            if self.item is None:
                data["quantity"] = parse_number(self.qty.get(), "จำนวนตั้งต้น", minimum=0, allow_empty=True)
            else:
                data["active"] = bool(self.active.get())
        except ValueError as e:
            self.error.configure(text=str(e))
            return
        self.close(data)


class QuantityDialog(BaseDialog):
    """กรอกจำนวน (เติม/ปรับ) -> result = (จำนวน float, เหตุผล str)
    mode='restock': จำนวน > 0, เหตุผลไม่บังคับ ; mode='adjust': จำนวน +/- (ไม่ใช่ 0), เหตุผลบังคับ"""
    def __init__(self, parent, item: dict, mode: str):
        self.mode = mode
        super().__init__(parent, "เติมสต๊อก" if mode == "restock" else "ปรับสต๊อก", width=440)
        ctk.CTkLabel(self.body, text=f"{item['name']}  (เหลือ {fmt_qty(item['quantity'])} {item['unit']})",
                     font=font(16, True), text_color=COLORS["text"], wraplength=390, justify="left").pack(anchor="w")
        hint = (f"จำนวนที่เติมเข้า ({item['unit']})" if mode == "restock"
                else f"จำนวนที่เปลี่ยน ({item['unit']}) — ใส่ + เพิ่ม / - ลด เช่น -2.5 (ถ้าจะเติมของเข้าร้านให้ใช้ปุ่ม \"เติม\")")
        self.qty = LabeledEntry(self.body, hint, placeholder="0")
        self.qty.pack(fill="x", pady=(10, 0))
        self.reason = LabeledEntry(self.body, "เหตุผล" + (" (ไม่บังคับ)" if mode == "restock" else " (บังคับ)"),
                                   placeholder="เช่น ซื้อเข้าร้าน / นับสต๊อกจริง / ของเสีย")
        self.reason.pack(fill="x", pady=(8, 0))
        self.error = ctk.CTkLabel(self.body, text="", font=font(13), text_color=COLORS["danger"], wraplength=390,
                                  justify="left")
        self.error.pack(anchor="w", pady=(6, 0))
        self.add_buttons("เติมสต๊อก" if mode == "restock" else "ปรับสต๊อก", "ยกเลิก", on_confirm=self._submit)

    def _submit(self) -> None:
        try:
            qty = parse_number(self.qty.get(), "จำนวน")
            reason = self.reason.get()
            if self.mode == "restock":
                if qty <= 0:
                    raise ValueError("จำนวนที่เติมต้องมากกว่า 0")
            else:
                if qty == 0:
                    raise ValueError("จำนวนที่ปรับต้องไม่เป็น 0")
                if not reason:
                    raise ValueError("กรุณากรอกเหตุผลที่ปรับสต๊อก")
        except ValueError as e:
            self.error.configure(text=str(e))
            return
        self.close((qty, reason))


class Page(OwnerPage):
    title = "สต๊อก"

    def build(self) -> None:
        self.include_inactive = False
        self._deleting = False
        header = PageHeader(self, "สต๊อก", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "+ เพิ่มรายการ", self.add_item, "primary", height=38, width=130).pack(side="right")
        self.delete_btn = ActionButton(
            header.right, "ลบรายการสต๊อกที่เลือก", self.delete_selected, "danger", height=38, width=175
        )
        self.delete_btn.pack(side="right", padx=(8, 8))
        self.show_inactive = ctk.CTkCheckBox(header.right, text="แสดงรายการที่ปิดใช้", font=font(14),
                                             command=self._toggle_inactive)
        self.show_inactive.pack(side="right", padx=10)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        body.grid_columnconfigure(0, weight=6, uniform="s")
        body.grid_columnconfigure(1, weight=4, uniform="s")
        body.grid_rowconfigure(0, weight=1)

        self.table = DataTable(body, columns=[
            {"key": "name", "title": "รายการ", "weight": 3, "min_width": 120, "anchor": "w"},
            {"key": "quantity", "title": "คงเหลือ", "weight": 2, "min_width": 85, "anchor": "w",
             "format": lambda v, r: f"{fmt_qty(v)} {r['unit']}"},
            {"key": "effective_min_quantity", "title": "จุดเตือน", "weight": 2, "min_width": 75, "anchor": "w",
             "format": lambda v, r: fmt_qty(v)},
            {"key": "status", "title": "สถานะ", "weight": 2, "min_width": 85, "anchor": "center",
             "widget": self._status_badge, "sticky": ""},
            {"key": "actions", "title": "จัดการสต๊อก", "weight": 6, "min_width": 270, "anchor": "w",
             "widget": self._row_actions, "sticky": "w"},
        ], on_select=lambda r: self._on_row_selected(), empty_text="ยังไม่มีรายการสต๊อก")
        self.table.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right = Card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.move_title = ctk.CTkLabel(right, text="ประวัติการเคลื่อนไหว", font=font(18, True), text_color=COLORS["text"])
        self.move_title.pack(anchor="w", padx=14, pady=(12, 4))
        self.moves = DataTable(right, columns=[
            {"key": "created_at", "title": "เวลา", "weight": 3, "min_width": 110, "anchor": "w", "format": lambda v, r: fmt_datetime(v)},
            {"key": "change_qty", "title": "เปลี่ยน", "weight": 2, "min_width": 70, "anchor": "w",
             "format": lambda v, r: ("+" if v > 0 else "") + fmt_qty(v)},
            {"key": "reason", "title": "เหตุผล", "weight": 4, "min_width": 100, "anchor": "w", "wrap": 150},
            {"key": "user_name", "title": "โดย", "weight": 2, "min_width": 70, "anchor": "w", "format": lambda v, r: v or "ระบบ"},
        ], empty_text="เลือกรายการทางซ้ายเพื่อดูประวัติ", font_size=13, row_height=36)
        self.moves.pack(fill="both", expand=True, padx=6, pady=(0, 8))

    # ---------- โหลดข้อมูล ----------
    def on_open(self, **params) -> None:
        self.refresh()

    def _toggle_inactive(self) -> None:
        self.include_inactive = bool(self.show_inactive.get())
        self.refresh()

    def refresh(self) -> None:
        items = stock_service.list_items(include_inactive=self.include_inactive)
        self.table.set_rows(items)
        low = sum(1 for i in items if i["active"] and i["is_low"])
        self.header.set_subtitle(f"{len(items)} รายการ" + (f" · ใกล้หมด/หมด {low} รายการ" if low else ""))
        self._on_row_selected()

    def _on_row_selected(self) -> None:
        sel = self.table.selected
        self.delete_btn.configure(state="normal" if sel is not None else "disabled")
        self._load_movements()

    def _load_movements(self) -> None:
        sel = self.table.selected
        if sel is None:
            self.move_title.configure(text="ประวัติการเคลื่อนไหว")
            self.moves.set_rows([])
            return
        self.move_title.configure(text=f"ประวัติ: {sel['name']}")
        ok, rows = self.call(stock_service.get_movements, sel["id"], 100)
        self.moves.set_rows(rows if ok else [])

    # ---------- แถวในตาราง ----------
    def _status_badge(self, parent, row: dict):
        if not row["active"]:
            return StatusBadge(parent, "ปิดใช้", COLORS["neutral"])
        if row["quantity"] <= 0:
            return StatusBadge(parent, "สินค้าหมด", COLORS["danger"])
        if row["is_low"]:
            return StatusBadge(parent, "ใกล้หมด", COLORS["warning"])
        return StatusBadge(parent, "พอ", COLORS["success"])

    def _row_actions(self, parent, row: dict):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        ActionButton(box, "เติม", lambda r=row: self.restock(r), "success", height=30, width=52, size=13).pack(side="left", padx=2)
        ActionButton(box, "ปรับ +/-", lambda r=row: self.adjust(r), "ghost", height=30, width=72, size=13).pack(side="left", padx=2)
        ActionButton(box, "แก้ไข", lambda r=row: self.edit_item(r), "info", height=30, width=58, size=13).pack(side="left", padx=2)
        ActionButton(box, "ลบ", lambda r=row: self.delete_item(r), "danger", height=30, width=48, size=13).pack(side="left", padx=(6, 2))
        return box

    # ---------- การกระทำ ----------
    def add_item(self) -> None:
        data = StockDialog(self).show()
        if not data:
            return
        ok, _ = self.call(stock_service.add_item, data["name"], data["unit"], data["quantity"], data["min_quantity"],
                          user_id=self.user_id, success="เพิ่มรายการสต๊อกแล้ว")
        if ok:
            self.refresh()
            if self.app.alert_center:
                self.app.alert_center.refresh_view()

    def edit_item(self, row: dict) -> None:
        data = StockDialog(self, item=row).show()
        if not data:
            return
        ok, _ = self.call(stock_service.update_item, row["id"], name=data["name"], unit=data["unit"],
                          min_quantity=data["min_quantity"], active=data["active"], user_id=self.user_id,
                          success="บันทึกแล้ว")
        if ok:
            self.refresh()
            if self.app.alert_center:
                self.app.alert_center.refresh_view()

    def restock(self, row: dict) -> None:
        result = QuantityDialog(self, row, "restock").show()
        if not result:
            return
        qty, reason = result
        ok, new_qty = self.call(stock_service.restock, row["id"], qty, user_id=self.user_id,
                                reason=reason or "เติมสต๊อก")
        if ok:
            self.toast(f"เติมแล้ว คงเหลือ {fmt_qty(new_qty)} {row['unit']}", "success")
            self.refresh()
            if self.app.alert_center:
                self.app.alert_center.refresh_view()

    def adjust(self, row: dict) -> None:
        result = QuantityDialog(self, row, "adjust").show()
        if not result:
            return
        qty, reason = result
        ok, new_qty = self.call(stock_service.adjust, row["id"], qty, reason, user_id=self.user_id)
        if ok:
            self.toast(f"ปรับแล้ว คงเหลือ {fmt_qty(new_qty)} {row['unit']}", "success")
            self.refresh()
            if self.app.alert_center:
                self.app.alert_center.refresh_view()

    def delete_selected(self) -> None:
        sel = self.table.selected
        if sel is None:
            self.toast("กรุณาเลือกรายการสต๊อกที่ต้องการลบก่อน", "warning")
            return
        self.delete_item(sel)

    def delete_item(self, row: dict) -> None:
        if self._deleting:
            return
        ok_imp, impact = self.call(stock_service.get_delete_impact, row["id"])
        if not ok_imp or not impact:
            return
        title = "ยืนยันลบรายการสต๊อก"
        btn_label = "ลบถาวร" if impact["can_hard_delete"] else "ปิดใช้งานแทนการลบ"
        msg = (
            f"ต้องการลบรายการสต๊อก \"{row['name']}\" (คงเหลือ {fmt_qty(row['quantity'])} {row['unit']}) ใช่หรือไม่?\n\n"
            f"ผลกระทบ:\n{impact['impact_text']}"
        )
        if not confirm(self, msg, title=title, confirm_text=btn_label, danger=True):
            return
        self._deleting = True
        try:
            ok, res = self.call(stock_service.delete_item, row["id"], user_id=self.user_id)
            if ok and res:
                self.toast(res["message"], "success")
                self.refresh()
                if self.app.alert_center:
                    self.app.alert_center.refresh_view()
        finally:
            self._deleting = False
