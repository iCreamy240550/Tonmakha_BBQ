"""ui/owner/dashboard_page.py — แดชบอร์ดและรายงานยอดขายของเจ้าของร้าน (รวมหน้ารายงานเข้ากับแดชบอร์ด)

ส่วนที่ 1: ภาพรวมสถานะร้านวันนี้ (ยอดขายวันนี้, โต๊ะที่ใช้งาน/รอยืนยัน/รอชำระ, แจ้งเตือนด่วน, สต๊อกใกล้หมด, ช่องทางชำระวันนี้)
ส่วนที่ 2: รายงานตามช่วงวันที่ พร้อมตัวเลือกวันที่แบบปฏิทิน (เลือกปี พ.ศ. เดือน และวันที่ได้โดยไม่ต้องพิมพ์เอง)
  - การ์ดสรุปยอดขายตามช่วงวันที่เลือก
  - ตารางรายงานแยกแท็บ: รายวัน · รายชั่วโมง · เมนูขายดี · รายการยกเลิก · บิล
  - ปุ่มส่งออก CSV และเปิดโฟลเดอร์ exports
ข้อมูลทั้งหมดมาจาก `report_service` และ `checkout_service.list_bills`
"""
from __future__ import annotations

from datetime import date, timedelta

import customtkinter as ctk

import config
from services import checkout_service, report_service
from ui.owner._common import (
    DatePickerField,
    OwnerPage,
    bar,
    ce_to_be_year,
    fmt_qty,
    format_thai_date,
    open_folder,
    parse_date,
)
from ui.theme import COLORS, baht, fmt_datetime, font, money
from ui.widgets import ActionButton, Card, DataTable, EmptyState, PageHeader, StatTile

TABS = ["รายวัน", "รายชั่วโมง", "เมนูขายดี", "รายการยกเลิก", "บิล"]
CANCELLED_BY_TH = {"staff": "พนักงาน", "customer": "ลูกค้า"}
KIND_TH = {"order_item": "รายการสั่ง", "weigh_entry": "รายการชั่ง", "session": "ยกเลิกทั้งโต๊ะ"}
BILL_LIMIT = 300


def _quick_range(kind: str) -> tuple[str, str]:
    today = date.today()
    if kind == "today":
        a = b = today
    elif kind == "yesterday":
        a = b = today - timedelta(days=1)
    elif kind == "7days":
        a, b = today - timedelta(days=6), today
    elif kind == "month":
        a, b = today.replace(day=1), today
    else:   # lastmonth
        b = today.replace(day=1) - timedelta(days=1)
        a = b.replace(day=1)
    return a.isoformat(), b.isoformat()


def _fmt_iso_to_be(iso_date: str | None) -> str:
    if not iso_date or len(str(iso_date)) < 10:
        return str(iso_date or "-")
    s = str(iso_date)[:10]
    try:
        y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        return f"{d:02d}/{m:02d}/{ce_to_be_year(y)}"
    except ValueError:
        return s


class Page(OwnerPage):
    title = "แดชบอร์ด"
    auto_refresh_ms = 15000

    def build(self) -> None:
        self._low_sig = None
        self._pay_sig = None
        self._report_sig = None
        self.range: tuple[str, str] = _quick_range("today")

        header = PageHeader(self, "แดชบอร์ดและรายงาน", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "ส่งออก CSV", self.export_csv, "success", height=38, width=120).pack(side="right")
        ActionButton(header.right, "เปิดโฟลเดอร์ exports", lambda: self._open_exports(), "ghost", height=38, width=170).pack(side="right", padx=8)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.scroll = scroll

        # ================================================================
        # ส่วนที่ 1: ภาพรวมสถานะร้านวันนี้ (Real-time Overview)
        # ================================================================
        ctk.CTkLabel(scroll, text="ภาพรวมสถานะร้านวันนี้", font=font(18, True), text_color=COLORS["text"]).pack(
            anchor="w", padx=8, pady=(2, 4)
        )
        tiles = ctk.CTkFrame(scroll, fg_color="transparent")
        tiles.pack(fill="x")
        for c in range(4):
            tiles.grid_columnconfigure(c, weight=1, uniform="tile")
        self.tile_sales = StatTile(tiles, "ยอดขายวันนี้", "-", COLORS["primary"])
        self.tile_bills = StatTile(tiles, "จำนวนบิลวันนี้", "-")
        self.tile_avg = StatTile(tiles, "เฉลี่ยต่อบิลวันนี้", "-")
        self.tile_discount = StatTile(tiles, "ส่วนลดวันนี้", "-", COLORS["warning"])
        self.tile_tables = StatTile(tiles, "โต๊ะที่ใช้งาน", "-", COLORS["success"])
        self.tile_pending = StatTile(tiles, "รอยืนยัน", "-", COLORS["warning"])
        self.tile_pay = StatTile(tiles, "รอชำระเงิน", "-", COLORS["info"])
        self.tile_alerts = StatTile(tiles, "แจ้งเตือนด่วน", "-", COLORS["danger"])
        for i, t in enumerate([self.tile_sales, self.tile_bills, self.tile_avg, self.tile_discount,
                               self.tile_tables, self.tile_pending, self.tile_pay, self.tile_alerts]):
            t.grid(row=i // 4, column=i % 4, padx=6, pady=5, sticky="nsew")

        lower = ctk.CTkFrame(scroll, fg_color="transparent")
        lower.pack(fill="x", pady=(4, 10))
        lower.grid_columnconfigure(0, weight=1, uniform="low")
        lower.grid_columnconfigure(1, weight=1, uniform="low")

        self.low_card = Card(lower)
        self.low_card.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        row_low = ctk.CTkFrame(self.low_card, fg_color="transparent")
        row_low.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(row_low, text="สต๊อกใกล้หมด", font=font(18, True), text_color=COLORS["text"]).pack(side="left")
        ActionButton(row_low, "ไปหน้าสต๊อก", lambda: self.app.navigate("stock"), "ghost",
                     height=30, width=110, size=13).pack(side="right")
        self.low_area = ctk.CTkFrame(self.low_card, fg_color="transparent")
        self.low_area.pack(fill="both", expand=True, padx=16, pady=(6, 14))

        self.pay_card = Card(lower)
        self.pay_card.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(self.pay_card, text="ยอดขายวันนี้แยกตามช่องทางชำระ", font=font(18, True),
                     text_color=COLORS["text"]).pack(anchor="w", padx=16, pady=(12, 0))
        self.pay_area = ctk.CTkFrame(self.pay_card, fg_color="transparent")
        self.pay_area.pack(fill="both", expand=True, padx=16, pady=(6, 6))
        self.cancel_label = ctk.CTkLabel(self.pay_card, text="", font=font(14), text_color=COLORS["text_muted"],
                                         anchor="w", justify="left")
        self.cancel_label.pack(fill="x", padx=16, pady=(0, 14))

        # ================================================================
        # ส่วนที่ 2: รายงานยอดขายและธุรกรรมตามช่วงวันที่ (เลือกจากปฏิทิน พ.ศ.)
        # ================================================================
        rep_head = ctk.CTkFrame(scroll, fg_color="transparent")
        rep_head.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(rep_head, text="รายงานยอดขายและธุรกรรมตามช่วงวันที่", font=font(20, True),
                     text_color=COLORS["text"]).pack(side="left")
        self.report_range_label = ctk.CTkLabel(rep_head, text="", font=font(14), text_color=COLORS["text_muted"])
        self.report_range_label.pack(side="left", padx=12)

        filt = Card(scroll)
        filt.pack(fill="x", padx=6, pady=(0, 8))
        row_filt = ctk.CTkFrame(filt, fg_color="transparent")
        row_filt.pack(fill="x", padx=14, pady=12)

        self.date_from = DatePickerField(
            row_filt, "จากวันที่ (พ.ศ.)", initial_iso=self.range[0],
            width=220, on_change=lambda _v: self._on_calendar_date_picked()
        )
        self.date_from.pack(side="left")

        self.date_to = DatePickerField(
            row_filt, "ถึงวันที่ (พ.ศ.)", initial_iso=self.range[1],
            width=220, on_change=lambda _v: self._on_calendar_date_picked()
        )
        self.date_to.pack(side="left", padx=10)

        ActionButton(row_filt, "แสดงรายงาน", self.show_report, "primary", height=42, width=120).pack(
            side="left", padx=(4, 12), pady=(18, 0)
        )
        quick = ctk.CTkFrame(row_filt, fg_color="transparent")
        quick.pack(side="left", pady=(18, 0))
        for label, kind in (("วันนี้", "today"), ("เมื่อวาน", "yesterday"), ("7 วัน", "7days"),
                            ("เดือนนี้", "month"), ("เดือนที่แล้ว", "lastmonth")):
            ActionButton(quick, label, lambda k=kind: self.quick(k), "ghost", height=36, width=82, size=14).pack(
                side="left", padx=2
            )

        # การ์ดสรุปของช่วงวันที่ที่เลือกในรายงาน
        rtiles = ctk.CTkFrame(scroll, fg_color="transparent")
        rtiles.pack(fill="x")
        for c in range(4):
            rtiles.grid_columnconfigure(c, weight=1, uniform="rt")
        self.rtile_total = StatTile(rtiles, "ยอดสุทธิ (ช่วงที่เลือก)", "-", COLORS["primary"])
        self.rtile_bills = StatTile(rtiles, "จำนวนบิล", "-")
        self.rtile_avg = StatTile(rtiles, "เฉลี่ยต่อบิล", "-")
        self.rtile_pay = StatTile(rtiles, "ช่องทางชำระ", "-", COLORS["info"])
        self.rtile_subtotal = StatTile(rtiles, "ยอดรวมก่อนส่วนลด", "-")
        self.rtile_discount = StatTile(rtiles, "ส่วนลด", "-", COLORS["warning"])
        self.rtile_service = StatTile(rtiles, "ค่าบริการ", "-")
        self.rtile_vat = StatTile(rtiles, "ภาษีมูลค่าเพิ่ม", "-")
        for i, t in enumerate([self.rtile_total, self.rtile_bills, self.rtile_avg, self.rtile_pay,
                               self.rtile_subtotal, self.rtile_discount, self.rtile_service, self.rtile_vat]):
            t.grid(row=i // 4, column=i % 4, padx=6, pady=4, sticky="nsew")

        # แท็บตารางรายงาน
        self.tab_bar = ctk.CTkSegmentedButton(
            scroll, values=TABS, font=font(15), command=self._select_tab,
            selected_color=COLORS["primary"], selected_hover_color=COLORS["primary_hover"]
        )
        self.tab_bar.pack(anchor="w", padx=6, pady=(10, 6))
        self.tab_area = ctk.CTkFrame(scroll, fg_color="transparent", height=360)
        self.tab_area.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._bar_max: dict[str, float] = {"daily": 1, "hourly": 1, "top": 1}

        self.tables = {
            "รายวัน": DataTable(self.tab_area, columns=[
                {"key": "date", "title": "วันที่ (พ.ศ.)", "weight": 2, "min_width": 120, "anchor": "w",
                 "format": lambda v, r: f"{_fmt_iso_to_be(v)} ({v})"},
                {"key": "bill_count", "title": "บิล", "weight": 1, "min_width": 60, "anchor": "w"},
                {"key": "total", "title": "ยอดขาย (บาท)", "weight": 2, "min_width": 120, "anchor": "w",
                 "format": lambda v, r: money(v)},
                {"key": "bar", "title": "สัดส่วน", "weight": 4, "min_width": 160, "anchor": "w",
                 "widget": self._bar_widget("daily"), "sticky": "w"},
            ], empty_text="ไม่มีข้อมูลในช่วงวันที่เลือก"),
            "รายชั่วโมง": DataTable(self.tab_area, columns=[
                {"key": "hour", "title": "ช่วงเวลา", "weight": 2, "min_width": 110, "anchor": "w",
                 "format": lambda v, r: f"{v:02d}:00 - {v:02d}:59"},
                {"key": "bill_count", "title": "บิล", "weight": 1, "min_width": 60, "anchor": "w"},
                {"key": "total", "title": "ยอดขาย (บาท)", "weight": 2, "min_width": 120, "anchor": "w",
                 "format": lambda v, r: money(v)},
                {"key": "bar", "title": "สัดส่วน", "weight": 4, "min_width": 160, "anchor": "w",
                 "widget": self._bar_widget("hourly"), "sticky": "w"},
            ], empty_text="ไม่มีข้อมูลในช่วงวันที่เลือก", row_height=34),
            "เมนูขายดี": DataTable(self.tab_area, columns=[
                {"key": "rank", "title": "#", "weight": 1, "min_width": 45, "anchor": "w"},
                {"key": "name", "title": "เมนู", "weight": 4, "min_width": 140, "anchor": "w"},
                {"key": "quantity", "title": "ขายได้", "weight": 2, "min_width": 100, "anchor": "w",
                 "format": lambda v, r: f"{v:g} {r['unit']}"},
                {"key": "amount", "title": "ยอดเงิน (บาท)", "weight": 2, "min_width": 120, "anchor": "w",
                 "format": lambda v, r: money(v)},
                {"key": "bar", "title": "สัดส่วน", "weight": 3, "min_width": 140, "anchor": "w",
                 "widget": self._bar_widget("top"), "sticky": "w"},
            ], empty_text="ยังไม่มีรายการขายในช่วงวันที่เลือก"),
            "รายการยกเลิก": DataTable(self.tab_area, columns=[
                {"key": "at", "title": "เวลา", "weight": 3, "min_width": 120, "anchor": "w",
                 "format": lambda v, r: fmt_datetime(v)},
                {"key": "kind", "title": "ประเภท", "weight": 2, "min_width": 100, "anchor": "w",
                 "format": lambda v, r: KIND_TH.get(v, v)},
                {"key": "table_no", "title": "โต๊ะ", "weight": 1, "min_width": 55, "anchor": "w"},
                {"key": "name", "title": "รายการ", "weight": 3, "min_width": 120, "anchor": "w"},
                {"key": "amount", "title": "มูลค่า", "weight": 2, "min_width": 85, "anchor": "w",
                 "format": lambda v, r: money(v) if v is not None else "-"},
                {"key": "reason", "title": "เหตุผล", "weight": 4, "min_width": 150, "anchor": "w", "wrap": 220},
                {"key": "by", "title": "โดย", "weight": 2, "min_width": 80, "anchor": "w"},
            ], empty_text="ไม่มีรายการยกเลิกในช่วงวันที่เลือก"),
            "บิล": DataTable(self.tab_area, columns=[
                {"key": "id", "title": "บิล", "weight": 1, "min_width": 50, "anchor": "w"},
                {"key": "paid_at", "title": "ชำระเมื่อ", "weight": 3, "min_width": 120, "anchor": "w",
                 "format": lambda v, r: fmt_datetime(v)},
                {"key": "table_no", "title": "โต๊ะ", "weight": 1, "min_width": 50, "anchor": "w"},
                {"key": "subtotal", "title": "รวม", "weight": 2, "min_width": 80, "anchor": "w",
                 "format": lambda v, r: money(v)},
                {"key": "discount", "title": "ลด", "weight": 2, "min_width": 70, "anchor": "w",
                 "format": lambda v, r: money(v) if v else "-"},
                {"key": "total", "title": "สุทธิ", "weight": 2, "min_width": 90, "anchor": "w",
                 "format": lambda v, r: money(v)},
                {"key": "payment_method_th", "title": "ชำระด้วย", "weight": 2, "min_width": 95, "anchor": "w"},
                {"key": "cashier_name", "title": "ผู้รับเงิน", "weight": 2, "min_width": 95, "anchor": "w",
                 "format": lambda v, r: v or "-"},
            ], empty_text="ไม่มีบิลในช่วงวันที่เลือก"),
        }
        self._current_tab = TABS[0]
        self.tab_bar.set(self._current_tab)
        self.tables[self._current_tab].pack(fill="both", expand=True)
        self.note = ctk.CTkLabel(scroll, text="", font=font(13), text_color=COLORS["text_muted"])
        self.note.pack(anchor="w", padx=8, pady=(0, 8))

    # ---------- ตัวช่วยส่วนรายงาน ----------
    def _bar_widget(self, key: str):
        def make(parent, row):
            frac = (row.get("total", row.get("amount", 0)) or 0) / (self._bar_max.get(key) or 1)
            return bar(parent, frac, COLORS["primary"], width=200)
        return make

    def _select_tab(self, name: str) -> None:
        if name == self._current_tab:
            return
        self.tables[self._current_tab].pack_forget()
        self._current_tab = name
        self.tables[name].pack(fill="both", expand=True)

    def _open_exports(self) -> None:
        if not open_folder(config.EXPORTS_DIR):
            self.toast(f"เปิดโฟลเดอร์ไม่ได้ — ไฟล์อยู่ที่ {config.EXPORTS_DIR}", "warning")

    def _fill_dates(self) -> None:
        self.date_from.set(self.range[0], notify=False)
        self.date_to.set(self.range[1], notify=False)

    def _on_calendar_date_picked(self) -> None:
        """เมื่อเลือกวันที่จากปฏิทิน พ.ศ. ให้ตรวจสอบและดึงข้อมูลรายงานทันที"""
        self.show_report()

    def quick(self, kind: str) -> None:
        self.range = _quick_range(kind)
        self._fill_dates()
        self._report_sig = None
        self.load_report(*self.range)

    def show_report(self) -> None:
        try:
            f = parse_date(self.date_from.get(), "วันที่เริ่ม", allow_empty=False)
            t = parse_date(self.date_to.get(), "วันที่สิ้นสุด", allow_empty=False)
        except ValueError as e:
            self.toast(str(e), "error")
            return
        if f > t:
            self.toast("วันเริ่มต้องไม่หลังวันสิ้นสุด", "error")
            return
        self.range = (f, t)
        self._report_sig = None
        self.load_report(f, t)

    # ---------- โหลดข้อมูล ----------
    def on_open(self, **params) -> None:
        self._report_sig = None
        self._fill_dates()
        self.refresh()

    def refresh(self) -> None:
        self._refresh_overview()
        self.load_report(*self.range)

    def _refresh_overview(self) -> None:
        ok, data = self.call(report_service.today_overview)
        if not ok:
            return
        sales = data["sales"]
        self.header.set_subtitle(f"ข้อมูลวันนี้: {format_thai_date(sales['date_from'], short_month=True)}")
        self.tile_sales.set(baht(sales["total"]), f"ก่อนหักส่วนลด {money(sales['subtotal'])}")
        self.tile_bills.set(f"{sales['bill_count']:,}", "บิลที่ชำระแล้ว")
        self.tile_avg.set(baht(sales["avg_per_bill"]))
        self.tile_discount.set(baht(sales["discount"]))
        self.tile_tables.set(f"{data['tables_in_use']} / {data['tables_total']}", "โต๊ะสถานะ \"ใช้งาน\" / โต๊ะทั้งหมด")
        self.tile_pending.set(str(data["tables_pending"]), "รอพนักงานยืนยัน")
        self.tile_pay.set(str(data["tables_awaiting_payment"]), "เช็คบิลแล้ว รอรับเงิน")
        self.tile_alerts.set(str(data["active_alerts"]), "แถบแดงที่ยังไม่จัดการ" if data["active_alerts"] else "ไม่มี")
        self._draw_low_stock(data["low_stock"])
        self._draw_payments(sales["by_payment"])
        self.cancel_label.configure(
            text=f"ยกเลิกวันนี้: รายการอาหาร {data['cancelled_items_today']} รายการ, "
                 f"โต๊ะ {data['cancelled_sessions_today']} โต๊ะ"
        )

    def _draw_low_stock(self, low: list[dict]) -> None:
        sig = tuple((s["id"], s["quantity"], s["min_quantity"]) for s in low)
        if sig == self._low_sig:
            return
        self._low_sig = sig
        for child in self.low_area.winfo_children():
            child.destroy()
        if not low:
            EmptyState(self.low_area, "สต๊อกทุกรายการยังพอ").pack(pady=24)
            return
        for s in low[:8]:
            row = ctk.CTkFrame(self.low_area, fg_color="transparent")
            row.pack(fill="x", pady=2)
            empty = s["quantity"] <= 0
            ctk.CTkLabel(row, text=s["name"], font=font(15), text_color=COLORS["text"], anchor="w").pack(side="left")
            ctk.CTkLabel(row, text="หมด" if empty else f"เหลือ {fmt_qty(s['quantity'])} {s['unit']}",
                         font=font(15, True), text_color=COLORS["danger"] if empty else COLORS["warning"]
                         ).pack(side="right")
        if len(low) > 8:
            ctk.CTkLabel(self.low_area, text=f"และอีก {len(low) - 8} รายการ", font=font(13),
                         text_color=COLORS["text_muted"]).pack(anchor="w", pady=(4, 0))

    def _draw_payments(self, by_payment: dict) -> None:
        sig = tuple((m, v["count"], v["total"]) for m, v in by_payment.items())
        if sig == self._pay_sig:
            return
        self._pay_sig = sig
        for child in self.pay_area.winfo_children():
            child.destroy()
        biggest = max((v["total"] for v in by_payment.values()), default=0) or 1
        for m, v in by_payment.items():
            if m == "card" and v["count"] == 0:
                continue
            row = ctk.CTkFrame(self.pay_area, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=f"{v['method_th']} ({v['count']} บิล)", font=font(15), width=165,
                         anchor="w", text_color=COLORS["text"]).pack(side="left")
            bar(row, v["total"] / biggest, COLORS["info"], width=150).pack(side="left", padx=8)
            ctk.CTkLabel(row, text=baht(v["total"]), font=font(15, True), anchor="e",
                         text_color=COLORS["text"]).pack(side="right")

    def load_report(self, f: str, t: str) -> None:
        ok, summary = self.call(report_service.sales_summary, f, t)
        if not ok:
            return
        sig = (f, t, summary["bill_count"], summary["total"], summary["discount"])
        if sig == self._report_sig:
            return
        self._report_sig = sig

        f_th = _fmt_iso_to_be(f)
        t_th = _fmt_iso_to_be(t)
        self.report_range_label.configure(
            text=f"ช่วงวันที่ {f_th} ถึง {t_th}" if f != t else f"วันที่ {f_th}"
        )
        self.rtile_total.set(baht(summary["total"]))
        self.rtile_bills.set(f"{summary['bill_count']:,}")
        self.rtile_avg.set(baht(summary["avg_per_bill"]))
        pay = " · ".join(f"{v['method_th']} {money(v['total'])}" for v in summary["by_payment"].values() if v["count"])
        self.rtile_pay.set("-" if not pay else f"{sum(v['count'] for v in summary['by_payment'].values())} บิล", pay or "")
        self.rtile_subtotal.set(baht(summary["subtotal"]))
        self.rtile_discount.set(baht(summary["discount"]))
        self.rtile_service.set(baht(summary["service_charge"]))
        self.rtile_vat.set(baht(summary["vat"]))

        ok, daily = self.call(report_service.daily_sales, f, t)
        self._bar_max["daily"] = max((d["total"] for d in daily), default=0) or 1
        self.tables["รายวัน"].set_rows(daily if ok else [])

        ok, hourly = self.call(report_service.hourly_sales, f, t)
        self._bar_max["hourly"] = max((h["total"] for h in hourly), default=0) or 1
        self.tables["รายชั่วโมง"].set_rows(hourly if ok else [])

        ok, top = self.call(report_service.top_items, f, t, 20)
        top = top if ok else []
        for i, row in enumerate(top, start=1):
            row["rank"] = i
        self._bar_max["top"] = max((x["amount"] for x in top), default=0) or 1
        self.tables["เมนูขายดี"].set_rows(top)

        ok, canc = self.call(report_service.cancellations, f, t)
        rows = []
        if ok:
            items = []
            for it in canc["items"]:
                it = dict(it)
                qty = it["quantity"]
                it["name"] = (f"{it['name']} {qty:g} กก." if it["kind"] == "weigh_entry" else f"{it['name']} ×{qty:g}")
                items.append(it)
            rows = items + [
                {"kind": "session", "table_no": s["table_no"], "name": "ยกเลิกโต๊ะ", "quantity": None, "amount": None,
                 "reason": s["reason"] or "-", "by": CANCELLED_BY_TH.get(s["cancelled_by"], s["cancelled_by"] or "-"),
                 "at": s["at"]} for s in canc["cancelled_sessions"]]
            rows.sort(key=lambda r: r["at"] or "", reverse=True)
        self.tables["รายการยกเลิก"].set_rows(rows)

        ok, bills = self.call(checkout_service.list_bills, f, t, BILL_LIMIT)
        self.tables["บิล"].set_rows(bills if ok else [])
        notes = []
        if ok and summary["bill_count"] > BILL_LIMIT:
            notes.append(f"แท็บบิลแสดง {BILL_LIMIT} บิลล่าสุด จากทั้งหมด {summary['bill_count']:,} บิล (ส่งออก CSV เพื่อดูครบ)")
        if ok and canc["item_count"]:
            notes.append(f"ยกเลิกรายการรวม {canc['item_count']} รายการ มูลค่า {baht(canc['item_amount'])}")
        self.note.configure(text="  ·  ".join(notes))

    # For compatibility with report_page callers
    def load(self, f: str, t: str) -> None:
        self._report_sig = None
        self.load_report(f, t)

    def export_csv(self) -> None:
        try:
            f = parse_date(self.date_from.get(), "วันที่เริ่ม", allow_empty=False)
            t = parse_date(self.date_to.get(), "วันที่สิ้นสุด", allow_empty=False)
        except ValueError as e:
            self.toast(str(e), "error")
            return
        ok, path = self.call(report_service.export_sales_csv, f, t)
        if ok:
            self.toast(f"ส่งออกแล้ว: {path}", "success")
