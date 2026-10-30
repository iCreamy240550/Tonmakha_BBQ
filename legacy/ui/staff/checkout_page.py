"""ui/staff/checkout_page.py — หน้าเช็คเอาท์: เช็คบิล -> เลือกโปร/ช่องทางชำระ (เงินสด หรือ โอน/PromptPay) -> ชำระเงิน -> ใบเสร็จ PDF/TXT

เปิดจากหน้าโต๊ะด้วย `app.navigate('checkout', session_id=...)` ; ซ้ายคือรายการโต๊ะที่ใช้งาน/รอชำระ
- โต๊ะสถานะ "ใช้งาน": ปุ่ม "เริ่มเช็คบิล" (ถามยืนยัน เพราะย้อนกลับไม่ได้) -> รอชำระ
- โต๊ะ "รอชำระ":
  - ช่องทางการชำระเงินมีเพียง 2 รูปแบบ: 1) เงินสด  2) โอน/PromptPay (นำตัวเลือกบัตรออกแล้ว)
  - เงินสด: กรอกเงินสดที่รับ คำนวณเงินทอนสดด้วย Decimal และไม่อนุญาตให้ยืนยันหากเงินรับต่ำกว่ายอดชำระหรือผิดรูปแบบ
  - โอน/PromptPay: สร้าง QR Code มาตรฐาน EMVCo ระบุยอดสุทธิอัตโนมัติ แสดงชื่อและหมายเลขผู้รับ สถานะ "รอตรวจสอบการโอน" และไม่แสดง/ไม่คำนวณเงินทอน
- หลังชำระ: กล่องสรุปใบเสร็จ (ใช้ฟอนต์ Prompt และจัดรูปแบบตามตัวอย่างใน PDF) + ปุ่มส่งออกใบเสร็จเป็น .pdf และ .txt ที่โฟลเดอร์ exports/
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import customtkinter as ctk

import config
from services import checkout_service, promo_service, qr_service, settings_service, table_service
from ui.theme import COLORS, baht, fmt_datetime, font, money, weight_text
from ui.widgets import ActionButton, BaseDialog, BasePage, Card, EmptyState, PageHeader, StatusBadge, confirm

NO_PROMO = "ไม่ใช้โปรโมชั่น"
LABEL_CASH = "เงินสด"
LABEL_PROMPTPAY = "โอน/PromptPay"
METHOD_LABELS = [LABEL_CASH, LABEL_PROMPTPAY]
METHOD_BY_LABEL = {
    LABEL_CASH: "cash",
    LABEL_PROMPTPAY: "transfer",
    "สแกน PromptPay": "transfer",
    "โอน/พร้อมเพย์": "transfer",
}

build_receipt_text = checkout_service.build_receipt_text


class ReceiptDialog(BaseDialog):
    """หน้าต่างแสดงใบเสร็จหลังชำระเงิน จัดย่อหน้าและลำดับข้อมูลตามแบบใน PDF ด้วยฟอนต์ Prompt พร้อมปุ่มส่งออกเป็นไฟล์ .pdf และ .txt"""
    def __init__(self, parent, bill: dict):
        super().__init__(parent, "ชำระเงินเรียบร้อย — ใบเสร็จรับเงิน", width=560)
        self.bill = bill
        info = checkout_service._extract_receipt_lines_and_totals(bill)
        shop = info["shop"]

        ctk.CTkLabel(
            self.body, text=f"โต๊ะ {bill['table_no']} ชำระเงินเรียบร้อยแล้ว ({info['method_th']})",
            font=font(18, True), text_color=COLORS["success"]
        ).pack(anchor="w")

        # กรอบจำลองกระดาษใบเสร็จด้วยฟอนต์ Prompt จัดย่อหน้าตามภาพตัวอย่างใน PDF
        paper = ctk.CTkScrollableFrame(
            self.body, height=380, fg_color="#ffffff",
            border_width=1, border_color=COLORS["card_border"], corner_radius=8
        )
        paper.pack(fill="both", expand=True, pady=(6, 4))

        def _center_lbl(txt: str, sz: int = 13, is_bold: bool = False):
            ctk.CTkLabel(
                paper, text=txt, font=font(sz, is_bold),
                text_color=COLORS["text"], justify="center", anchor="center"
            ).pack(fill="x", padx=12, pady=0)

        def _divider():
            ctk.CTkFrame(paper, fg_color=COLORS["text"], height=1).pack(fill="x", padx=10, pady=5)

        def _meta_row(label_txt: str, val_txt: str):
            r = ctk.CTkFrame(paper, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(r, text=label_txt, width=95, font=font(13, True), text_color=COLORS["text"], anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=val_txt, font=font(13), text_color=COLORS["text"], anchor="w").pack(side="left")

        def _right_summary_row(label_txt: str, val_txt: str, is_bold: bool = False, highlight: bool = False):
            r = ctk.CTkFrame(paper, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=1)
            color = COLORS["primary"] if highlight else COLORS["text"]
            sz = 15 if highlight else 13
            ctk.CTkLabel(r, text=val_txt, width=105, font=font(sz, is_bold or highlight), text_color=color, anchor="e").pack(side="right")
            ctk.CTkLabel(r, text=label_txt, font=font(sz, is_bold or highlight), text_color=color, anchor="e").pack(side="right", padx=(0, 12))

        # 1-6. ส่วนหัวใบเสร็จ (ดึงจากการตั้งค่าร้านจริง)
        _center_lbl(shop["shop_name"], 16, True)
        if shop["shop_tax_id_enabled"] and shop["shop_tax_id"]:
            _center_lbl(f"เลขผู้เสียภาษี {shop['shop_tax_id']}", 13)
        _center_lbl("ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน", 13, True)
        if shop["address_line1"]:
            _center_lbl(shop["address_line1"], 12)
        if shop["address_line2"]:
            _center_lbl(shop["address_line2"], 12)
        if shop["phone_line"]:
            _center_lbl(shop["phone_line"], 12)

        _divider()

        # 7-9. พนักงานขาย, วันที่, เวลา
        _meta_row("พนักงานขาย", info["cashier"])
        _meta_row("วันที่", info["date_str"])
        _meta_row("เวลา", info["time_str"])

        _divider()

        # 10. ตารางรายการสินค้า (จำนวน | รายการ | จำนวนเงิน)
        head_row = ctk.CTkFrame(paper, fg_color="transparent")
        head_row.pack(fill="x", padx=12, pady=1)
        ctk.CTkLabel(head_row, text="จำนวน", width=55, font=font(13, True), text_color=COLORS["text"], anchor="center").pack(side="left")
        ctk.CTkLabel(head_row, text="รายการ", font=font(13, True), text_color=COLORS["text"], anchor="w").pack(side="left", padx=6)
        ctk.CTkLabel(head_row, text="จำนวนเงิน", width=95, font=font(13, True), text_color=COLORS["text"], anchor="e").pack(side="right")

        _divider()

        for ln in info["lines"]:
            it_row = ctk.CTkFrame(paper, fg_color="transparent")
            it_row.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(it_row, text=ln["qty_str"], width=55, font=font(13), text_color=COLORS["text"], anchor="center").pack(side="left")
            ctk.CTkLabel(it_row, text=ln["amount_str"], width=95, font=font(13), text_color=COLORS["text"], anchor="e").pack(side="right")
            ctk.CTkLabel(it_row, text=ln["name"], font=font(13), text_color=COLORS["text"], anchor="w", wraplength=280, justify="left").pack(side="left", padx=6, fill="x", expand=True)

        _divider()

        # 11-17. จำนวนรวม และ สรุปยอดเงิน
        qty_row = ctk.CTkFrame(paper, fg_color="transparent")
        qty_row.pack(fill="x", padx=12, pady=1)
        ctk.CTkLabel(qty_row, text=f"จำนวนรวม   {info['total_qty_count']}", font=font(13, True), text_color=COLORS["text"], anchor="w").pack(side="left")

        promo_suffix = f" ({info['promo_name']})" if info.get("promo_name") else ""
        _right_summary_row("รวมเป็นเงิน", money(info["subtotal"]))
        _right_summary_row(f"ส่วนลด{promo_suffix}", money(info["discount"]))
        _right_summary_row("จำนวนเงินหลังหักส่วนลด", money(info["after_discount"]))
        if info["service_charge"] > 0:
            pct = info.get("service_charge_percent")
            sc_lbl = f"ค่าบริการ ({pct:g}%)" if pct else "ค่าบริการ"
            _right_summary_row(sc_lbl, money(info["service_charge"]))
        _right_summary_row("ราคาไม่รวมภาษีมูลค่าเพิ่ม", money(info["pre_vat"]))
        _right_summary_row("ภาษีมูลค่าเพิ่ม 7%", money(info["vat"]))
        _right_summary_row("รวมทั้งสิ้น", baht(info["total"]), is_bold=True, highlight=True)

        _divider()

        # 18-19. ช่องทางการชำระเงิน (และ รับเงินมา / เงินทอน เฉพาะกรณีเงินสด)
        pay_r = ctk.CTkFrame(paper, fg_color="transparent")
        pay_r.pack(fill="x", padx=12, pady=1)
        ctk.CTkLabel(pay_r, text=f"ช่องทางการชำระ :   {info['method_th']}", font=font(13, True), text_color=COLORS["text"], anchor="w").pack(side="left")

        if info["method"] == "cash":
            rec_r = ctk.CTkFrame(paper, fg_color="transparent")
            rec_r.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(rec_r, text="รับเงินมา", font=font(13), text_color=COLORS["text"], anchor="w").pack(side="left")
            ctk.CTkLabel(rec_r, text=money(info["received"]), font=font(13), text_color=COLORS["text"], anchor="e").pack(side="right")

            chg_r = ctk.CTkFrame(paper, fg_color="transparent")
            chg_r.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(chg_r, text="เงินทอน", font=font(13, True), text_color=COLORS["text"], anchor="w").pack(side="left")
            ctk.CTkLabel(chg_r, text=money(info["change"]), font=font(13, True), text_color=COLORS["text"], anchor="e").pack(side="right")

        _divider()

        # 20. ท้ายใบเสร็จ
        _center_lbl(shop["shop_name"], 14, True)
        _center_lbl("ขอบคุณที่ใช้บริการ", 13)

        self.saved = ctk.CTkLabel(
            self.body, text="เลือกส่งออกใบเสร็จเป็นไฟล์ PDF หรือ TXT ด้านล่าง",
            font=font(13), text_color=COLORS["text_muted"], wraplength=480, justify="left"
        )
        self.saved.pack(anchor="w", pady=(4, 0))
        self.add_buttons("ปิด", None)
        ActionButton(self.button_row, "บันทึก PDF (.pdf)", self._save_pdf, "primary", width=140, size=13).pack(side="left", padx=(0, 6))
        ActionButton(self.button_row, "บันทึก TXT (.txt)", self._save_txt, "ghost", width=140, size=13).pack(side="left")

    def _save_pdf(self) -> None:
        try:
            path = checkout_service.export_receipt_pdf(self.bill)
            self.saved.configure(text=f"บันทึก PDF แล้ว: {path}", text_color=COLORS["success"])
        except ValueError as e:
            self.saved.configure(text=str(e), text_color=COLORS["danger"])

    def _save_txt(self) -> None:
        try:
            path = checkout_service.export_receipt_txt(self.bill)
            self.saved.configure(text=f"บันทึก TXT แล้ว: {path}", text_color=COLORS["success"])
        except ValueError as e:
            self.saved.configure(text=str(e), text_color=COLORS["danger"])


class Page(BasePage):
    title = "เช็คเอาท์"
    auto_refresh_ms = 5000

    def build(self) -> None:
        self.session_id: int | None = None
        self._promo_map: dict[str, int | None] = {NO_PROMO: None}
        self._list_sig = None
        self._bill_sig = None
        self.bill: dict | None = None
        self._qr_ctk_image = None
        self._qr_valid: bool = True
        self._submitting: bool = False

        PageHeader(self, "เช็คเอาท์", "เลือกโต๊ะทางซ้าย เพื่อดูบิล ตรวจสอบยอดเงิน และรับชำระเงิน").pack(fill="x", padx=24, pady=(18, 8))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        body.grid_columnconfigure(0, weight=2, uniform="c")
        body.grid_columnconfigure(1, weight=5, uniform="c")
        body.grid_rowconfigure(0, weight=1)

        self.list_area = ctk.CTkScrollableFrame(body, fg_color=COLORS["card"], border_width=1,
                                                border_color=COLORS["card_border"], corner_radius=12)
        self.list_area.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right = Card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.right = right
        self.title_label = ctk.CTkLabel(right, text="", font=font(22, True), text_color=COLORS["text"])
        self.title_label.pack(anchor="w", padx=18, pady=(12, 0))
        self.items_area = ctk.CTkScrollableFrame(right, fg_color="transparent", height=140)
        self.items_area.pack(fill="both", expand=True, padx=10, pady=2)
        self.totals_area = ctk.CTkFrame(right, fg_color="transparent")
        self.totals_area.pack(fill="x", padx=18)
        self.controls = ctk.CTkFrame(right, fg_color="transparent")
        self.controls.pack(fill="x", padx=18, pady=(4, 12))

        # ตัวควบคุมถาวร (สร้างครั้งเดียว กันค่าที่กรอกหายตอนรีเฟรช)
        row1 = ctk.CTkFrame(self.controls, fg_color="transparent")
        row1.pack(fill="x")
        ctk.CTkLabel(row1, text="โปรโมชั่น", font=font(15)).pack(side="left")
        self.promo_menu = ctk.CTkOptionMenu(row1, values=[NO_PROMO], width=240, height=36, font=font(14),
                                            dropdown_font=font(14), command=lambda v: self._load_bill(force=True))
        self.promo_menu.pack(side="left", padx=8)
        self.method = ctk.CTkSegmentedButton(
            row1, values=METHOD_LABELS, font=font(14), command=lambda v: self._on_method_changed(),
            selected_color=COLORS["primary"], selected_hover_color=COLORS["primary_hover"]
        )
        self.method.set(LABEL_CASH)
        self.method.pack(side="right")

        # แถวกรอกเงินสดรับ + คำนวณเงินทอน (แสดงเฉพาะกรณีเงินสด)
        self.cash_row = ctk.CTkFrame(self.controls, fg_color="transparent")
        self.cash_row.pack(fill="x", pady=6)
        self.cash_label = ctk.CTkLabel(self.cash_row, text="รับเงินสดมา (บาท)", font=font(15, True))
        self.cash_label.pack(side="left")
        self.cash_var = ctk.StringVar()
        self.cash_entry = ctk.CTkEntry(
            self.cash_row, textvariable=self.cash_var, width=140, height=38, font=font(16, True),
            justify="right", placeholder_text="0.00"
        )
        self.cash_entry.pack(side="left", padx=8)
        self.cash_var.trace_add("write", lambda *a: self._update_change())
        self.change_label = ctk.CTkLabel(self.cash_row, text="", font=font(15, True), text_color=COLORS["info"])
        self.change_label.pack(side="left", padx=8)

        # กรอบแสดง QR PromptPay (แสดงเมื่อเลือก โอน/PromptPay)
        self.qr_frame = ctk.CTkFrame(
            self.controls, fg_color=COLORS["row_alt"], corner_radius=10,
            border_width=1, border_color=COLORS["card_border"]
        )
        qr_inner = ctk.CTkFrame(self.qr_frame, fg_color="transparent")
        qr_inner.pack(fill="x", padx=12, pady=8)
        self.qr_img_label = ctk.CTkLabel(
            qr_inner, text="", width=160, height=160,
            fg_color="#ffffff", corner_radius=8
        )
        self.qr_img_label.pack(side="left", padx=(0, 12))
        qr_info_col = ctk.CTkFrame(qr_inner, fg_color="transparent")
        qr_info_col.pack(side="left", fill="both", expand=True)
        self.qr_status_badge = StatusBadge(qr_info_col, "สถานะ: รอตรวจสอบการโอน", COLORS["warning"], size=13)
        self.qr_status_badge.pack(anchor="w", pady=(0, 4))
        self.qr_amount_label = ctk.CTkLabel(qr_info_col, text="", font=font(18, True), text_color=COLORS["primary"], anchor="w")
        self.qr_amount_label.pack(fill="x")
        self.qr_account_label = ctk.CTkLabel(qr_info_col, text="", font=font(14, True), text_color=COLORS["text"], anchor="w", justify="left")
        self.qr_account_label.pack(fill="x", pady=(2, 2))
        self.qr_hint_label = ctk.CTkLabel(
            qr_info_col,
            text="การแสดง QR ไม่ได้ยืนยันว่าเงินเข้าแล้ว กรุณาตรวจสลิป/ยอดเงินเข้าแอปธนาคารของร้านก่อนกดยืนยันชำระเงิน",
            font=font(12), text_color=COLORS["text_muted"], wraplength=340, justify="left", anchor="w"
        )
        self.qr_hint_label.pack(fill="x")

        self.action_button = ActionButton(self.controls, "", self._on_action, "success", height=50, width=320, size=17)
        self.action_button.pack(anchor="e", pady=(4, 0))

    # ---------- โหลดข้อมูล ----------
    def on_show(self, session_id: int | None = None, **params) -> None:
        if session_id is not None:
            self.session_id = session_id
        self._list_sig = self._bill_sig = None
        self.refresh()

    def refresh(self) -> None:
        self._load_list()
        self._load_bill()

    def _load_list(self) -> None:
        rows = [t for t in table_service.list_tables_with_status()
                if t["status"] in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT)]
        if self.session_id is not None and not any(t["session_id"] == self.session_id for t in rows):
            self.session_id = None      # โต๊ะถูกปิด/ยกเลิกไปแล้ว
        sig = tuple((t["session_id"], t["status"], t["session_id"] == self.session_id) for t in rows)
        if sig == self._list_sig:
            return
        self._list_sig = sig
        for c in self.list_area.winfo_children():
            c.destroy()
        if not rows:
            EmptyState(self.list_area, "ไม่มีโต๊ะที่ต้องเช็คบิล").pack(pady=40)
            return
        for t in rows:
            selected = t["session_id"] == self.session_id
            btn = ctk.CTkButton(self.list_area, text=f"โต๊ะ {t['table_no']}   ·   {t['status_th']}", height=48, anchor="w",
                                font=font(16, True), corner_radius=8,
                                fg_color=COLORS["primary"] if selected else "#efe6d8",
                                text_color="#ffffff" if selected else COLORS["text"],
                                hover_color=COLORS["primary_hover"] if selected else COLORS["row_hover"],
                                command=lambda s=t["session_id"]: self._select(s))
            btn.pack(fill="x", padx=6, pady=3)

    def _select(self, session_id: int) -> None:
        self.session_id = session_id
        self.promo_menu.set(NO_PROMO)
        self.cash_var.set("")
        self._list_sig = self._bill_sig = None
        self.refresh()

    def _selected_promo_id(self) -> int | None:
        return self._promo_map.get(self.promo_menu.get())

    def _load_bill(self, force: bool = False) -> None:
        if self.session_id is None:
            self.bill = None
            self._clear_right()
            return
        try:
            bill = checkout_service.preview(self.session_id, promo_id=self._selected_promo_id())
        except ValueError as e:
            self.toast(str(e), "error")
            self.bill = None
            self._clear_right()
            return
        current_id = self._selected_promo_id()
        available = promo_service.list_available(bill["subtotal"])
        self._promo_map = {NO_PROMO: None}
        for p in available:
            self._promo_map[f"{p['name']} ({p['label']}) ลด {money(p['discount'])}"] = p["id"]
        self.promo_menu.configure(values=list(self._promo_map))
        label = next((l for l, pid in self._promo_map.items() if pid is not None and pid == current_id), None)
        self.promo_menu.set(label or NO_PROMO)
        self.bill = bill
        sig = (bill["status"], bill["total"], bill["discount"], len(bill["weigh_entries"]),
               tuple((o["id"], o["status"], len(o["items"])) for o in bill["orders"]))
        if sig == self._bill_sig and not force:
            return
        self._bill_sig = sig
        self._render_bill(bill)

    def _clear_right(self) -> None:
        self.title_label.configure(text="ยังไม่ได้เลือกโต๊ะ")
        for area in (self.items_area, self.totals_area):
            for c in area.winfo_children():
                c.destroy()
        self.controls.pack_forget()
        self._bill_sig = None

    def _render_bill(self, bill: dict) -> None:
        self.title_label.configure(text=f"โต๊ะ {bill['table_no']}  ·  {bill['status_th']}")
        for c in self.items_area.winfo_children():
            c.destroy()

        def line(text_left, text_right, bold=False, muted=False):
            row = ctk.CTkFrame(self.items_area, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=1)
            color = COLORS["text_muted"] if muted else COLORS["text"]
            ctk.CTkLabel(row, text=text_left, font=font(15, bold), text_color=color, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=text_right, font=font(15, bold), text_color=color).pack(side="right")

        if bill["weigh_entries"]:
            line("รายการชั่งกิโล", "", bold=True)
            for e in bill["weigh_entries"]:
                line(f"  {e['name_snapshot']}  {weight_text(e['weight_grams'])}", money(e["amount"]))
        order_lines = [(it, o) for o in bill["orders"] for it in o["items"]]
        if order_lines:
            line("รายการสั่งอาหาร", "", bold=True)
            for it, o in order_lines:
                line(f"  {it['name_snapshot']} × {it['quantity']}", money(it["unit_price"] * it["quantity"]))
        if not bill["weigh_entries"] and not order_lines:
            line("ยังไม่มีรายการ", "", muted=True)

        for c in self.totals_area.winfo_children():
            c.destroy()
        self._totals_rows(bill)
        self.controls.pack(fill="x", padx=18, pady=(4, 12))
        self._update_controls(bill)

    def _totals_rows(self, bill: dict) -> None:
        def row(label, value, big=False):
            r = ctk.CTkFrame(self.totals_area, fg_color="transparent")
            r.pack(fill="x")
            ctk.CTkLabel(r, text=label, font=font(20 if big else 14, big), text_color=COLORS["text"]).pack(side="left")
            ctk.CTkLabel(r, text=value, font=font(24 if big else 14, big),
                         text_color=COLORS["primary"] if big else COLORS["text"]).pack(side="right")
        ctk.CTkFrame(self.totals_area, fg_color=COLORS["card_border"], height=1).pack(fill="x", pady=3)
        row("รวมเป็นเงินก่อนคิดภาษีและส่วนลด", money(bill["subtotal"]))
        if bill["discount"]:
            row(f"ส่วนลด {bill.get('promo_name') or ''}".strip(), f"-{money(bill['discount'])}")
        if bill["service_charge"]:
            row(f"ค่าบริการ {bill['service_charge_percent']:g}%", money(bill["service_charge"]))
        if bill["vat"]:
            row(f"ภาษีมูลค่าเพิ่ม {bill['vat_percent']:g}%", money(bill["vat"]))
        row("ยอดที่ต้องชำระ", baht(bill["total"]), big=True)

    def _on_method_changed(self) -> None:
        if self.bill is not None:
            self._update_controls(self.bill)

    def _update_promptpay_box(self, bill: dict) -> None:
        self._qr_valid = False
        try:
            qr_data = qr_service.generate_promptpay_qr(bill["total"])
            pil_img = qr_data["image"].resize((150, 150))
            self._qr_ctk_image = ctk.CTkImage(light_image=pil_img, size=(150, 150))
            self.qr_img_label.configure(image=self._qr_ctk_image, text="")
            self.qr_status_badge.set(f"สถานะ: {qr_data['status_th']}", COLORS["warning"])
            self.qr_amount_label.configure(text=f"สแกนชำระ: {baht(qr_data['amount'])}")
            self.qr_account_label.configure(
                text=f"พร้อมเพย์: {qr_data['promptpay_id']}\nชื่อบัญชี: {qr_data['promptpay_name']}"
            )
            self._qr_valid = True
        except ValueError as e:
            self._qr_ctk_image = None
            self.qr_img_label.configure(image=None, text="สร้าง QR ไม่ได้")
            self.qr_status_badge.set("ข้อมูล PromptPay ไม่ถูกต้อง", COLORS["danger"])
            self.qr_amount_label.configure(text=str(e))
            self.qr_account_label.configure(text="กรุณาตรวจสอบหมายเลข PromptPay ที่หน้าตั้งค่า")

    def _update_controls(self, bill: dict) -> None:
        awaiting = bill["status"] == config.SESSION_AWAITING_PAYMENT
        method_key = METHOD_BY_LABEL.get(self.method.get(), "cash")
        is_cash = method_key == "cash"
        is_promptpay = method_key == "transfer"

        for w in (self.promo_menu, self.method):
            w.configure(state="normal" if awaiting else "disabled")
        self.cash_entry.configure(state="normal" if (awaiting and is_cash) else "disabled")

        if is_cash:
            self.cash_row.pack(fill="x", pady=6, before=self.action_button)
        else:
            self.cash_row.pack_forget()

        if awaiting and is_promptpay:
            self._update_promptpay_box(bill)
            self.qr_frame.pack(fill="x", pady=(2, 6), before=self.action_button)
        else:
            self.qr_frame.pack_forget()
            self._qr_valid = True

        if awaiting:
            btn_text = "ยืนยันรับเงินโอนแล้ว (ปิดโต๊ะ)" if is_promptpay else "ชำระเงินแล้ว (ปิดโต๊ะ)"
            self.action_button.configure(text=btn_text)
            self.action_button.set_variant("success")
        else:
            self.action_button.configure(text="เริ่มเช็คบิล")
            self.action_button.set_variant("info")
            self.action_button.configure(state="normal")
        self._update_change()

    def _parse_cash_status(self) -> tuple[bool, Decimal | None, Decimal | None, str]:
        """ตรวจสอบช่องเงินสดด้วย Decimal -> (valid, received_dec, change_dec, message)"""
        if self.bill is None:
            return False, None, None, ""
        total_dec = Decimal(str(self.bill["total"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        raw = (self.cash_var.get() or "").strip().replace(",", "")
        if not raw:
            return False, None, None, f"กรุณากรอกเงินสดที่รับ (อย่างน้อย {baht(total_dec)})"
        try:
            rec = Decimal(raw)
        except (InvalidOperation, ValueError):
            return False, None, None, "กรุณากรอกจำนวนเงินเป็นตัวเลขที่ถูกต้อง"
        if not rec.is_finite():
            return False, None, None, "จำนวนเงินไม่ถูกต้อง"
        if rec < Decimal("0"):
            return False, None, None, "ห้ามกรอกจำนวนเงินติดลบ"
        rec = rec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if rec < total_dec:
            diff = (total_dec - rec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return False, rec, None, f"เงินสดรับไม่พอ (ยังขาด {baht(diff)})"
        change = (rec - total_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return True, rec, change, f"เงินทอน {baht(change)}"

    def _update_change(self) -> None:
        if self.bill is None:
            self.change_label.configure(text="")
            return
        awaiting = self.bill["status"] == config.SESSION_AWAITING_PAYMENT
        method_key = METHOD_BY_LABEL.get(self.method.get(), "cash")
        is_cash = method_key == "cash"
        for w in (self.cash_label, self.cash_entry):
            w.configure(text_color=COLORS["text"] if is_cash else COLORS["text_muted"])

        if not awaiting:
            self.change_label.configure(text="")
            self.action_button.configure(state="normal")
            return

        if not is_cash:
            self.change_label.configure(text="")
            self.action_button.configure(state="normal" if self._qr_valid else "disabled")
            return

        ok_cash, _rec, _chg, msg = self._parse_cash_status()
        self.change_label.configure(text=msg, text_color=COLORS["info"] if ok_cash else COLORS["danger"])
        self.action_button.configure(state="normal" if ok_cash else "disabled")

    # ---------- การกระทำ ----------
    def _on_action(self) -> None:
        if self._submitting or self.bill is None or self.session_id is None:
            return
        if self.bill["status"] == config.SESSION_OPEN:
            self.start_checkout()
        else:
            self.pay()

    def start_checkout(self) -> None:
        t = self.bill["table_no"]
        if not confirm(self, f"เริ่มเช็คบิลโต๊ะ {t} ใช่หรือไม่?\nหลังเช็คบิลแล้วโต๊ะนี้จะสั่ง/ชั่งเพิ่มไม่ได้ (ย้อนกลับไม่ได้)",
                       title="เริ่มเช็คบิล", confirm_text="เริ่มเช็คบิล"):
            return
        ok, _ = self.call(checkout_service.start_checkout, self.session_id, self.user_id, success=f"เช็คบิลโต๊ะ {t} แล้ว")
        if ok:
            self._list_sig = self._bill_sig = None
            self.refresh()

    def pay(self) -> None:
        if self._submitting or self.bill is None or self.session_id is None:
            return
        method_label = self.method.get()
        method = METHOD_BY_LABEL.get(method_label, "cash")
        promo_id = self._selected_promo_id()

        if method == "cash":
            ok_cash, rec_dec, chg_dec, msg = self._parse_cash_status()
            if not ok_cash or rec_dec is None or chg_dec is None:
                self.toast(msg or "กรุณาตรวจสอบจำนวนเงินสดที่รับ", "error")
                return
            amount_received = float(rec_dec)
            summary_text = (
                f"สรุปการรับชำระเงิน โต๊ะ {self.bill['table_no']}\n"
                f"• ยอดที่ต้องชำระ: {baht(self.bill['total'])}\n"
                f"• ช่องทางการชำระ: เงินสด\n"
                f"• รับเงินมา: {baht(rec_dec)}\n"
                f"• เงินทอน: {baht(chg_dec)}\n\n"
                "ยืนยันการบันทึกบิลและปิดโต๊ะใช่หรือไม่?"
            )
        else:
            if not self._qr_valid:
                self.toast("ไม่สามารถยืนยันได้เนื่องจากข้อมูล PromptPay ไม่ถูกต้อง", "error")
                return
            amount_received = float(self.bill["total"])
            summary_text = (
                f"สรุปการรับชำระเงิน โต๊ะ {self.bill['table_no']}\n"
                f"• ยอดที่ต้องชำระ: {baht(self.bill['total'])}\n"
                f"• ช่องทางการชำระ: โอน/PromptPay\n"
                "(กรุณาตรวจสอบว่ามีเงินโอนเข้าบัญชีร้านจริงแล้วก่อนกดยืนยัน)\n\n"
                "ยืนยันว่าตรวจสอบยอดเงินเรียบร้อยและต้องการปิดโต๊ะใช่หรือไม่?"
            )

        force = False
        if self.bill["unserved_orders"]:
            if not confirm(self, f"ยังมีออเดอร์ที่ยังไม่เสิร์ฟ {self.bill['unserved_orders']} รายการ\nปิดบิลต่อเลย (ระบบจะตั้งเป็นเสิร์ฟแล้ว) ใช่หรือไม่?",
                           title="มีออเดอร์ค้าง", confirm_text="ปิดบิลต่อ", danger=True):
                return
            force = True
        if not confirm(self, summary_text, title="ยืนยันชำระเงิน", confirm_text="ยืนยันชำระเงิน"):
            return

        self._submitting = True
        try:
            ok, paid = self.call(
                checkout_service.pay,
                self.session_id,
                method,
                self.user_id,
                promo_id=promo_id,
                force=force,
                amount_received=amount_received,
            )
            if not ok:
                self._list_sig = self._bill_sig = None
                self.refresh()
                return
            self.session_id = None
            self.cash_var.set("")
            self.promo_menu.set(NO_PROMO)
            self._list_sig = self._bill_sig = None
            self.refresh()
            if self.app.alert_center:
                self.app.alert_center.refresh_view()
            ReceiptDialog(self, paid).show()
        finally:
            self._submitting = False
