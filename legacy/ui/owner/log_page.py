"""ui/owner/log_page.py — ประวัติการใช้งาน (activity_log) สำหรับเจ้าของ

กรองตาม ประเภทการกระทำ / ผู้ใช้ / ช่วงวันที่ (ปี-เดือน-วัน) แล้วเปิดดูทีละหน้า (หน้าละ 100 รายการ ใหม่สุดก่อน)
ผู้กระทำ = ผู้ใช้ที่ล็อกอิน หรือ \"ลูกค้า\"/\"ระบบ\" (กรณี actor) ; อ่านอย่างเดียว ไม่มีแก้/ลบ log
- การจัดแนวตาราง: ทุกคอลัมน์ชิดซ้ายตามข้อกำหนดใน PDF
"""
from __future__ import annotations

import customtkinter as ctk

from services import auth_service, log_service
from ui.owner._common import LabeledMenu, OwnerPage, parse_date
from ui.theme import COLORS, fmt_datetime, font
from ui.widgets import ActionButton, Card, DataTable, LabeledEntry, PageHeader

PAGE_SIZE = 100
ALL = "ทั้งหมด"

# รหัส action -> ข้อความไทย (รหัสที่ไม่อยู่ในรายการนี้จะแสดงรหัสเดิม)
ACTION_TH = {
    "login": "เข้าสู่ระบบ", "login_fail": "เข้าสู่ระบบไม่สำเร็จ", "logout": "ออกจากระบบ",
    "shop_open": "เปิดร้าน", "shop_close": "ปิดร้าน", "shop_closed": "ปิดร้าน",
    "session_start": "ลูกค้าสแกนเข้าโต๊ะ", "session_confirm": "ยืนยันโต๊ะ", "session_cancel": "ยกเลิกโต๊ะ",
    "session_awaiting_payment": "เริ่มเช็คบิล", "session_close": "ปิดโต๊ะ", "checkout_paid": "ชำระเงิน",
    "weigh_add": "ชั่งน้ำหนัก", "weigh_cancel": "ยกเลิกรายการชั่ง",
    "order_create": "สร้างออเดอร์", "order_status": "เปลี่ยนสถานะออเดอร์", "order_item_cancel": "ยกเลิกรายการสั่ง",
    "notice_send": "ส่งข้อความถึงลูกค้า",
    "alert_raised": "แจ้งเตือนด่วน (โต๊ะ/สต๊อก)", "alert_cancel_table": "แจ้งเตือน: ยกเลิกโต๊ะ", "alert_snooze": "แจ้งเตือน: ปล่อยไว้",
    "alert_checked": "แจ้งเตือน: รับทราบ/ไปเช็คแล้ว", "alert_wake": "แจ้งเตือนซ้ำ", "alert_auto_clear": "แจ้งเตือนปิดเอง",
    "menu_category_add": "เพิ่มหมวดเมนู", "menu_category_update": "แก้หมวดเมนู", "menu_item_add": "เพิ่มเมนู",
    "menu_item_update": "แก้เมนู", "menu_item_delete": "ลบ/ปิดใช้เมนู", "menu_price_change": "แก้ราคาเมนู",
    "menu_sold_out": "เมนูหมด", "menu_available": "เมนูกลับมามีขาย", "menu_image_update": "อัปโหลดรูปเมนู", "menu_image_delete": "ลบรูปเมนู",
    "stock_add": "เพิ่มรายการสต๊อก", "stock_update": "แก้รายการสต๊อก", "stock_delete": "ลบ/ปิดใช้รายการสต๊อก",
    "stock_delete_blocked": "ปฏิเสธการลบสต๊อก",
    "promo_add": "เพิ่มโปรโมชั่น", "promo_update": "แก้โปรโมชั่น",
    "table_add": "เพิ่มโต๊ะ", "table_update": "แก้โต๊ะ", "table_secret_reset": "สุ่มรหัสลับ QR ใหม่",
    "user_create": "สร้างผู้ใช้", "user_update": "แก้ผู้ใช้", "password_change": "เปลี่ยนรหัสผ่าน",
    "setting_change": "แก้ตั้งค่า",
    "backup_create": "สำรองข้อมูล", "backup_delete": "ลบไฟล์สำรอง", "backup_prune": "ลบไฟล์สำรองเก่า",
    "backup_restore": "กู้คืนข้อมูล",
}
ACTION_BY_TH = {v: k for k, v in ACTION_TH.items() if k != "shop_closed"}   # shop_closed ซ้ำคำกับ shop_close


def action_text(code: str) -> str:
    return ACTION_TH.get(code, code)


def who_text(row: dict) -> str:
    return row.get("user_name") or row.get("actor") or "-"


class Page(OwnerPage):
    title = "ประวัติการใช้งาน"

    def build(self) -> None:
        self.offset = 0
        self.total = 0
        self._filters: dict = {}
        self._users: dict[str, int | None] = {ALL: None}
        header = PageHeader(self, "ประวัติการใช้งาน", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header

        filt = Card(self)
        filt.pack(fill="x", padx=24, pady=(0, 8))
        row = ctk.CTkFrame(filt, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)
        self.action_menu = LabeledMenu(row, "การกระทำ", [ALL] + sorted(ACTION_BY_TH), width=210)
        self.action_menu.pack(side="left")
        self.user_menu = LabeledMenu(row, "ผู้ใช้", [ALL], width=170)
        self.user_menu.pack(side="left", padx=10)
        self.date_from = LabeledEntry(row, "จากวันที่", width=130, placeholder="ปี-เดือน-วัน")
        self.date_from.pack(side="left")
        self.date_to = LabeledEntry(row, "ถึงวันที่", width=130, placeholder="ปี-เดือน-วัน")
        self.date_to.pack(side="left", padx=10)
        ActionButton(row, "ค้นหา", self.search, "primary", height=40, width=90).pack(side="left", pady=(18, 0))
        ActionButton(row, "ล้างตัวกรอง", self.clear_filters, "ghost", height=40, width=110).pack(side="left", padx=8, pady=(18, 0))

        self.table = DataTable(self, columns=[
            {"key": "created_at", "title": "เวลา", "weight": 3, "min_width": 130, "anchor": "w", "format": lambda v, r: fmt_datetime(v)},
            {"key": "who", "title": "ผู้ทำ", "weight": 2, "min_width": 100, "anchor": "w", "format": lambda v, r: who_text(r)},
            {"key": "action", "title": "การกระทำ", "weight": 3, "min_width": 150, "anchor": "w", "format": lambda v, r: action_text(v)},
            {"key": "detail", "title": "รายละเอียด", "weight": 7, "min_width": 260, "anchor": "w", "wrap": 520,
             "format": lambda v, r: v or ""},
        ], empty_text="ไม่พบประวัติตามเงื่อนไข", row_height=44)
        self.table.pack(fill="both", expand=True, padx=24, pady=(0, 6))

        pager = ctk.CTkFrame(self, fg_color="transparent")
        pager.pack(fill="x", padx=24, pady=(0, 14))
        self.prev_btn = ActionButton(pager, "◀ ใหม่กว่า", self.prev_page, "ghost", height=36, width=110, size=14)
        self.prev_btn.pack(side="left")
        self.page_label = ctk.CTkLabel(pager, text="", font=font(14), text_color=COLORS["text_muted"])
        self.page_label.pack(side="left", padx=14)
        self.next_btn = ActionButton(pager, "เก่ากว่า ▶", self.next_page, "ghost", height=36, width=110, size=14)
        self.next_btn.pack(side="left")

    # ---------- โหลดข้อมูล ----------
    def on_open(self, **params) -> None:
        self._load_users()
        self.offset = 0
        self.search()

    def refresh(self) -> None:
        self._query()

    def reload(self) -> None:
        """log เพิ่มบ่อย (เช่นแจ้งเตือน) — ไม่รีเฟรชเองเพื่อไม่ให้หน้าที่กำลังอ่านเลื่อนหาย"""

    def _load_users(self) -> None:
        users = auth_service.list_users(include_inactive=True)
        self._users = {ALL: None}
        for u in users:
            label = u["display_name"]
            if label in self._users:
                label = f"{label} ({u['username']})"
            self._users[label] = u["id"]
        self.user_menu.configure_values(list(self._users))
        if self.user_menu.get() not in self._users:
            self.user_menu.set(ALL)

    def clear_filters(self) -> None:
        self.action_menu.set(ALL)
        self.user_menu.set(ALL)
        self.date_from.clear()
        self.date_to.clear()
        self.search()

    def search(self) -> None:
        """อ่านตัวกรองจากฟอร์ม (ตรวจรูปแบบวันที่) แล้วโหลดหน้าแรก"""
        try:
            f = parse_date(self.date_from.get(), "วันที่เริ่ม")
            t = parse_date(self.date_to.get(), "วันที่สิ้นสุด")
        except ValueError as e:
            self.toast(str(e), "error")
            return
        if f and t and f > t:
            self.toast("วันเริ่มต้องไม่หลังวันสิ้นสุด", "error")
            return
        action_label = self.action_menu.get()
        self._filters = {
            "action": None if action_label == ALL else ACTION_BY_TH.get(action_label),
            "user_id": self._users.get(self.user_menu.get()),
            "date_from": f or None, "date_to": t or None,
        }
        self.offset = 0
        self._query()

    def _query(self) -> None:
        ok, total = self.call(log_service.count_logs, **self._filters)
        if not ok:
            return
        self.total = total
        if self.offset >= total and self.offset > 0:
            self.offset = max(0, ((total - 1) // PAGE_SIZE) * PAGE_SIZE)
        ok, rows = self.call(log_service.get_logs, limit=PAGE_SIZE, offset=self.offset, **self._filters)
        self.table.set_rows(rows if ok else [])
        first = self.offset + 1 if total else 0
        last = min(self.offset + PAGE_SIZE, total)
        self.header.set_subtitle(f"ทั้งหมด {total:,} รายการ")
        self.page_label.configure(text=f"แสดง {first:,}–{last:,} จาก {total:,}")
        self.prev_btn.configure(state="normal" if self.offset > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.offset + PAGE_SIZE < total else "disabled")

    def prev_page(self) -> None:
        self.offset = max(0, self.offset - PAGE_SIZE)
        self._query()

    def next_page(self) -> None:
        if self.offset + PAGE_SIZE < self.total:
            self.offset += PAGE_SIZE
            self._query()
