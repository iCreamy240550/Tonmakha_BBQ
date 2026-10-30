"""ui/owner/backup_page.py — สำรอง/กู้คืนข้อมูล (เจ้าของ)

- \"สำรองตอนนี้\": สร้างไฟล์ .db ใน backups/ (ปลอดภัยแม้ร้านเปิดอยู่ — ใช้ sqlite backup API)
- ระบบสำรองอัตโนมัติวันละครั้งตอนเปิดแอป (main.py เรียก backup_service.auto_backup) เก็บ 14 ไฟล์ล่าสุด
- การจัดแนวตาราง: ทุกคอลัมน์ชิดซ้ายตามข้อกำหนดใน PDF
"""
from __future__ import annotations

import customtkinter as ctk

import config
from services import backup_service, shop_service
from ui.owner._common import OwnerPage, human_size, open_folder
from ui.theme import COLORS, fmt_datetime, font
from ui.widgets import ActionButton, Card, DataTable, PageHeader, StatusBadge, ask_text, confirm, show_info

CONFIRM_WORD = "กู้คืน"
KIND_COLORS = {"manual": COLORS["info"], "auto": COLORS["neutral"], "prerestore": COLORS["warning"]}


class Page(OwnerPage):
    title = "สำรองข้อมูล"

    def build(self) -> None:
        header = PageHeader(self, "สำรองข้อมูล", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "สำรองตอนนี้", self.backup_now, "success", height=38, width=130).pack(side="right")
        ActionButton(header.right, "เปิดโฟลเดอร์สำรอง", lambda: self._open_folder(), "ghost", height=38, width=160).pack(side="right", padx=8)

        info = Card(self)
        info.pack(fill="x", padx=24, pady=(0, 8))
        self.shop_label = ctk.CTkLabel(info, text="", font=font(15, True), anchor="w", justify="left")
        self.shop_label.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(info, text="ระบบสำรองอัตโนมัติวันละครั้งตอนเปิดแอป (เก็บ 14 ไฟล์ล่าสุด) · ไฟล์สำรองคือฐานข้อมูลทั้งหมดของร้าน "
                                "เก็บสำเนาไว้นอกเครื่อง (เช่น USB/คลาวด์) เป็นระยะเพื่อกันเครื่องเสีย",
                     font=font(13), text_color=COLORS["text_muted"], wraplength=980, justify="left", anchor="w"
                     ).pack(fill="x", padx=16, pady=(2, 12))

        self.table = DataTable(self, columns=[
            {"key": "created_at", "title": "สร้างเมื่อ", "weight": 3, "min_width": 130, "anchor": "w", "format": lambda v, r: fmt_datetime(v)},
            {"key": "kind", "title": "ชนิด", "weight": 3, "min_width": 130, "anchor": "w", "widget": self._kind_badge, "sticky": "w"},
            {"key": "filename", "title": "ชื่อไฟล์", "weight": 6, "min_width": 260, "anchor": "w"},
            {"key": "size_bytes", "title": "ขนาด", "weight": 2, "min_width": 85, "anchor": "w", "format": lambda v, r: human_size(v)},
            {"key": "actions", "title": "จัดการ", "weight": 3, "min_width": 170, "anchor": "w", "widget": self._row_actions, "sticky": "w"},
        ], empty_text="ยังไม่มีไฟล์สำรอง — กด \"สำรองตอนนี้\"")
        self.table.pack(fill="both", expand=True, padx=24, pady=(0, 16))

    # ---------- โหลดข้อมูล ----------
    def on_open(self, **params) -> None:
        self.refresh()

    def refresh(self) -> None:
        backups = backup_service.list_backups()
        for i, b in enumerate(backups):
            b["id"] = i
        self.table.set_rows(backups)
        latest = fmt_datetime(backups[0]["created_at"]) if backups else "ยังไม่มี"
        self.header.set_subtitle(f"{len(backups)} ไฟล์ · สำรองล่าสุด {latest}")
        self._update_shop_label()

    def _restore_blockers(self) -> str | None:
        """เหตุที่ยังกู้คืนไม่ได้ (None = พร้อม)"""
        if shop_service.is_open():
            return "ร้านยังเปิดอยู่ — ปิดร้านก่อน"
        n = shop_service.active_session_count()
        if n > 0:
            return f"ยังมีโต๊ะค้าง {n} โต๊ะ — เคลียร์ที่หน้าโต๊ะก่อน"
        return None

    def _update_shop_label(self) -> None:
        reason = self._restore_blockers()
        if reason:
            self.shop_label.configure(text=f"สถานะการกู้คืน: ยังกู้คืนไม่ได้ ({reason})", text_color=COLORS["warning"])
        else:
            self.shop_label.configure(text="สถานะการกู้คืน: พร้อม (ร้านปิดและไม่มีโต๊ะค้าง)", text_color=COLORS["success"])

    def _kind_badge(self, parent, row: dict):
        return StatusBadge(parent, row["kind_th"], KIND_COLORS.get(row["kind"], COLORS["neutral"]))

    def _row_actions(self, parent, row: dict):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        ActionButton(box, "กู้คืน", lambda r=row: self.restore(r), "danger", height=30, width=70, size=13).pack(side="left", padx=2)
        ActionButton(box, "ลบไฟล์", lambda r=row: self.delete(r), "ghost", height=30, width=70, size=13).pack(side="left", padx=2)
        return box

    def _open_folder(self) -> None:
        if not open_folder(config.BACKUPS_DIR):
            self.toast(f"เปิดโฟลเดอร์ไม่ได้ — ไฟล์อยู่ที่ {config.BACKUPS_DIR}", "warning")

    # ---------- การกระทำ ----------
    def backup_now(self) -> None:
        ok, info = self.call(backup_service.create_backup, self.user_id)
        if ok:
            self.toast(f"สำรองแล้ว: {info['filename']} ({human_size(info['size_bytes'])})", "success")
            self.refresh()

    def delete(self, row: dict) -> None:
        if not confirm(self, f"ลบไฟล์สำรอง\n{row['filename']} ?\nลบแล้วเอากลับมาไม่ได้", title="ลบไฟล์สำรอง",
                       confirm_text="ลบไฟล์", danger=True):
            return
        ok, _ = self.call(backup_service.delete_backup, row["filename"], self.user_id, success="ลบไฟล์สำรองแล้ว")
        if ok:
            self.refresh()

    def restore(self, row: dict) -> None:
        reason = self._restore_blockers()
        if reason:
            self.toast(f"กู้คืนไม่ได้: {reason}", "error")
            self._update_shop_label()
            return
        if not confirm(
                self, f"กู้คืนข้อมูลจากไฟล์\n{row['filename']}\n(สร้างเมื่อ {fmt_datetime(row['created_at'])})\n\n"
                      "ข้อมูลปัจจุบันทั้งหมดจะถูกแทนที่ด้วยข้อมูลในไฟล์นี้ — ระบบจะสำรองข้อมูลปัจจุบันไว้ให้ก่อน",
                title="กู้คืนข้อมูล", confirm_text="ดำเนินการต่อ", danger=True):
            return
        typed = ask_text(self, f"เพื่อความปลอดภัย พิมพ์คำว่า {CONFIRM_WORD} เพื่อยืนยัน", title="ยืนยันการกู้คืน",
                         confirm_text="กู้คืนเดี๋ยวนี้", danger=True)
        if typed is None:
            return
        if typed != CONFIRM_WORD:
            self.toast(f"พิมพ์ไม่ตรง ({CONFIRM_WORD}) — ยกเลิกการกู้คืน", "error")
            return
        ok, result = self.call(backup_service.restore_backup, row["filename"], self.user_id)
        if not ok:
            self.refresh()
            return
        msg = (f"กู้คืนข้อมูลเรียบร้อย\nข้อมูลก่อนกู้คืนถูกสำรองไว้ที่ {result['filename']}\n"
               "ร้านถูกตั้งเป็น \"ปิด\" — ระบบจะพาไปหน้าล็อกอินใหม่ (ข้อมูลผู้ใช้อาจเปลี่ยน)\n"
               "แนะนำให้ปิดแล้วเปิดโปรแกรมอีกครั้ง (รวมเว็บมือถือถ้ารันแยก)")
        if result.get("active_sessions"):
            msg += f"\n\nมีโต๊ะค้างจากไฟล์สำรอง {result['active_sessions']} โต๊ะ — ให้พนักงานเคลียร์ที่หน้าโต๊ะ"
        show_info(self, msg, title="กู้คืนสำเร็จ")
        self.app.show_login()
