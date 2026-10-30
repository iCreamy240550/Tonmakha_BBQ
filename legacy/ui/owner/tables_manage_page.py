"""ui/owner/tables_manage_page.py — จัดการโต๊ะ + QR (เจ้าของ)

ซ้าย: รายการโต๊ะ (เพิ่ม/เปลี่ยนชื่อ/เปิด-ปิดใช้/สุ่มรหัสลับใหม่) · ขวา: ตัวอย่าง QR ของโต๊ะที่เลือก + ลิงก์
- การจัดแนวตาราง: ทุกคอลัมน์ชิดซ้าย ยกเว้นคอลัมน์ "สถานะ" จัดกึ่งกลางตามข้อกำหนดใน PDF
"""
from __future__ import annotations

from urllib.parse import urlparse

import customtkinter as ctk
from PIL import Image

import config
from services import qr_service, table_service
from ui.owner._common import OwnerPage, open_folder, parse_int
from ui.theme import COLORS, font, status_color
from ui.widgets import (ActionButton, BaseDialog, Card, DataTable, LabeledEntry, PageHeader, StatusBadge,
                        ask_text, confirm)

PREVIEW_SIZE = 250
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def qr_file_for(table_no: int):
    return config.QR_DIR / f"table_{table_no}.png"


def url_is_local(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "").lower() in LOCAL_HOSTS
    except ValueError:
        return True


class AddTableDialog(BaseDialog):
    """เพิ่มโต๊ะ -> result = (table_no:int, name:str)"""
    def __init__(self, parent, suggested_no: int):
        super().__init__(parent, "เพิ่มโต๊ะ", width=400)
        self.no = LabeledEntry(self.body, "เลขโต๊ะ", placeholder="เช่น 11")
        self.no.pack(fill="x")
        self.no.set(str(suggested_no))
        self.name = LabeledEntry(self.body, "ชื่อโต๊ะ (ว่าง = \"โต๊ะ <เลข>\")", placeholder="เช่น โต๊ะริมสระ")
        self.name.pack(fill="x", pady=(8, 0))
        self.error = ctk.CTkLabel(self.body, text="", font=font(13), text_color=COLORS["danger"])
        self.error.pack(anchor="w", pady=(6, 0))
        self.add_buttons("เพิ่มโต๊ะ", "ยกเลิก", on_confirm=self._submit)

    def _submit(self) -> None:
        try:
            no = parse_int(self.no.get(), "เลขโต๊ะ", minimum=1)
        except ValueError as e:
            self.error.configure(text=str(e))
            return
        self.close((no, self.name.get()))


class Page(OwnerPage):
    title = "จัดการโต๊ะ/QR"

    def build(self) -> None:
        self.tables: list[dict] = []
        self._qr_image = None
        header = PageHeader(self, "จัดการโต๊ะและ QR", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "+ เพิ่มโต๊ะ", self.add_table, "primary", height=38, width=110).pack(side="right")
        ActionButton(header.right, "สร้าง QR ทุกโต๊ะ", self.generate_all, "success", height=38, width=140).pack(side="right", padx=8)
        ActionButton(header.right, "เปิดโฟลเดอร์ QR", lambda: self._open_qr_folder(), "ghost", height=38, width=140).pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        body.grid_columnconfigure(0, weight=6, uniform="t")
        body.grid_columnconfigure(1, weight=4, uniform="t")
        body.grid_rowconfigure(0, weight=1)

        self.table = DataTable(body, columns=[
            {"key": "table_no", "title": "เลข", "weight": 1, "min_width": 55, "anchor": "w"},
            {"key": "name", "title": "ชื่อโต๊ะ", "weight": 3, "min_width": 110, "anchor": "w"},
            {"key": "status", "title": "สถานะ", "weight": 2, "min_width": 95, "anchor": "center",
             "widget": self._status_badge, "sticky": ""},
            {"key": "qr", "title": "ไฟล์ QR", "weight": 2, "min_width": 85, "anchor": "w",
             "format": lambda v, r: "สร้างแล้ว" if qr_file_for(r["table_no"]).exists() else "ยังไม่สร้าง"},
            {"key": "actions", "title": "จัดการ", "weight": 6, "min_width": 270, "anchor": "w",
             "widget": self._row_actions, "sticky": "w"},
        ], on_select=lambda r: self._show_preview(), empty_text="ยังไม่มีโต๊ะ")
        self.table.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right = Card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.preview_title = ctk.CTkLabel(right, text="ตัวอย่าง QR", font=font(18, True), text_color=COLORS["text"])
        self.preview_title.pack(anchor="w", padx=16, pady=(12, 4))
        self.preview_box = ctk.CTkLabel(right, text="เลือกโต๊ะทางซ้าย", font=font(15), text_color=COLORS["text_muted"],
                                        width=PREVIEW_SIZE, height=PREVIEW_SIZE, fg_color=COLORS["row_alt"], corner_radius=10)
        self.preview_box.pack(padx=16, pady=6)
        self.url_entry = ctk.CTkEntry(right, height=36, font=font(12), fg_color=COLORS["input_bg"],
                                      border_color=COLORS["input_border"])
        self.url_entry.pack(fill="x", padx=16, pady=(6, 0))
        self.warn_label = ctk.CTkLabel(right, text="", font=font(13), text_color=COLORS["danger"], wraplength=330,
                                       justify="left")
        self.warn_label.pack(fill="x", padx=16, pady=(6, 0))
        btns = ctk.CTkFrame(right, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(8, 14))
        ActionButton(btns, "สร้าง/อัปเดตรูป QR", self.generate_selected, "success", height=36, width=150, size=14).pack(side="left")
        ActionButton(btns, "คัดลอกลิงก์", self.copy_link, "ghost", height=36, width=110, size=14).pack(side="left", padx=8)

    # ---------- โหลดข้อมูล ----------
    def on_open(self, **params) -> None:
        self.refresh()

    def refresh(self) -> None:
        live = {t["id"]: t for t in table_service.list_tables_with_status()}
        self.tables = []
        for t in table_service.list_tables(include_inactive=True):
            t["status_key"] = live[t["id"]]["status"] if t["id"] in live else "inactive"
            t["status_th"] = live[t["id"]]["status_th"] if t["id"] in live else "ปิดใช้งาน"
            self.tables.append(t)
        self.table.set_rows(self.tables)
        active = sum(1 for t in self.tables if t["active"])
        self.header.set_subtitle(f"{len(self.tables)} โต๊ะ (ใช้งาน {active})")
        self._show_preview()

    def _status_badge(self, parent, row: dict):
        color = COLORS["neutral"] if row["status_key"] == "inactive" else status_color(row["status_key"])
        return StatusBadge(parent, row["status_th"], color)

    def _row_actions(self, parent, row: dict):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        ActionButton(box, "ชื่อ", lambda r=row: self.rename(r), "info", height=30, width=48, size=13).pack(side="left", padx=2)
        ActionButton(box, "สุ่มรหัสใหม่", lambda r=row: self.regenerate(r), "ghost", height=30, width=96, size=13).pack(side="left", padx=2)
        ActionButton(box, "เปิดใช้" if not row["active"] else "ปิดใช้", lambda r=row: self.toggle_active(r),
                     "success" if not row["active"] else "ghost", height=30, width=72, size=13).pack(side="left", padx=2)
        return box

    # ---------- ตัวอย่าง QR ----------
    def _selected_table(self) -> dict | None:
        sel = self.table.selected
        if sel is None:
            return None
        return next((t for t in self.tables if t["id"] == sel["id"]), None)

    def _show_preview(self) -> None:
        t = self._selected_table()
        self.url_entry.configure(state="normal")
        self.url_entry.delete(0, "end")
        if t is None:
            self.preview_title.configure(text="ตัวอย่าง QR")
            self._set_preview_image(None, "เลือกโต๊ะทางซ้าย")
            self.warn_label.configure(text="")
            self.url_entry.configure(state="readonly")
            return
        url = qr_service.build_url(t["table_no"], t["secret_key"])
        self.url_entry.insert(0, url)
        self.url_entry.configure(state="readonly")
        self.preview_title.configure(text=f"QR: {t['name']}")
        path = qr_file_for(t["table_no"])
        if path.exists():
            try:
                self._set_preview_image(Image.open(path).convert("RGB"), "")
            except Exception:
                self._set_preview_image(None, "เปิดรูป QR ไม่ได้ — กด \"สร้าง/อัปเดตรูป QR\"")
        else:
            self._set_preview_image(None, "ยังไม่มีรูป QR\nกด \"สร้าง/อัปเดตรูป QR\"")
        self.warn_label.configure(
            text="ลิงก์ยังเป็น localhost — มือถือลูกค้าสแกนแล้วเข้าไม่ได้ ตั้งค่า \"ลิงก์เว็บลูกค้า\" ที่หน้าตั้งค่าก่อนสร้าง QR"
            if url_is_local(url) else "")

    def _set_preview_image(self, img: Image.Image | None, text: str) -> None:
        if img is None:
            self._qr_image = None
            self.preview_box.configure(image=None, text=text)
            return
        img = img.resize((PREVIEW_SIZE, PREVIEW_SIZE), Image.NEAREST)
        self._qr_image = ctk.CTkImage(light_image=img, size=(PREVIEW_SIZE, PREVIEW_SIZE))
        self.preview_box.configure(image=self._qr_image, text=text)

    # ---------- QR ----------
    def _make_qr(self, table_id: int):
        try:
            return qr_service.generate_qr_image(table_id)
        except ImportError:
            self.toast("ยังไม่ได้ติดตั้งไลบรารี qrcode — รัน pip install -r requirements.txt", "error")
        except ValueError as e:
            self.toast(str(e), "error")
        except Exception as e:
            self.toast(f"สร้าง QR ไม่สำเร็จ: {e}", "error")
        return None

    def generate_selected(self) -> None:
        t = self._selected_table()
        if t is None:
            self.toast("เลือกโต๊ะทางซ้ายก่อน", "warning")
            return
        if self._make_qr(t["id"]):
            self.toast(f"สร้าง QR โต๊ะ {t['table_no']} แล้ว", "success")
            self.refresh()

    def generate_all(self) -> None:
        active = [t for t in self.tables if t["active"]]
        if not active:
            self.toast("ยังไม่มีโต๊ะที่ใช้งาน", "warning")
            return
        if any(url_is_local(qr_service.build_url(t["table_no"], t["secret_key"])) for t in active) and not confirm(
                self, "ลิงก์เว็บลูกค้ายังเป็น localhost — QR ที่สร้างจะใช้กับมือถือไม่ได้\nสร้างต่อหรือไม่?",
                title="ลิงก์ยังเป็น localhost", confirm_text="สร้างต่อ"):
            return
        done = 0
        for t in active:
            if self._make_qr(t["id"]) is None:
                break
            done += 1
        if done:
            self.toast(f"สร้าง QR แล้ว {done} โต๊ะ (ไฟล์อยู่ที่โฟลเดอร์ QR)", "success")
            self.refresh()

    def _open_qr_folder(self) -> None:
        if not open_folder(config.QR_DIR):
            self.toast(f"เปิดโฟลเดอร์ไม่ได้ — ไฟล์อยู่ที่ {config.QR_DIR}", "warning")

    def copy_link(self) -> None:
        t = self._selected_table()
        if t is None:
            self.toast("เลือกโต๊ะทางซ้ายก่อน", "warning")
            return
        self.clipboard_clear()
        self.clipboard_append(qr_service.build_url(t["table_no"], t["secret_key"]))
        self.toast("คัดลอกลิงก์แล้ว", "success")

    # ---------- จัดการโต๊ะ ----------
    def add_table(self) -> None:
        suggested = max((t["table_no"] for t in self.tables), default=0) + 1
        result = AddTableDialog(self, suggested).show()
        if not result:
            return
        no, name = result
        ok, _ = self.call(table_service.add_table, no, name or None, user_id=self.user_id, success=f"เพิ่มโต๊ะ {no} แล้ว")
        if ok:
            self.refresh()

    def rename(self, row: dict) -> None:
        name = ask_text(self, f"ชื่อโต๊ะ {row['table_no']}", title="เปลี่ยนชื่อโต๊ะ", initial=row["name"])
        if name is None:
            return
        ok, _ = self.call(table_service.update_table, row["id"], name=name, user_id=self.user_id, success="เปลี่ยนชื่อแล้ว")
        if ok:
            self.refresh()

    def toggle_active(self, row: dict) -> None:
        if row["active"] and not confirm(self, f"ปิดใช้งาน {row['name']} ?\nลูกค้าสแกน QR ของโต๊ะนี้ไม่ได้จนกว่าจะเปิดใหม่",
                                         title="ปิดใช้งานโต๊ะ", confirm_text="ปิดใช้งาน"):
            return
        ok, _ = self.call(table_service.update_table, row["id"], active=not row["active"], user_id=self.user_id,
                          success="ปิดใช้งานโต๊ะแล้ว" if row["active"] else "เปิดใช้งานโต๊ะแล้ว")
        if ok:
            self.refresh()

    def regenerate(self, row: dict) -> None:
        if not confirm(self, f"สุ่มรหัสลับใหม่ให้ {row['name']} ?\nQR เดิมที่พิมพ์ติดโต๊ะไว้จะใช้ไม่ได้ ต้องพิมพ์ QR ใหม่\n"
                             "(ลูกค้าที่กำลังนั่งอยู่ไม่ได้รับผลกระทบ)", title="สุ่มรหัสลับใหม่",
                       confirm_text="สุ่มรหัสใหม่", danger=True):
            return
        ok, new = self.call(table_service.regenerate_secret, row["id"], user_id=self.user_id, success="เปลี่ยนรหัสลับแล้ว")
        if not ok:
            return
        if qr_file_for(row["table_no"]).exists():
            self._make_qr(row["id"])
        self.refresh()
