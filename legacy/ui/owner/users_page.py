"""ui/owner/users_page.py — จัดการผู้ใช้ (เจ้าของ)

เพิ่มพนักงาน/เจ้าของ, แก้ชื่อที่แสดง/สิทธิ์, รีเซ็ตรหัสผ่าน, เปิด-ปิดบัญชี ; ไม่มีลบ (log อ้างอิงผู้ใช้อยู่)
- การจัดแนวตาราง: ทุกคอลัมน์ชิดซ้าย ยกเว้นคอลัมน์ "สถานะ" จัดกึ่งกลางตามข้อกำหนดใน PDF
"""
from __future__ import annotations

import customtkinter as ctk

import config
from services import auth_service
from ui.owner._common import LabeledMenu, OwnerPage
from ui.theme import COLORS, fmt_datetime, font
from ui.widgets import ActionButton, BaseDialog, DataTable, LabeledEntry, PageHeader, StatusBadge, confirm

ROLE_LABELS = {config.ROLE_STAFF: "พนักงาน", config.ROLE_OWNER: "เจ้าของร้าน"}


class UserDialog(BaseDialog):
    """เพิ่ม/แก้ผู้ใช้
    เพิ่ม -> result = dict(username, display_name, role, password) ; แก้ -> dict(display_name, role)"""
    def __init__(self, parent, user: dict | None = None, lock_role: bool = False):
        super().__init__(parent, "แก้ไขผู้ใช้" if user else "เพิ่มผู้ใช้", width=440)
        self.user = user
        self.username = LabeledEntry(self.body, "ชื่อผู้ใช้ (สำหรับล็อกอิน)", placeholder="เช่น staff2")
        self.username.pack(fill="x")
        self.display = LabeledEntry(self.body, "ชื่อที่แสดง", placeholder="เช่น น้องมะค่า")
        self.display.pack(fill="x", pady=(8, 0))
        self.role = LabeledMenu(self.body, "สิทธิ์", list(ROLE_LABELS.values()))
        self.role.pack(fill="x", pady=(8, 0))
        if user is None:
            self.password = LabeledEntry(self.body, f"รหัสผ่าน (อย่างน้อย {config.MIN_PASSWORD_LENGTH} ตัว)", show="*")
            self.password.pack(fill="x", pady=(8, 0))
            self.password2 = LabeledEntry(self.body, "ยืนยันรหัสผ่าน", show="*")
            self.password2.pack(fill="x", pady=(8, 0))
        else:
            self.username.set(user["username"])
            self.username.entry.configure(state="disabled")
            self.display.set(user["display_name"])
            self.role.set(ROLE_LABELS[user["role"]])
            if lock_role:
                self.role.menu.configure(state="disabled")
        self.error = ctk.CTkLabel(self.body, text="", font=font(13), text_color=COLORS["danger"], wraplength=390,
                                  justify="left")
        self.error.pack(anchor="w", pady=(6, 0))
        self.add_buttons("บันทึก", "ยกเลิก", on_confirm=self._submit)

    def _role_key(self) -> str:
        return next(k for k, v in ROLE_LABELS.items() if v == self.role.get())

    def _submit(self) -> None:
        display = self.display.get()
        if self.user is not None:
            self.close({"display_name": display, "role": self._role_key()})
            return
        username = self.username.get()
        if not username:
            self.error.configure(text="กรุณากรอกชื่อผู้ใช้")
            return
        pw, pw2 = self.password.entry.get(), self.password2.entry.get()
        if pw != pw2:
            self.error.configure(text="รหัสผ่านทั้งสองช่องไม่ตรงกัน")
            return
        self.close({"username": username, "display_name": display or username, "role": self._role_key(), "password": pw})


class PasswordDialog(BaseDialog):
    """ตั้งรหัสผ่านใหม่ -> result = str"""
    def __init__(self, parent, username: str):
        super().__init__(parent, "รีเซ็ตรหัสผ่าน", width=420)
        ctk.CTkLabel(self.body, text=f"ตั้งรหัสผ่านใหม่ให้ {username}", font=font(16, True),
                     text_color=COLORS["text"]).pack(anchor="w")
        self.pw = LabeledEntry(self.body, f"รหัสผ่านใหม่ (อย่างน้อย {config.MIN_PASSWORD_LENGTH} ตัว)", show="*")
        self.pw.pack(fill="x", pady=(8, 0))
        self.pw2 = LabeledEntry(self.body, "ยืนยันรหัสผ่านใหม่", show="*")
        self.pw2.pack(fill="x", pady=(8, 0))
        self.error = ctk.CTkLabel(self.body, text="", font=font(13), text_color=COLORS["danger"])
        self.error.pack(anchor="w", pady=(6, 0))
        self.add_buttons("เปลี่ยนรหัสผ่าน", "ยกเลิก", on_confirm=self._submit)

    def _submit(self) -> None:
        a, b = self.pw.entry.get(), self.pw2.entry.get()
        if a != b:
            self.error.configure(text="รหัสผ่านทั้งสองช่องไม่ตรงกัน")
            return
        self.close(a)


class Page(OwnerPage):
    title = "ผู้ใช้"

    def build(self) -> None:
        header = PageHeader(self, "ผู้ใช้", "")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        ActionButton(header.right, "+ เพิ่มผู้ใช้", self.add_user, "primary", height=38, width=120).pack(side="right")
        self.table = DataTable(self, columns=[
            {"key": "username", "title": "ชื่อผู้ใช้", "weight": 3, "min_width": 120, "anchor": "w"},
            {"key": "display_name", "title": "ชื่อที่แสดง", "weight": 3, "min_width": 120, "anchor": "w"},
            {"key": "role", "title": "สิทธิ์", "weight": 2, "min_width": 90, "anchor": "w", "format": lambda v, r: ROLE_LABELS.get(v, v)},
            {"key": "status", "title": "สถานะ", "weight": 2, "min_width": 95, "anchor": "center",
             "widget": self._status_badge, "sticky": ""},
            {"key": "created_at", "title": "สร้างเมื่อ", "weight": 3, "min_width": 120, "anchor": "w", "format": lambda v, r: fmt_datetime(v)},
            {"key": "actions", "title": "จัดการ", "weight": 5, "min_width": 270, "anchor": "w",
             "widget": self._row_actions, "sticky": "w"},
        ], empty_text="ยังไม่มีผู้ใช้")
        self.table.pack(fill="both", expand=True, padx=24, pady=(0, 16))

    def on_open(self, **params) -> None:
        self.refresh()

    def refresh(self) -> None:
        users = auth_service.list_users(include_inactive=True)
        self.table.set_rows(users)
        active = sum(1 for u in users if u["active"])
        self.header.set_subtitle(f"{len(users)} บัญชี (ใช้งาน {active})")

    def _is_me(self, row: dict) -> bool:
        return row["id"] == self.user_id

    def _status_badge(self, parent, row: dict):
        text = ("ใช้งาน (คุณ)" if self._is_me(row) else "ใช้งาน") if row["active"] else "ปิดบัญชี"
        return StatusBadge(parent, text, COLORS["success"] if row["active"] else COLORS["neutral"])

    def _row_actions(self, parent, row: dict):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        ActionButton(box, "แก้ไข", lambda r=row: self.edit_user(r), "info", height=30, width=64, size=13).pack(side="left", padx=2)
        ActionButton(box, "รีเซ็ตรหัส", lambda r=row: self.reset_password(r), "ghost", height=30, width=88, size=13).pack(side="left", padx=2)
        ActionButton(box, "เปิดบัญชี" if not row["active"] else "ปิดบัญชี", lambda r=row: self.toggle_active(r),
                     "success" if not row["active"] else "ghost", height=30, width=84, size=13).pack(side="left", padx=2)
        return box

    # ---------- การกระทำ ----------
    def add_user(self) -> None:
        d = UserDialog(self).show()
        if not d:
            return
        ok, _ = self.call(auth_service.create_user, d["username"], d["password"], d["display_name"], d["role"],
                          by_user_id=self.user_id, success=f"เพิ่มผู้ใช้ {d['username']} แล้ว")
        if ok:
            self.refresh()

    def edit_user(self, row: dict) -> None:
        d = UserDialog(self, user=row, lock_role=self._is_me(row)).show()
        if not d:
            return
        if self._is_me(row) and d["role"] != row["role"]:
            self.toast("ลดสิทธิ์บัญชีที่กำลังล็อกอินอยู่ไม่ได้", "error")
            return
        ok, _ = self.call(auth_service.update_user, row["id"], display_name=d["display_name"], role=d["role"],
                          by_user_id=self.user_id, success="บันทึกแล้ว")
        if ok:
            self.refresh()

    def reset_password(self, row: dict) -> None:
        pw = PasswordDialog(self, row["username"]).show()
        if pw is None:
            return
        ok, _ = self.call(auth_service.change_password, row["id"], pw, by_user_id=self.user_id,
                          success=f"เปลี่ยนรหัสผ่านของ {row['username']} แล้ว")

    def toggle_active(self, row: dict) -> None:
        if row["active"]:
            if self._is_me(row):
                self.toast("ปิดบัญชีที่กำลังล็อกอินอยู่ไม่ได้", "error")
                return
            if not confirm(self, f"ปิดบัญชี {row['username']} ?\nผู้ใช้นี้จะล็อกอินไม่ได้ (ประวัติเดิมยังอยู่)",
                           title="ปิดบัญชีผู้ใช้", confirm_text="ปิดบัญชี", danger=True):
                return
        ok, _ = self.call(auth_service.update_user, row["id"], active=not row["active"], by_user_id=self.user_id,
                          success="ปิดบัญชีแล้ว" if row["active"] else "เปิดบัญชีแล้ว")
        if ok:
            self.refresh()
