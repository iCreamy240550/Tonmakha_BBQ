"""ui/owner/report_page.py — รายงานยอดขาย (รวมเข้ากับหน้าแดชบอร์ดแล้ว แต่คงโมดูลนี้ไว้พร้อมปฏิทิน พ.ศ. เพื่อความเข้ากันได้ย้อนหลัง)"""
from __future__ import annotations

from datetime import date, timedelta

import customtkinter as ctk

import config
from services import checkout_service, report_service
from ui.owner._common import DatePickerField, OwnerPage, bar, ce_to_be_year, open_folder, parse_date
from ui.theme import COLORS, baht, fmt_datetime, font, money
from ui.widgets import ActionButton, Card, DataTable, PageHeader, StatTile

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
    else:
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
    title = "รายงาน"

    def build(self) -> None:
        self.range: tuple[str, str] = _quick_range("today")
        header = PageHeader(self, "รายงาน", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "ส่งออก CSV", self.export_csv, "success", height=38, width=120).pack(side="right")
        ActionButton(header.right, "เปิดโฟลเดอร์ exports", lambda: self._open_exports(), "ghost", height=38, width=170).pack(side="right", padx=8)

        filt = Card(self)
        filt.pack(fill="x", padx=24, pady=(0, 8))
        row = ctk.CTkFrame(filt, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)
        self.date_from = DatePickerField(
            row, "จากวันที่ (พ.ศ.)", initial_iso=self.range[0],
            width=210, on_change=lambda _v: self.show_report()
        )
        self.date_from.pack(side="left")
        self.date_to = DatePickerField(
            row, "ถึงวันที่ (พ.ศ.)", initial_iso=self.range[1],
            width=210, on_change=lambda _v: self.show_report()
        )
        self.date_to.pack(side="left", padx=10)
        ActionButton(row, "แสดงรายงาน", self.show_report, "primary", height=42, width=130).pack(side="left", padx=(6, 14), pady=(18, 0))
        quick = ctk.CTkFrame(row, fg_color="transparent")
        quick.pack(side="left", pady=(18, 0))
        for label, kind in (("วันนี้", "today"), ("เมื่อวาน", "yesterday"), ("7 วัน", "7days"),
                            ("เดือนนี้", "month"), ("เดือนที่แล้ว", "lastmonth")):
            ActionButton(quick, label, lambda k=kind: self.quick(k), "ghost", height=36, width=84, size=14).pack(side="left", padx=3)

        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.pack(fill="x", padx=18)
        for c in range(4):
            tiles.grid_columnconfigure(c, weight=1, uniform="rt")
        self.tile_total = StatTile(tiles, "ยอดสุทธิ", "-", COLORS["primary"])
        self.tile_bills = StatTile(tiles, "จำนวนบิล", "-")
        self.tile_avg = StatTile(tiles, "เฉลี่ยต่อบิล", "-")
        self.tile_pay = StatTile(tiles, "ช่องทางชำระ", "-", COLORS["info"])
        self.tile_subtotal = StatTile(tiles, "ยอดรวมก่อนส่วนลด", "-")
        self.tile_discount = StatTile(tiles, "ส่วนลด", "-", COLORS["warning"])
        self.tile_service = StatTile(tiles, "ค่าบริการ", "-")
        self.tile_vat = StatTile(tiles, "ภาษีมูลค่าเพิ่ม", "-")
        for i, t in enumerate([self.tile_total, self.tile_bills, self.tile_avg, self.tile_pay,
                               self.tile_subtotal, self.tile_discount, self.tile_service, self.tile_vat]):
            t.grid(row=i // 4, column=i % 4, padx=6, pady=4, sticky="nsew")

        self.tab_bar = ctk.CTkSegmentedButton(self, values=TABS, font=font(15), command=self._select_tab,
                                              selected_color=COLORS["primary"], selected_hover_color=COLORS["primary_hover"])
        self.tab_bar.pack(anchor="w", padx=24, pady=(8, 6))
        self.tab_area = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_area.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        self._bar_max: dict[str, float] = {"daily": 1, "hourly": 1, "top": 1}
        self.tables = {
            "รายวัน": DataTable(self.tab_area, columns=[
                {"key": "date", "title": "วันที่ (พ.ศ.)", "weight": 2, "min_width": 120, "anchor": "w",
                 "format": lambda v, r: f"{_fmt_iso_to_be(v)} ({v})"},
                {"key": "bill_count", "title": "บิล", "weight": 1, "min_width": 60, "anchor": "w"},
                {"key": "total", "title": "ยอดขาย (บาท)", "weight": 2, "min_width": 120, "anchor": "w", "format": lambda v, r: money(v)},
                {"key": "bar", "title": "สัดส่วน", "weight": 4, "min_width": 160, "anchor": "w", "widget": self._bar_widget("daily"), "sticky": "w"},
            ], empty_text="ไม่มีข้อมูล"),
            "รายชั่วโมง": DataTable(self.tab_area, columns=[
                {"key": "hour", "title": "ช่วงเวลา", "weight": 2, "min_width": 110, "anchor": "w",
                 "format": lambda v, r: f"{v:02d}:00 - {v:02d}:59"},
                {"key": "bill_count", "title": "บิล", "weight": 1, "min_width": 60, "anchor": "w"},
                {"key": "total", "title": "ยอดขาย (บาท)", "weight": 2, "min_width": 120, "anchor": "w", "format": lambda v, r: money(v)},
                {"key": "bar", "title": "สัดส่วน", "weight": 4, "min_width": 160, "anchor": "w", "widget": self._bar_widget("hourly"), "sticky": "w"},
            ], empty_text="ไม่มีข้อมูล", row_height=34),
            "เมนูขายดี": DataTable(self.tab_area, columns=[
                {"key": "rank", "title": "#", "weight": 1, "min_width": 40, "anchor": "w"},
                {"key": "name", "title": "เมนู", "weight": 4, "min_width": 140, "anchor": "w"},
                {"key": "quantity", "title": "ขายได้", "weight": 2, "min_width": 100, "anchor": "w",
                 "format": lambda v, r: f"{v:g} {r['unit']}"},
                {"key": "amount", "title": "ยอดเงิน (บาท)", "weight": 2, "min_width": 120, "anchor": "w", "format": lambda v, r: money(v)},
                {"key": "bar", "title": "สัดส่วน", "weight": 3, "min_width": 140, "anchor": "w", "widget": self._bar_widget("top"), "sticky": "w"},
            ], empty_text="ยังไม่มีรายการขายในช่วงนี้"),
            "รายการยกเลิก": DataTable(self.tab_area, columns=[
                {"key": "at", "title": "เวลา", "weight": 3, "min_width": 120, "anchor": "w", "format": lambda v, r: fmt_datetime(v)},
                {"key": "kind", "title": "ประเภท", "weight": 2, "min_width": 100, "anchor": "w", "format": lambda v, r: KIND_TH.get(v, v)},
                {"key": "table_no", "title": "โต๊ะ", "weight": 1, "min_width": 50, "anchor": "w"},
                {"key": "name", "title": "รายการ", "weight": 3, "min_width": 120, "anchor": "w"},
                {"key": "amount", "title": "มูลค่า", "weight": 2, "min_width": 80, "anchor": "w",
                 "format": lambda v, r: money(v) if v is not None else "-"},
                {"key": "reason", "title": "เหตุผล", "weight": 4, "min_width": 150, "anchor": "w", "wrap": 220},
                {"key": "by", "title": "โดย", "weight": 2, "min_width": 80, "anchor": "w"},
            ], empty_text="ไม่มีรายการยกเลิกในช่วงนี้"),
            "บิล": DataTable(self.tab_area, columns=[
                {"key": "id", "title": "บิล", "weight": 1, "min_width": 50, "anchor": "w"},
                {"key": "paid_at", "title": "ชำระเมื่อ", "weight": 3, "min_width": 120, "anchor": "w", "format": lambda v, r: fmt_datetime(v)},
                {"key": "table_no", "title": "โต๊ะ", "weight": 1, "min_width": 50, "anchor": "w"},
                {"key": "subtotal", "title": "รวม", "weight": 2, "min_width": 80, "anchor": "w", "format": lambda v, r: money(v)},
                {"key": "discount", "title": "ลด", "weight": 2, "min_width": 70, "anchor": "w", "format": lambda v, r: money(v) if v else "-"},
                {"key": "total", "title": "สุทธิ", "weight": 2, "min_width": 90, "anchor": "w", "format": lambda v, r: money(v)},
                {"key": "payment_method_th", "title": "ชำระด้วย", "weight": 2, "min_width": 90, "anchor": "w"},
                {"key": "cashier_name", "title": "ผู้รับเงิน", "weight": 2, "min_width": 90, "anchor": "w", "format": lambda v, r: v or "-"},
            ], empty_text="ไม่มีบิลในช่วงนี้"),
        }
        self._current_tab = TABS[0]
        self.tab_bar.set(self._current_tab)
        self.tables[self._current_tab].pack(fill="both", expand=True)
        self.note = ctk.CTkLabel(self, text="", font=font(13), text_color=COLORS["text_muted"])
        self.note.pack(anchor="w", padx=26, pady=(0, 8))

    def _bar_widget(self, key: str):
        def make(parent, row):
            frac = (row.get("total", row.get("amount", 0)) or 0) / (self._bar_max.get(key) or 1)
            return bar(parent, frac, COLORS["primary"], width=220)
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

    def on_open(self, **params) -> None:
        self.range = _quick_range("today")
        self._fill_dates()
        self.show_report()

    def refresh(self) -> None:
        self.load(*self.range)

    def reload(self) -> None:
        pass

    def _fill_dates(self) -> None:
        self.date_from.set(self.range[0])
        self.date_to.set(self.range[1])

    def quick(self, kind: str) -> None:
        self.range = _quick_range(kind)
        self._fill_dates()
        self.load(*self.range)

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
        self.load(f, t)

    def load(self, f: str, t: str) -> None:
        ok, summary = self.call(report_service.sales_summary, f, t)
        if not ok:
            return
        self.header.set_subtitle(f"ช่วงวันที่ {_fmt_iso_to_be(f)} ถึง {_fmt_iso_to_be(t)}" if f != t else f"วันที่ {_fmt_iso_to_be(f)}")
        self.tile_total.set(baht(summary["total"]))
        self.tile_bills.set(f"{summary['bill_count']:,}")
        self.tile_avg.set(baht(summary["avg_per_bill"]))
        pay = " · ".join(f"{v['method_th']} {money(v['total'])}" for v in summary["by_payment"].values() if v["count"])
        self.tile_pay.set("-" if not pay else f"{sum(v['count'] for v in summary['by_payment'].values())} บิล", pay or "")
        self.tile_subtotal.set(baht(summary["subtotal"]))
        self.tile_discount.set(baht(summary["discount"]))
        self.tile_service.set(baht(summary["service_charge"]))
        self.tile_vat.set(baht(summary["vat"]))

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
