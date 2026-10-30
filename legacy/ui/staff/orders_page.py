"""ui/staff/orders_page.py — หน้าออเดอร์: ดู/เปลี่ยนสถานะออเดอร์ตามลำดับ (เริ่มทำ -> เสิร์ฟแล้ว) และสั่งให้ลูกค้า (กรณีไม่มีมือถือ)

เปิดจากหน้าโต๊ะด้วย `app.navigate('orders', session_id=...)` = กรองเฉพาะโต๊ะนั้น
- ออเดอร์ใหม่ (new): แสดงปุ่ม "เริ่มทำ" เพียงปุ่มเดียว
- ออเดอร์กำลังทำ (preparing): แสดงปุ่ม "เสิร์ฟแล้ว" เพียงปุ่มเดียว
- ออเดอร์เสิร์ฟแล้ว (served): ไม่แสดงปุ่มดำเนินการซ้ำ
- ไม่มีปุ่ม "ยกเลิก" และ "ยกเลิกออเดอร์" บนหน้าออเดอร์ตามข้อกำหนด
"""
from __future__ import annotations

import customtkinter as ctk

import config
from services import menu_service, order_service, table_service
from ui.theme import COLORS, baht, font, money
from ui.widgets import ActionButton, BaseDialog, BasePage, EmptyState, OrderCard, PageHeader

COLUMNS = 3
ALL_TABLES = "ทุกโต๊ะ"
FILTER_ACTIVE = "ยังไม่เสิร์ฟ"
FILTER_ALL = "ทั้งหมด"


class Page(BasePage):
    title = "ออเดอร์"
    auto_refresh_ms = 4000

    def build(self) -> None:
        self.session_id: int | None = None
        self._signature = None
        self._updating_order_ids: set[int] = set()
        self._tables: dict[str, int | None] = {ALL_TABLES: None}
        header = PageHeader(self, "ออเดอร์", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "+ สั่งให้ลูกค้า", self.open_create_dialog, "primary", height=38, width=140).pack(side="right")
        self.status_filter = ctk.CTkSegmentedButton(header.right, values=[FILTER_ACTIVE, FILTER_ALL], font=font(14),
                                                    command=lambda v: self._reload_now(), selected_color=COLORS["primary"],
                                                    selected_hover_color=COLORS["primary_hover"])
        self.status_filter.set(FILTER_ACTIVE)
        self.status_filter.pack(side="right", padx=10)
        self.table_menu = ctk.CTkOptionMenu(header.right, values=[ALL_TABLES], width=130, height=36, font=font(15),
                                            dropdown_font=font(14), command=self._on_table_picked)
        self.table_menu.pack(side="right")
        self.area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.area.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for c in range(COLUMNS):
            self.area.grid_columnconfigure(c, weight=1, uniform="ord")

    def on_show(self, session_id: int | None = None, **params) -> None:
        self.session_id = session_id
        self._signature = None
        self.refresh()

    def _reload_now(self) -> None:
        self._signature = None
        self.refresh()

    def _on_table_picked(self, label: str) -> None:
        self.session_id = self._tables.get(label)
        self._reload_now()

    def _gather(self) -> list[dict]:
        only_active = self.status_filter.get() == FILTER_ACTIVE
        tables = {t["session_id"]: t for t in table_service.list_tables_with_status() if t["session_id"]}
        orders: list[dict] = []
        if only_active and self.session_id is None:
            orders = order_service.list_active_orders()
        else:
            sids = [self.session_id] if self.session_id else list(tables)
            for sid in sids:
                t = tables.get(sid)
                for o in order_service.list_orders(sid):
                    if only_active and o["status"] not in ("new", "preparing"):
                        continue
                    o["table_no"] = t["table_no"] if t else None
                    orders.append(o)
            orders.sort(key=lambda o: o["id"])
        return orders

    def refresh(self) -> None:
        usable = [t for t in table_service.list_tables_with_status() if t["status"] in (config.SESSION_OPEN, config.SESSION_AWAITING_PAYMENT)]
        self._tables = {ALL_TABLES: None, **{f"โต๊ะ {t['table_no']}": t["session_id"] for t in usable}}
        self.table_menu.configure(values=list(self._tables))
        label = next((l for l, sid in self._tables.items() if sid == self.session_id), ALL_TABLES)
        if label == ALL_TABLES:
            self.session_id = None
        self.table_menu.set(label)

        orders = self._gather()
        self.header.set_subtitle(f"{len(orders)} ออเดอร์")
        signature = tuple((o["id"], o["status"], tuple((i["id"], i["status"], i["quantity"]) for i in o["items"])) for o in orders)
        if signature == self._signature:
            return
        self._signature = signature
        for child in self.area.winfo_children():
            child.destroy()
        if not orders:
            EmptyState(self.area, "ไม่มีออเดอร์").grid(row=0, column=0, columnspan=COLUMNS, pady=60)
            return
        for i, o in enumerate(orders):
            card = OrderCard(self.area, o, on_status=self.set_status)
            card.grid(row=i // COLUMNS, column=i % COLUMNS, padx=6, pady=6, sticky="new")

    # ---------- การกระทำ ----------
    def set_status(self, order: dict, new_status: str) -> None:
        oid = order["id"]
        if oid in self._updating_order_ids:
            return
        self._updating_order_ids.add(oid)
        try:
            # ตรวจสอบสถานะปัจจุบันก่อนเปลี่ยนสถานะตามลำดับ
            latest = order_service.get_order(oid)
            if latest is None:
                self.toast("ไม่พบออเดอร์", "error")
                self._reload_now()
                return
            if new_status == "preparing" and latest["status"] != "new":
                self.toast("ออเดอร์นี้ไม่ได้อยู่ในสถานะใหม่แล้ว", "warning")
                self._reload_now()
                return
            if new_status == "served" and latest["status"] != "preparing":
                self.toast("ต้องกดเริ่มทำออเดอร์ก่อนจึงจะเสิร์ฟได้", "warning")
                self._reload_now()
                return
            ok, _ = self.call(order_service.set_order_status, oid, new_status, self.user_id)
            if ok:
                self._reload_now()
        finally:
            self._updating_order_ids.discard(oid)

    def open_create_dialog(self) -> None:
        tables = {l: sid for l, sid in self._tables.items() if sid}
        if not tables:
            self.toast("ยังไม่มีโต๊ะที่ใช้งานอยู่", "error")
            return
        dlg = CreateOrderDialog(self, tables, self.session_id)
        result = dlg.show()
        if result:
            sid, items, note = result
            ok, order = self.call(order_service.create_order, sid, items, note or None, self.user_id,
                                  success="บันทึกออเดอร์แล้ว")
            if ok:
                self._reload_now()


class CreateOrderDialog(BaseDialog):
    """พนักงานสั่งให้ลูกค้า: เลือกโต๊ะ + จำนวนต่อเมนู (เฉพาะเมนูปกติที่ไม่หมด) -> result = (session_id, items, note)"""
    def __init__(self, parent, tables: dict[str, int], preselect_session: int | None):
        super().__init__(parent, "สั่งให้ลูกค้า", width=520)
        self.tables = tables
        self.qty: dict[int, int] = {}
        self.qty_labels: dict[int, ctk.CTkLabel] = {}
        top = ctk.CTkFrame(self.body, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text="โต๊ะ", font=font(16, True)).pack(side="left")
        self.table_menu = ctk.CTkOptionMenu(top, values=list(tables), width=160, height=36, font=font(15), dropdown_font=font(14))
        self.table_menu.pack(side="left", padx=10)
        pre = next((l for l, sid in tables.items() if sid == preselect_session), None)
        if pre:
            self.table_menu.set(pre)
        self.total_label = ctk.CTkLabel(top, text="รวม 0.00 บาท", font=font(16, True), text_color=COLORS["primary"])
        self.total_label.pack(side="right")

        scroll = ctk.CTkScrollableFrame(self.body, height=300, fg_color=COLORS["bg"])
        scroll.pack(fill="x", pady=10)
        self.items = [m for m in menu_service.list_items() if m["item_type"] == config.MENU_TYPE_NORMAL and not m["is_sold_out"]]
        for m in self.items:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=4)
            ctk.CTkLabel(row, text=f"{m['name']}  ({money(m['price'])})", font=font(15), anchor="w").pack(side="left")
            ActionButton(row, "+", lambda mm=m: self._change(mm["id"], 1), "success", height=30, width=36, size=16).pack(side="right")
            lbl = ctk.CTkLabel(row, text="0", font=font(16, True), width=36)
            lbl.pack(side="right")
            self.qty_labels[m["id"]] = lbl
            ActionButton(row, "−", lambda mm=m: self._change(mm["id"], -1), "ghost", height=30, width=36, size=16).pack(side="right")
        if not self.items:
            ctk.CTkLabel(scroll, text="ไม่มีเมนูปกติที่สั่งได้", font=font(14), text_color=COLORS["text_muted"]).pack(pady=20)
        self.note = ctk.CTkEntry(self.body, placeholder_text="หมายเหตุ (ถ้ามี)", height=36, font=font(14))
        self.note.pack(fill="x")
        self.error = ctk.CTkLabel(self.body, text="", font=font(13), text_color=COLORS["danger"])
        self.error.pack(anchor="w")
        self.add_buttons("บันทึกออเดอร์", "ยกเลิก", on_confirm=self._submit)

    def _change(self, item_id: int, delta: int) -> None:
        q = max(0, min(99, self.qty.get(item_id, 0) + delta))
        self.qty[item_id] = q
        self.qty_labels[item_id].configure(text=str(q))
        total = sum(m["price"] * self.qty.get(m["id"], 0) for m in self.items)
        self.total_label.configure(text=f"รวม {baht(total)}")

    def _submit(self) -> None:
        items = [{"menu_item_id": i, "quantity": q} for i, q in self.qty.items() if q > 0]
        if not items:
            self.error.configure(text="ยังไม่ได้เลือกรายการ")
            return
        self.close((self.tables[self.table_menu.get()], items, self.note.get().strip()))
