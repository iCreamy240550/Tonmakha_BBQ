"""ui/owner/menu_page.py — เมนูและราคา + จัดการรูปภาพเมนู 1:1 + ลบรายการเมนู (เจ้าของ)

ซ้าย: หมวดเมนู (เพิ่ม/เปลี่ยนชื่อ/ซ่อน-แสดง/เลื่อนลำดับ) · ขวา: รายการเมนูของหมวดที่เลือก (หรือทั้งหมด)
- เพิ่ม/แก้เมนู: ชื่อ, หมวด, ราคา, ผูกสต๊อก, รูปภาพเมนู (JPG/PNG/WebP ปรับสัดส่วน 1:1 อัตโนมัติ พร้อมตัวอย่างและปุ่มลบรูป)
- ปุ่มต่อแถว: แก้ไข / ทำเป็นหมด-มีขาย / ซ่อน-แสดง / ลบ (แสดงหน้าต่างยืนยันพร้อมชื่อเมนู และป้องกันข้อมูลการขายเก่าเสียหาย)
- การจัดแนวตาราง: ทุกคอลัมน์ชิดซ้าย ยกเว้นคอลัมน์ "รูปภาพ" และ "สถานะ" จัดกึ่งกลางตามข้อกำหนดใน PDF
"""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageOps

import config
from services import menu_service, stock_service
from ui.owner._common import LabeledMenu, OwnerPage, parse_number
from ui.theme import COLORS, font, money
from ui.widgets import (ActionButton, BaseDialog, Card, DataTable, LabeledEntry, PageHeader, StatusBadge,
                        ask_text, confirm)

ALL_CATEGORIES = "ทั้งหมด"
NO_STOCK = "ไม่ผูกสต๊อก"
TYPE_LABELS = {config.MENU_TYPE_WEIGHED: "ชั่งกิโล (บาท/กก.)", config.MENU_TYPE_NORMAL: "ปกติ (บาท/หน่วย)"}
TYPE_SHORT = {config.MENU_TYPE_WEIGHED: "ชั่งกิโล", config.MENU_TYPE_NORMAL: "ปกติ"}
_IMG_UNCHANGED = menu_service._UNSET
PREVIEW_DIM = 96


def stock_labels(stock_items: list[dict]) -> dict[str, int]:
    """ชื่อที่แสดงในเมนูเลือก -> id (ชื่อซ้ำจะต่อ #id ให้ไม่ชนกัน)"""
    labels: dict[str, int] = {}
    for s in stock_items:
        label = f"{s['name']} ({s['unit']})"
        if label in labels:
            label = f"{label} #{s['id']}"
        labels[label] = s["id"]
    return labels


class ItemDialog(BaseDialog):
    """เพิ่ม/แก้เมนู พร้อมอัปโหลด/ดูตัวอย่าง/ลบรูปภาพเมนู (1:1 square)
    -> result = dict(name, category_id, item_type, price, stock_item_id, image_source)"""
    def __init__(self, parent, categories: list[dict], stock_items: list[dict], item: dict | None = None,
                 default_category_id: int | None = None):
        super().__init__(parent, "แก้ไขเมนู" if item else "เพิ่มเมนู", width=480)
        self.item = item
        self.cat_map = {c["name"] + ("" if c["active"] else " (ซ่อนอยู่)"): c["id"] for c in categories}
        self.stock_map = {NO_STOCK: None, **stock_labels(stock_items)}
        self.item_type = item["item_type"] if item else config.MENU_TYPE_NORMAL
        self._image_source = _IMG_UNCHANGED
        self._preview_ctk_img = None

        self.name = LabeledEntry(self.body, "ชื่อเมนู", placeholder="เช่น หมูสามชั้น")
        self.name.pack(fill="x")
        self.category = LabeledMenu(self.body, "หมวด", list(self.cat_map))
        self.category.pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(self.body, text="ประเภท", font=font(14), text_color=COLORS["text_muted"]).pack(anchor="w", pady=(8, 0))
        if item:
            ctk.CTkLabel(self.body, text=TYPE_LABELS[self.item_type] + "  (เปลี่ยนประเภทไม่ได้)",
                         font=font(15), text_color=COLORS["text"]).pack(anchor="w")
        else:
            self.type_seg = ctk.CTkSegmentedButton(self.body, values=list(TYPE_LABELS.values()), font=font(14),
                                                   command=self._on_type, selected_color=COLORS["primary"],
                                                   selected_hover_color=COLORS["primary_hover"])
            self.type_seg.set(TYPE_LABELS[self.item_type])
            self.type_seg.pack(fill="x", pady=(2, 0))
        self.price = LabeledEntry(self.body, self._price_label(), placeholder="0.00")
        self.price.pack(fill="x", pady=(8, 0))
        self.price_caption = next((w for w in self.price.winfo_children() if isinstance(w, ctk.CTkLabel)), None)
        self.stock = LabeledMenu(self.body, "ผูกกับสต๊อก (ตัดสต๊อก/หมดอัตโนมัติ)", list(self.stock_map))
        self.stock.pack(fill="x", pady=(8, 0))

        # --- ส่วนจัดการรูปภาพเมนู (1:1 Square) ---
        img_box = ctk.CTkFrame(self.body, fg_color=COLORS["row_alt"], corner_radius=10, border_width=1, border_color=COLORS["card_border"])
        img_box.pack(fill="x", pady=(10, 0))
        img_row = ctk.CTkFrame(img_box, fg_color="transparent")
        img_row.pack(fill="x", padx=12, pady=10)
        self.preview_label = ctk.CTkLabel(
            img_row, text="ไม่มีรูป\n(1:1)", width=PREVIEW_DIM, height=PREVIEW_DIM,
            fg_color="#efe6d8", text_color=COLORS["text_muted"], font=font(13), corner_radius=8
        )
        self.preview_label.pack(side="left", padx=(0, 12))
        img_ctrl = ctk.CTkFrame(img_row, fg_color="transparent")
        img_ctrl.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(img_ctrl, text="รูปภาพเมนู (แสดงสัดส่วน 1:1)", font=font(14, True), text_color=COLORS["text"]).pack(anchor="w")
        self.img_status = ctk.CTkLabel(
            img_ctrl, text="รองรับ JPG, PNG, WebP (ไม่เกิน 5 MB)",
            font=font(12), text_color=COLORS["text_muted"], wraplength=280, justify="left"
        )
        self.img_status.pack(anchor="w", pady=(2, 6))
        btn_row = ctk.CTkFrame(img_ctrl, fg_color="transparent")
        btn_row.pack(anchor="w")
        ActionButton(btn_row, "เลือกรูป...", self.browse_image, "info", height=32, width=100, size=13).pack(side="left", padx=(0, 6))
        self.remove_img_btn = ActionButton(btn_row, "ลบรูป", self.clear_image, "danger", height=32, width=84, size=13)
        self.remove_img_btn.pack(side="left")

        self.error = ctk.CTkLabel(self.body, text="", font=font(13), text_color=COLORS["danger"], wraplength=420,
                                  justify="left")
        self.error.pack(anchor="w", pady=(6, 0))

        if item:
            self.name.set(item["name"])
            self.price.set(f"{item['price']:g}")
            cat_label = next((l for l, cid in self.cat_map.items() if cid == item["category_id"]), None)
            if cat_label:
                self.category.set(cat_label)
            stock_label = next((l for l, sid in self.stock_map.items() if sid == item["stock_item_id"]), NO_STOCK)
            self.stock.set(stock_label)
            existing_file = menu_service.get_item_image_file(item)
            self._load_preview(existing_file)
        else:
            self._load_preview(None)
            if default_category_id is not None:
                cat_label = next((l for l, cid in self.cat_map.items() if cid == default_category_id), None)
                if cat_label:
                    self.category.set(cat_label)
        self.add_buttons("บันทึก", "ยกเลิก", on_confirm=self._submit)

    def _price_label(self) -> str:
        return "ราคา (บาทต่อ 1 กก.)" if self.item_type == config.MENU_TYPE_WEIGHED else "ราคา (บาทต่อหน่วย)"

    def _on_type(self, label: str) -> None:
        self.item_type = next(k for k, v in TYPE_LABELS.items() if v == label)
        if self.price_caption is not None:
            self.price_caption.configure(text=self._price_label())

    def _load_preview(self, img_path: Path | None) -> None:
        if img_path is not None and img_path.exists():
            try:
                with Image.open(img_path) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    sq = ImageOps.fit(im, (PREVIEW_DIM, PREVIEW_DIM), method=Image.Resampling.LANCZOS)
                self._preview_ctk_img = ctk.CTkImage(light_image=sq, size=(PREVIEW_DIM, PREVIEW_DIM))
                self.preview_label.configure(image=self._preview_ctk_img, text="")
                self.img_status.configure(text=f"ไฟล์: {img_path.name}", text_color=COLORS["success"])
                self.remove_img_btn.configure(state="normal")
                return
            except Exception as e:
                self.error.configure(text=f"ไม่สามารถแสดงตัวอย่างรูปได้: {e}")
        self._preview_ctk_img = None
        self.preview_label.configure(image=None, text="ไม่มีรูป\n(1:1)")
        self.img_status.configure(text="ยังไม่มีรูปภาพ (รองรับ JPG, PNG, WebP ≤ 5 MB)", text_color=COLORS["text_muted"])
        self.remove_img_btn.configure(state="disabled")

    def select_image_file(self, path_str: str | Path) -> bool:
        """ตั้งค่ารูปภาพที่เลือก (พร้อมตรวจสอบขนาดและชนิดไฟล์เบื้องต้นเพื่อแสดงตัวอย่าง 1:1)"""
        p = Path(path_str)
        if not p.exists() or not p.is_file():
            self.error.configure(text="ไม่พบไฟล์รูปภาพที่เลือก")
            return False
        if p.suffix.lower() not in config.ALLOWED_IMAGE_EXTENSIONS:
            self.error.configure(text="นามสกุลไฟล์ไม่รองรับ (รองรับเฉพาะ JPG, JPEG, PNG และ WebP)")
            return False
        if p.stat().st_size > config.MAX_IMAGE_SIZE_BYTES:
            self.error.configure(text=f"ไฟล์มีขนาดใหญ่เกิน {config.MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB")
            return False
        try:
            with Image.open(p) as probe:
                fmt = (probe.format or "").upper()
                probe.verify()
            if fmt not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("ชนิดไฟล์ไม่รองรับ")
        except Exception:
            self.error.configure(text="ไฟล์รูปภาพไม่ถูกต้องหรือเสียหาย")
            return False
        self.error.configure(text="")
        self._image_source = p
        self._load_preview(p)
        return True

    def browse_image(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="เลือกรูปภาพเมนู",
            filetypes=[("ไฟล์รูปภาพ", "*.jpg *.jpeg *.png *.webp")],
        )
        if path:
            self.select_image_file(path)

    def clear_image(self) -> None:
        self._image_source = None
        self._load_preview(None)
        self.img_status.configure(text="จะลบรูปภาพเมื่อกดบันทึก", text_color=COLORS["warning"])

    def _submit(self) -> None:
        try:
            name = self.name.get()
            if not name:
                raise ValueError("กรุณากรอกชื่อเมนู")
            price = parse_number(self.price.get(), "ราคา", minimum=0)
        except ValueError as e:
            self.error.configure(text=str(e))
            return
        self.close({
            "name": name,
            "category_id": self.cat_map[self.category.get()],
            "item_type": self.item_type,
            "price": price,
            "stock_item_id": self.stock_map[self.stock.get()],
            "image_source": self._image_source,
        })


class Page(OwnerPage):
    title = "เมนูและราคา"

    def build(self) -> None:
        self.category_id: int | None = None          # None = ทั้งหมด
        self.categories: list[dict] = []
        self.stock_items: list[dict] = []
        self.stock_names: dict[int, str] = {}
        self._deleting: bool = False

        header = PageHeader(self, "เมนูและราคา", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "+ เพิ่มเมนู", self.add_item, "primary", height=38, width=120).pack(side="right")
        self.btn_down = ActionButton(header.right, "▼", lambda: self.move_item(1), "ghost", height=38, width=44)
        self.btn_down.pack(side="right", padx=(0, 8))
        self.btn_up = ActionButton(header.right, "▲", lambda: self.move_item(-1), "ghost", height=38, width=44)
        self.btn_up.pack(side="right", padx=(0, 4))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        body.grid_columnconfigure(0, weight=2, uniform="m")
        body.grid_columnconfigure(1, weight=7, uniform="m")
        body.grid_rowconfigure(0, weight=1)

        left = Card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(left, text="หมวดเมนู", font=font(18, True), text_color=COLORS["text"]).pack(anchor="w", padx=14, pady=(12, 4))
        self.cat_area = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.cat_area.pack(fill="both", expand=True, padx=6)
        tools = ctk.CTkFrame(left, fg_color="transparent")
        tools.pack(fill="x", padx=10, pady=(4, 12))
        ActionButton(tools, "+ หมวด", self.add_category, "success", height=34, width=80, size=14).pack(side="left")
        ActionButton(tools, "เปลี่ยนชื่อ", self.rename_category, "ghost", height=34, width=90, size=14).pack(side="left", padx=4)
        ActionButton(tools, "▲", lambda: self.move_category(-1), "ghost", height=34, width=36, size=14).pack(side="left")
        ActionButton(tools, "▼", lambda: self.move_category(1), "ghost", height=34, width=36, size=14).pack(side="left", padx=(4, 0))
        self.btn_cat_toggle = ActionButton(left, "ซ่อนหมวดนี้", self.toggle_category, "ghost", height=34, size=14)
        self.btn_cat_toggle.pack(fill="x", padx=10, pady=(0, 12))

        self.table = DataTable(body, columns=[
            {"key": "name", "title": "ชื่อเมนู", "weight": 3, "min_width": 135, "anchor": "w"},
            {"key": "category_name", "title": "หมวด", "weight": 2, "min_width": 90, "anchor": "w"},
            {"key": "item_type", "title": "ประเภท", "weight": 2, "min_width": 75, "anchor": "w",
             "format": lambda v, r: TYPE_SHORT.get(v, v)},
            {"key": "price", "title": "ราคา", "weight": 2, "min_width": 95, "anchor": "w",
             "format": lambda v, r: money(v) + (" /กก." if r["item_type"] == config.MENU_TYPE_WEIGHED else "")},
            {"key": "stock_item_id", "title": "สต๊อกที่ผูก", "weight": 2, "min_width": 90, "anchor": "w",
             "format": lambda v, r: self.stock_names.get(v, "-") if v else "-"},
            {"key": "has_image", "title": "รูปภาพ", "weight": 1, "min_width": 65, "anchor": "center",
             "format": lambda v, r: "มีรูป" if v else "-"},
            {"key": "status", "title": "สถานะ", "weight": 2, "min_width": 85, "anchor": "center",
             "widget": self._status_badge, "sticky": ""},
            {"key": "actions", "title": "จัดการ", "weight": 6, "min_width": 290, "anchor": "w",
             "widget": self._row_actions, "sticky": "w"},
        ], on_select=lambda r: self._update_move_buttons(), empty_text="ยังไม่มีเมนูในหมวดนี้")
        self.table.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    # ---------- โหลดข้อมูล ----------
    def on_open(self, **params) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.categories = menu_service.list_categories(include_inactive=True)
        if self.category_id is not None and not any(c["id"] == self.category_id for c in self.categories):
            self.category_id = None
        self.stock_items = stock_service.list_items(include_inactive=True)
        self.stock_names = {s["id"]: s["name"] for s in self.stock_items}
        self._draw_categories()
        items = menu_service.list_items(self.category_id, include_inactive=True)
        self.table.set_rows(items)
        self._update_move_buttons()
        active = sum(1 for i in items if i["active"])
        self.header.set_subtitle(f"{len(items)} รายการ (ขายอยู่ {active})")

    def _draw_categories(self) -> None:
        for child in self.cat_area.winfo_children():
            child.destroy()
        entries = [(None, ALL_CATEGORIES, True)] + [(c["id"], c["name"] + ("" if c["active"] else " (ซ่อน)"), c["active"])
                                                    for c in self.categories]
        for cid, label, active in entries:
            selected = cid == self.category_id
            ctk.CTkButton(
                self.cat_area, text=label, anchor="w", height=36, font=font(15, selected),
                fg_color=COLORS["primary"] if selected else "transparent",
                hover_color=COLORS["primary_hover"] if selected else COLORS["row_hover"],
                text_color="#ffffff" if selected else (COLORS["text"] if active else COLORS["text_muted"]),
                corner_radius=8, command=lambda c=cid: self.select_category(c)).pack(fill="x", pady=2, padx=4)
        cat = self._current_category()
        self.btn_cat_toggle.configure(text=("แสดงหมวดนี้อีกครั้ง" if cat and not cat["active"] else "ซ่อนหมวดนี้"))

    def _current_category(self) -> dict | None:
        return next((c for c in self.categories if c["id"] == self.category_id), None)

    def select_category(self, category_id: int | None) -> None:
        self.category_id = category_id
        self.refresh()

    def _update_move_buttons(self) -> None:
        enabled = self.category_id is not None and self.table.selected is not None
        for b in (self.btn_up, self.btn_down):
            b.configure(state="normal" if enabled else "disabled")

    # ---------- แถวในตาราง ----------
    def _status_badge(self, parent, row: dict):
        if not row["active"]:
            return StatusBadge(parent, "ซ่อนอยู่", COLORS["neutral"])
        if row["is_sold_out"]:
            return StatusBadge(parent, "หมด", COLORS["danger"])
        return StatusBadge(parent, "ขายอยู่", COLORS["success"])

    def _row_actions(self, parent, row: dict):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        ActionButton(box, "แก้ไข", lambda r=row: self.edit_item(r), "info", height=30, width=56, size=13).pack(side="left", padx=2)
        ActionButton(box, "มีขาย" if row["is_sold_out"] else "ทำเป็นหมด", lambda r=row: self.toggle_sold_out(r),
                     "success" if row["is_sold_out"] else "ghost", height=30, width=84, size=13).pack(side="left", padx=2)
        ActionButton(box, "แสดง" if not row["active"] else "ซ่อน", lambda r=row: self.toggle_active(r),
                     "ghost", height=30, width=54, size=13).pack(side="left", padx=2)
        ActionButton(box, "ลบ", lambda r=row: self.delete_item(r), "danger", height=30, width=52, size=13).pack(side="left", padx=2)
        return box

    # ---------- การกระทำ: เมนู ----------
    def add_item(self) -> None:
        if not [c for c in self.categories if c["active"]]:
            self.toast("ต้องมีหมวดที่ใช้งานอย่างน้อย 1 หมวดก่อน", "error")
            return
        dlg = ItemDialog(self, [c for c in self.categories if c["active"]],
                         [s for s in self.stock_items if s["active"]], default_category_id=self.category_id)
        data = dlg.show()
        if not data:
            return
        img_src = None if data["image_source"] is _IMG_UNCHANGED else data["image_source"]
        ok, _ = self.call(
            menu_service.add_item,
            data["category_id"], data["name"], data["item_type"], data["price"],
            stock_item_id=data["stock_item_id"], image_source=img_src,
            user_id=self.user_id, success="เพิ่มเมนูแล้ว",
        )
        if ok:
            self.refresh()

    def edit_item(self, row: dict) -> None:
        linked = row["stock_item_id"]
        stock = [s for s in self.stock_items if s["active"] or s["id"] == linked]
        dlg = ItemDialog(self, self.categories, stock, item=row)
        data = dlg.show()
        if not data:
            return
        ok, _ = self.call(
            menu_service.update_item,
            row["id"],
            name=data["name"],
            price=data["price"],
            category_id=data["category_id"],
            stock_item_id=data["stock_item_id"],
            image_source=data["image_source"],
            user_id=self.user_id,
            success="บันทึกเมนูแล้ว",
        )
        if ok:
            self.refresh()

    def remove_image(self, row: dict) -> None:
        if not confirm(
            self,
            f"ต้องการลบรูปภาพของเมนู \"{row['name']}\" ใช่หรือไม่?",
            title="ลบรูปภาพเมนู",
            confirm_text="ลบรูป",
            danger=True,
        ):
            return
        ok, _ = self.call(menu_service.delete_item_image, row["id"], user_id=self.user_id, success="ลบรูปภาพเมนูแล้ว")
        if ok:
            self.refresh()

    def delete_item(self, row: dict) -> None:
        if self._deleting:
            return
        ok_imp, impact = self.call(menu_service.get_delete_impact, row["id"])
        if not ok_imp or not impact:
            return
        msg = (
            f"ต้องการลบเมนู \"{row['name']}\" ใช่หรือไม่?\n\n"
            f"{impact['impact_text']}"
        )
        if not confirm(self, msg, title="ยืนยันการลบเมนู", confirm_text="ลบเมนู", danger=True):
            return
        self._deleting = True
        try:
            ok, res = self.call(menu_service.delete_item, row["id"], user_id=self.user_id)
            if ok and res:
                self.toast(res["message"], "success")
                self.refresh()
        finally:
            self._deleting = False

    def toggle_sold_out(self, row: dict) -> None:
        ok, changed = self.call(menu_service.set_sold_out, row["id"], not row["is_sold_out"], user_id=self.user_id)
        if ok:
            self.toast(f"{row['name']} {'กลับมามีขาย' if row['is_sold_out'] else 'ทำเป็นหมดแล้ว (แจ้งโต๊ะที่นั่งอยู่)'}", "success")
            self.refresh()

    def toggle_active(self, row: dict) -> None:
        if row["active"] and not confirm(self, f"ซ่อนเมนู \"{row['name']}\" ?\nลูกค้าจะไม่เห็นเมนูนี้ (ประวัติเดิมไม่หาย)",
                                         title="ซ่อนเมนู", confirm_text="ซ่อน"):
            return
        ok, _ = self.call(menu_service.update_item, row["id"], active=not row["active"], user_id=self.user_id,
                          success="ซ่อนเมนูแล้ว" if row["active"] else "แสดงเมนูแล้ว")
        if ok:
            self.refresh()

    def move_item(self, delta: int) -> None:
        sel = self.table.selected
        if self.category_id is None or sel is None:
            return
        items = menu_service.list_items(self.category_id, include_inactive=True)
        ids = [i["id"] for i in items]
        if sel["id"] not in ids:
            return
        pos = ids.index(sel["id"])
        new_pos = pos + delta
        if not 0 <= new_pos < len(ids):
            return
        ids.insert(new_pos, ids.pop(pos))
        by_id = {i["id"]: i for i in items}
        for order, item_id in enumerate(ids, start=1):
            if by_id[item_id]["sort_order"] != order:
                ok, _ = self.call(menu_service.update_item, item_id, sort_order=order, user_id=self.user_id)
                if not ok:
                    break
        self.refresh()

    # ---------- การกระทำ: หมวด ----------
    def add_category(self) -> None:
        name = ask_text(self, "ชื่อหมวดใหม่", title="เพิ่มหมวด")
        if name is None:
            return
        ok, cat = self.call(menu_service.add_category, name, user_id=self.user_id, success="เพิ่มหมวดแล้ว")
        if ok:
            self.category_id = cat["id"]
            self.refresh()

    def rename_category(self) -> None:
        cat = self._current_category()
        if cat is None:
            self.toast("เลือกหมวดทางซ้ายก่อน", "warning")
            return
        name = ask_text(self, "ชื่อหมวด", title="เปลี่ยนชื่อหมวด", initial=cat["name"])
        if name is None:
            return
        ok, _ = self.call(menu_service.update_category, cat["id"], name=name, user_id=self.user_id, success="เปลี่ยนชื่อแล้ว")
        if ok:
            self.refresh()

    def toggle_category(self) -> None:
        cat = self._current_category()
        if cat is None:
            self.toast("เลือกหมวดทางซ้ายก่อน", "warning")
            return
        if cat["active"] and not confirm(self, f"ซ่อนหมวด \"{cat['name']}\" ?\nเมนูในหมวดนี้จะไม่แสดงให้ลูกค้า",
                                         title="ซ่อนหมวด", confirm_text="ซ่อน"):
            return
        ok, _ = self.call(menu_service.update_category, cat["id"], active=not cat["active"], user_id=self.user_id,
                          success="ซ่อนหมวดแล้ว" if cat["active"] else "แสดงหมวดแล้ว")
        if ok:
            self.refresh()

    def move_category(self, delta: int) -> None:
        cat = self._current_category()
        if cat is None:
            self.toast("เลือกหมวดทางซ้ายก่อน", "warning")
            return
        ids = [c["id"] for c in self.categories]
        pos = ids.index(cat["id"])
        new_pos = pos + delta
        if not 0 <= new_pos < len(ids):
            return
        ids.insert(new_pos, ids.pop(pos))
        by_id = {c["id"]: c for c in self.categories}
        for order, cid in enumerate(ids, start=1):
            if by_id[cid]["sort_order"] != order:
                ok, _ = self.call(menu_service.update_category, cid, sort_order=order, user_id=self.user_id)
                if not ok:
                    break
        self.refresh()
