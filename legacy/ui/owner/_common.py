"""ui/owner/_common.py — ตัวช่วยที่หน้าเจ้าของใช้ร่วมกัน (รวมปุ่มเลือกวันที่จากปฏิทิน พ.ศ.)

- `OwnerPage(BasePage)` : คลาสแม่ของหน้าเจ้าของ — กันพนักงานอีกชั้น (นอกจาก App.navigate) แล้วเรียก `on_open(**params)`
- `parse_number / parse_int / parse_percent / parse_date` : แปลงข้อความจากช่องกรอก -> ตัวเลข/วันที่ (ผิด = ValueError ไทย)
- `ThaiDatePickerDialog` / `DatePickerField` : ตัวเลือกวันที่แบบปฏิทินที่สามารถเลือกปี พ.ศ. เดือน และวันที่ได้โดยไม่ต้องพิมพ์เอง
- `open_folder(path)` : เปิดโฟลเดอร์ในโปรแกรมจัดการไฟล์ของระบบ (Windows/macOS/Linux)
- `LabeledMenu` / `bar(...)` : ชิ้นส่วนฟอร์มและกราฟแท่งสัดส่วน
"""
from __future__ import annotations

import calendar
import os
import socket
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import customtkinter as ctk

from services import auth_service
from ui.theme import COLORS, font
from ui.widgets import ActionButton, BaseDialog, BasePage

THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]
THAI_MONTHS_SHORT = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]
THAI_WEEKDAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]


def ce_to_be_year(ce_year: int) -> int:
    """แปลงปี ค.ศ. -> พ.ศ. (ป้องกันการบวก 543 ซ้ำหากค่าเป็น พ.ศ. อยู่แล้ว)"""
    y = int(ce_year)
    return y if y >= 2400 else y + 543


def be_to_ce_year(be_or_ce_year: int) -> int:
    """แปลงปี พ.ศ. -> ค.ศ. สำหรับค้นหาในฐานข้อมูล (หากเป็น ค.ศ. อยู่แล้วจะไม่ลบซ้ำ)"""
    y = int(be_or_ce_year)
    return y - 543 if y >= 2400 else y


def format_thai_date(iso_date: str | date | None, short_month: bool = False) -> str:
    """แปลง 'YYYY-MM-DD' (ค.ศ.) เป็นข้อความวันที่ภาษาไทย พ.ศ. เช่น '24 ตุลาคม 2569 (24/10/2569)'"""
    if not iso_date:
        return "เลือกวันที่..."
    if isinstance(iso_date, date):
        d = iso_date
    else:
        try:
            d = datetime.strptime(str(iso_date).strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            return str(iso_date)
    be_y = ce_to_be_year(d.year)
    m_name = THAI_MONTHS_SHORT[d.month - 1] if short_month else THAI_MONTHS[d.month - 1]
    return f"{d.day:02d}/{d.month:02d}/{be_y} ({d.day} {m_name} {be_y})"


class OwnerPage(BasePage):
    """หน้าของเจ้าของร้าน: ถ้าผู้ใช้ไม่ใช่เจ้าของ จะไม่โหลดข้อมูลและพากลับหน้าโต๊ะ
    หน้าลูกเขียน `on_open(**params)` แทน `on_show` (ค่าเริ่มต้นเรียก `refresh()`)"""

    def is_allowed(self) -> bool:
        return auth_service.is_owner(self.app.user)

    def on_show(self, **params) -> None:
        if not self.is_allowed():
            self.toast("หน้านี้สำหรับเจ้าของร้านเท่านั้น", "error")
            self.after(50, lambda: self.app.navigate("tables"))
            return
        self.on_open(**params)

    def on_open(self, **params) -> None:
        self.refresh()

    def reload(self) -> None:           # แจ้งเตือนเปลี่ยน -> โหลดใหม่ เฉพาะเมื่อเป็นเจ้าของ
        if self.is_allowed():
            super().reload()

    def _schedule(self) -> None:        # ไม่ตั้งรีเฟรชอัตโนมัติถ้าไม่ใช่เจ้าของ
        if self.is_allowed():
            super()._schedule()


# ---------------------------------------------------------------- แปลงค่าจากช่องกรอก

def parse_number(text: str, label: str, minimum: float | None = None, maximum: float | None = None,
                 allow_empty: bool = False, default: float = 0.0) -> float:
    """'1,250.50' -> 1250.5 ; ว่าง + allow_empty -> default ; ผิด -> ValueError(ข้อความไทย)"""
    t = (text or "").strip().replace(",", "")
    if not t:
        if allow_empty:
            return default
        raise ValueError(f"กรุณากรอก{label}")
    try:
        value = float(t)
    except ValueError:
        raise ValueError(f"{label}ต้องเป็นตัวเลข") from None
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{label}ไม่ถูกต้อง")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label}ต้องไม่น้อยกว่า {minimum:g}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}ต้องไม่เกิน {maximum:g}")
    return value


def parse_int(text: str, label: str, minimum: int | None = None, maximum: int | None = None) -> int:
    """จำนวนเต็ม ('12' หรือ '12.0' ได้ ; '12.5' ไม่ได้)"""
    value = parse_number(text, label)
    if value != int(value):
        raise ValueError(f"{label}ต้องเป็นจำนวนเต็ม")
    value = int(value)
    if minimum is not None and value < minimum:
        raise ValueError(f"{label}ต้องไม่น้อยกว่า {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}ต้องไม่เกิน {maximum}")
    return value


def parse_percent(text: str, label: str) -> float:
    return parse_number(text, label, minimum=0, maximum=100)


def parse_date(text: str, label: str, allow_empty: bool = True) -> str:
    """รองรับทั้ง 'YYYY-MM-DD' (ค.ศ. หรือ พ.ศ.) และ 'DD/MM/YYYY' (ค.ศ. หรือ พ.ศ.) -> คืนค่า 'YYYY-MM-DD' (ค.ศ.) เสมอ
    ว่าง -> '' (ถ้า allow_empty) ; รูปแบบผิด -> ValueError"""
    t = (text or "").strip()
    if not t:
        if allow_empty:
            return ""
        raise ValueError(f"กรุณาเลือก{label}")
    # ตัดส่วนวงเล็บแสดงผล เช่น '24/10/2569 (24 ตุลาคม 2569)'
    if "(" in t:
        t = t.split("(", 1)[0].strip()

    for sep, order in (("-", "ymd"), ("/", "dmy"), ("/", "ymd")):
        if sep in t:
            parts = t.split(sep)
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                try:
                    if order == "ymd" and len(parts[0]) == 4:
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    elif order == "dmy" and len(parts[2]) == 4:
                        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    else:
                        continue
                    ce_y = be_to_ce_year(y)
                    return date(ce_y, m, d).isoformat()
                except ValueError:
                    raise ValueError(f"{label}ไม่ถูกต้อง") from None
    raise ValueError(f"{label}ไม่ถูกต้อง (กรุณาเลือกวันที่จากปฏิทิน)")


def fmt_qty(value: float | int | None) -> str:
    """ปริมาณสต๊อก: 12.0 -> '12', 3.250 -> '3.25'"""
    return f"{float(value or 0):,.3f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- ปฏิทินเลือกวันที่ (พ.ศ. / เดือน / วันที่)

class ThaiDatePickerDialog(BaseDialog):
    """หน้าต่างปฏิทินให้ผู้ใช้เลือกปี พ.ศ., เดือน และวันที่ -> คืนค่า ISO 'YYYY-MM-DD' (ค.ศ.)"""
    def __init__(self, parent, initial_iso: str | None = None, title: str = "เลือกวันที่"):
        super().__init__(parent, title, width=400)
        today = date.today()
        init_date = today
        if initial_iso:
            try:
                parsed = parse_date(initial_iso, "วันที่", allow_empty=True)
                if parsed:
                    init_date = datetime.strptime(parsed, "%Y-%m-%d").date()
            except ValueError:
                init_date = today

        self.selected_date: date = init_date
        self.view_ce_year: int = init_date.year
        self.view_month: int = init_date.month

        # ช่วงปี พ.ศ. ให้เลือกสะดวก (ย้อนหลัง 10 ปี ถึงล่วงหน้า 5 ปี)
        min_ce = min(today.year - 10, self.view_ce_year - 2)
        max_ce = max(today.year + 5, self.view_ce_year + 2)
        self._year_options = [f"พ.ศ. {ce_to_be_year(y)}" for y in range(max_ce, min_ce - 1, -1)]
        self._year_map = {f"พ.ศ. {ce_to_be_year(y)}": y for y in range(max_ce, min_ce - 1, -1)}

        # แถบเลือกเดือนและปี พ.ศ.
        nav = ctk.CTkFrame(self.body, fg_color="transparent")
        nav.pack(fill="x", pady=(0, 8))
        ActionButton(nav, "◀", self._prev_month, "ghost", height=34, width=36, size=14).pack(side="left")

        self.month_menu = ctk.CTkOptionMenu(
            nav,
            values=THAI_MONTHS,
            width=135,
            height=34,
            font=font(14, True),
            dropdown_font=font(14),
            command=self._on_month_selected,
        )
        self.month_menu.set(THAI_MONTHS[self.view_month - 1])
        self.month_menu.pack(side="left", padx=6)

        self.year_menu = ctk.CTkOptionMenu(
            nav,
            values=self._year_options,
            width=120,
            height=34,
            font=font(14, True),
            dropdown_font=font(14),
            command=self._on_year_selected,
        )
        self.year_menu.set(f"พ.ศ. {ce_to_be_year(self.view_ce_year)}")
        self.year_menu.pack(side="left", padx=(0, 6))

        ActionButton(nav, "▶", self._next_month, "ghost", height=34, width=36, size=14).pack(side="right")

        # หัวตารางวันในสัปดาห์ (จ. - อา.)
        wk_frame = ctk.CTkFrame(self.body, fg_color=COLORS["sidebar"], corner_radius=6)
        wk_frame.pack(fill="x", pady=(0, 4))
        for i, wd in enumerate(THAI_WEEKDAYS):
            wk_frame.grid_columnconfigure(i, weight=1, uniform="wd")
            ctk.CTkLabel(
                wk_frame, text=wd, font=font(13, True),
                text_color=COLORS["sidebar_text"], anchor="center"
            ).grid(row=0, column=i, padx=2, pady=4, sticky="ew")

        # ตารางวันที่
        self.days_frame = ctk.CTkFrame(self.body, fg_color=COLORS["row_alt"], corner_radius=8)
        self.days_frame.pack(fill="x", pady=(0, 8))
        for i in range(7):
            self.days_frame.grid_columnconfigure(i, weight=1, uniform="cal_d")

        # แถบลัดและแสดงวันที่ที่เลือก
        foot_info = ctk.CTkFrame(self.body, fg_color="transparent")
        foot_info.pack(fill="x")
        self.selected_label = ctk.CTkLabel(
            foot_info, text="", font=font(14, True), text_color=COLORS["primary"], anchor="w"
        )
        self.selected_label.pack(side="left")
        ActionButton(foot_info, "วันนี้", self._pick_today, "ghost", height=28, width=68, size=12).pack(side="right")

        self.add_buttons("ตกลง", "ยกเลิก", on_confirm=lambda: self.close(self.selected_date.isoformat()))
        self._render_calendar()

    def _sync_menus(self) -> None:
        self.month_menu.set(THAI_MONTHS[self.view_month - 1])
        be_label = f"พ.ศ. {ce_to_be_year(self.view_ce_year)}"
        if be_label not in self._year_map:
            self._year_map[be_label] = self.view_ce_year
            self._year_options.append(be_label)
            self.year_menu.configure(values=self._year_options)
        self.year_menu.set(be_label)

    def _prev_month(self) -> None:
        if self.view_month == 1:
            self.view_month = 12
            self.view_ce_year -= 1
        else:
            self.view_month -= 1
        self._sync_menus()
        self._render_calendar()

    def _next_month(self) -> None:
        if self.view_month == 12:
            self.view_month = 1
            self.view_ce_year += 1
        else:
            self.view_month += 1
        self._sync_menus()
        self._render_calendar()

    def _on_month_selected(self, month_th: str) -> None:
        if month_th in THAI_MONTHS:
            self.view_month = THAI_MONTHS.index(month_th) + 1
            self._render_calendar()

    def _on_year_selected(self, year_label: str) -> None:
        ce_y = self._year_map.get(year_label)
        if ce_y is None:
            digits = "".join(ch for ch in year_label if ch.isdigit())
            if digits:
                ce_y = be_to_ce_year(int(digits))
        if ce_y:
            self.view_ce_year = ce_y
            self._render_calendar()

    def _pick_today(self) -> None:
        t = date.today()
        self.selected_date = t
        self.view_ce_year = t.year
        self.view_month = t.month
        self._sync_menus()
        self._render_calendar()

    def _pick_day(self, day_num: int) -> None:
        self.selected_date = date(self.view_ce_year, self.view_month, day_num)
        self.close(self.selected_date.isoformat())

    def _render_calendar(self) -> None:
        for child in self.days_frame.winfo_children():
            child.destroy()
        cal = calendar.Calendar(firstweekday=0)  # วันจันทร์เป็นวันแรก
        weeks = cal.monthdayscalendar(self.view_ce_year, self.view_month)
        today = date.today()

        for r_idx, week in enumerate(weeks):
            for c_idx, day_num in enumerate(week):
                if day_num == 0:
                    ctk.CTkLabel(self.days_frame, text="", height=34).grid(row=r_idx, column=c_idx, padx=2, pady=2)
                    continue
                cur_d = date(self.view_ce_year, self.view_month, day_num)
                is_sel = cur_d == self.selected_date
                is_today = cur_d == today
                fg = COLORS["primary"] if is_sel else ("#efe6d8" if is_today else COLORS["card"])
                txt_col = "#ffffff" if is_sel else (COLORS["primary"] if is_today else COLORS["text"])
                hover = COLORS["primary_hover"] if is_sel else COLORS["row_hover"]
                btn = ctk.CTkButton(
                    self.days_frame,
                    text=str(day_num),
                    width=42,
                    height=34,
                    corner_radius=6,
                    font=font(14, is_sel or is_today),
                    fg_color=fg,
                    hover_color=hover,
                    text_color=txt_col,
                    command=lambda d=day_num: self._pick_day(d),
                )
                btn.grid(row=r_idx, column=c_idx, padx=2, pady=2, sticky="nsew")

        self.selected_label.configure(text=f"เลือก: {format_thai_date(self.selected_date, short_month=True)}")


class DatePickerField(ctk.CTkFrame):
    """ช่องเลือกวันที่จากปฏิทิน (แสดงปี พ.ศ. เดือน และวันที่ชัดเจน กดเพื่อเปิดปฏิทิน ไม่ต้องพิมพ์เอง)
    - `.get()` คืนค่า ISO 'YYYY-MM-DD' (ค.ศ.) สำหรับส่งให้ report_service / database
    - `.get_thai_text()` คืนข้อความวันที่ พ.ศ. ที่แสดงบนปุ่ม
    - `.set(iso_or_date)` ตั้งค่าวันที่ใหม่"""
    def __init__(self, master, label: str, initial_iso: str | None = None,
                 width: int = 210, on_change=None, allow_empty: bool = False):
        super().__init__(master, fg_color="transparent")
        self.label_text = label
        self.on_change = on_change
        self.allow_empty = allow_empty
        self._iso_value: str = ""
        ctk.CTkLabel(self, text=label, font=font(14), text_color=COLORS["text_muted"]).pack(anchor="w")

        self.button = ctk.CTkButton(
            self,
            text="",
            width=width,
            height=42,
            anchor="w",
            font=font(15, True),
            fg_color=COLORS["input_bg"],
            hover_color=COLORS["row_hover"],
            text_color=COLORS["text"],
            border_width=1,
            border_color=COLORS["input_border"],
            corner_radius=8,
            command=self.open_picker,
        )
        self.button.pack(fill="x", pady=(2, 0))
        if initial_iso:
            self.set(initial_iso, notify=False)
        elif not allow_empty:
            self.set(date.today().isoformat(), notify=False)
        else:
            self._update_display()

    def _update_display(self) -> None:
        if not self._iso_value:
            self.button.configure(text="📅 เลือกวันที่ (พ.ศ.)", text_color=COLORS["text_muted"])
        else:
            self.button.configure(
                text=f"📅 {format_thai_date(self._iso_value, short_month=True)}",
                text_color=COLORS["text"],
            )

    def open_picker(self) -> None:
        dlg = ThaiDatePickerDialog(self, initial_iso=self._iso_value or date.today().isoformat(),
                                   title=f"เลือก{self.label_text}")
        chosen = dlg.show()
        if chosen:
            self.set(chosen, notify=True)

    def get(self) -> str:
        """คืนค่าวันที่รูปแบบ 'YYYY-MM-DD' (ค.ศ.) สำหรับใช้กรองฐานข้อมูล"""
        return self._iso_value

    def get_thai_text(self) -> str:
        """คืนข้อความวันที่รูปแบบ พ.ศ. ที่แสดงให้ผู้ใช้เห็น"""
        return format_thai_date(self._iso_value, short_month=False) if self._iso_value else ""

    def set(self, value: str | date | None, notify: bool = False) -> None:
        if value is None or str(value).strip() == "":
            self._iso_value = "" if self.allow_empty else date.today().isoformat()
        elif isinstance(value, date):
            self._iso_value = value.isoformat()
        else:
            self._iso_value = parse_date(str(value), self.label_text, allow_empty=self.allow_empty)
        self._update_display()
        if notify and self.on_change:
            self.on_change(self._iso_value)

    def clear(self) -> None:
        self.set("" if self.allow_empty else date.today().isoformat(), notify=False)


# ---------------------------------------------------------------- ระบบไฟล์

def open_folder(path) -> bool:
    """เปิดโฟลเดอร์ (สร้างให้ถ้ายังไม่มี) -> True ถ้าสั่งเปิดได้"""
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(p))                      # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return True
    except Exception:  # noqa: BLE001 — เปิดไม่ได้ไม่ใช่ปัญหาร้ายแรง
        return False


def detect_lan_ip() -> str | None:
    """IP ของเครื่องนี้ในเครือข่ายภายใน (เช่น 192.168.1.50) หรือ None ถ้าหาไม่ได้ — ไม่ส่งข้อมูลออกเครือข่ายจริง"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))     # UDP ไม่ส่งแพ็กเก็ต แค่ให้ระบบเลือกการ์ดเครือข่าย
            ip = sock.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("ไบต์", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.0f} {unit}" if unit == "ไบต์" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{num_bytes} ไบต์"


# ---------------------------------------------------------------- ชิ้นส่วนฟอร์ม

class LabeledMenu(ctk.CTkFrame):
    """ป้ายชื่อ + เมนูเลือก (CTkOptionMenu) ; `.get()` = ข้อความที่เลือก, `.set(v)`, `.configure_values(list)`"""
    def __init__(self, master, label: str, values: list[str], width: int = 220, command=None):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=label, font=font(14), text_color=COLORS["text_muted"]).pack(anchor="w")
        self.menu = ctk.CTkOptionMenu(self, values=list(values) or [""], width=width, height=40, font=font(15),
                                      dropdown_font=font(14), command=command)
        self.menu.pack(fill="x", pady=(2, 0))

    def get(self) -> str:
        return self.menu.get()

    def set(self, value: str) -> None:
        self.menu.set(value)

    def configure_values(self, values: list[str]) -> None:
        self.menu.configure(values=list(values) or [""])


def bar(master, fraction: float, color: str = COLORS["primary"], width: int = 140, height: int = 12):
    """แท่งสัดส่วน 0..1"""
    pb = ctk.CTkProgressBar(master, width=width, height=height, progress_color=color,
                            fg_color=COLORS["row_hover"], corner_radius=6)
    pb.set(max(0.0, min(1.0, float(fraction))))
    return pb
