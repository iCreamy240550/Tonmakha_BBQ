"""ui/theme.py — สี ฟอนต์ Prompt และฟังก์ชันจัดรูปแบบข้อความที่ใช้ร่วมกันทุกหน้าของแอป PC

หมายเหตุ: `font()` / `font_family()` ต้องเรียกหลังสร้างหน้าต่างหลัก (CTk) แล้วเท่านั้น
"""
from __future__ import annotations

import ctypes
import shutil
import sys
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

import config

# ---------- สี ----------
COLORS = {
    "bg": "#f6f1ea",            # พื้นหลังหน้า (ครีมอุ่น)
    "card": "#ffffff",
    "card_border": "#e6dccd",
    "sidebar": "#2b2118",       # ถ่านไม้
    "sidebar_hover": "#44342a",
    "sidebar_active": "#e8590c",
    "sidebar_text": "#f3e9dc",
    "sidebar_muted": "#a89886",
    "primary": "#e8590c",       # ส้มถ่านร้อน
    "primary_hover": "#c94a07",
    "success": "#2f9e44",
    "success_hover": "#278a3a",
    "danger": "#e03131",
    "danger_hover": "#c02a2a",
    "warning": "#f08c00",
    "info": "#1c7ed6",
    "info_hover": "#1a6fbd",
    "neutral": "#868e96",
    "neutral_hover": "#6c747c",
    "text": "#2b2118",
    "text_muted": "#7a6d60",
    "text_on_dark": "#ffffff",
    "input_bg": "#ffffff",
    "input_border": "#d4c7b4",
    "row_alt": "#faf6f0",
    "row_hover": "#f1e8da",
    "alert_bg": "#c92a2a",
    "alert_text": "#ffffff",
}

# สีตามสถานะโต๊ะ/รอบ (คีย์ = ค่าสถานะในฐานข้อมูล + 'free')
STATUS_COLORS = {
    config.TABLE_STATUS_FREE: "#868e96",
    config.SESSION_PENDING: "#f08c00",
    config.SESSION_OPEN: "#2f9e44",
    config.SESSION_AWAITING_PAYMENT: "#1c7ed6",
    config.SESSION_CLOSED: "#495057",
    config.SESSION_CANCELLED: "#e03131",
}

# สีตามสถานะออเดอร์
ORDER_STATUS_COLORS = {
    "new": "#e03131",
    "preparing": "#f08c00",
    "served": "#2f9e44",
    "cancelled": "#868e96",
}

PRIMARY_FONT_FAMILY = "Prompt"

# ฟอนต์ที่รองรับภาษาไทย เรียงตามความต้องการ (Prompt เป็นฟอนต์หลักอันดับแรกของระบบ)
_FONT_CANDIDATES = [
    "Prompt",
    "Leelawadee UI", "Tahoma", "Sarabun", "TH Sarabun New", "Noto Sans Thai",
    "Noto Sans Thai UI", "Loma", "Garuda", "Segoe UI",
]

_family: str | None = None
_font_cache: dict[tuple, ctk.CTkFont] = {}
_fonts_registered: bool = False


def register_local_fonts() -> None:
    """ลงทะเบียนไฟล์ฟอนต์ Prompt จากโฟลเดอร์ assets/fonts/ เข้าสู่ระบบปฏิบัติการและ CustomTkinter"""
    global _fonts_registered
    if _fonts_registered:
        return
    _fonts_registered = True
    font_files = [
        config.FONTS_DIR / "Prompt-Regular.ttf",
        config.FONTS_DIR / "Prompt-Bold.ttf",
    ]
    existing = [p for p in font_files if p.exists() and p.is_file()]
    if not existing:
        return

    # 1) หากมี FontManager ของ CustomTkinter ให้โหลดเข้าโปรเซส
    try:
        from customtkinter.windows.widgets.font import FontManager
        for p in existing:
            FontManager.load_font(str(p))
    except Exception:
        pass

    # 2) บน Windows ใช้ AddFontResourceExW (FR_PRIVATE = 0x10)
    if sys.platform.startswith("win"):
        try:
            gdi32 = ctypes.windll.gdi32
            for p in existing:
                gdi32.AddFontResourceExW(str(p), 0x10, 0)
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        # บน Linux คัดลอกไว้ใน ~/.local/share/fonts เพื่อให้ fontconfig มองเห็นโดยไม่ต้องใช้สิทธิ์ root
        try:
            user_font_dir = Path.home() / ".local" / "share" / "fonts"
            user_font_dir.mkdir(parents=True, exist_ok=True)
            for p in existing:
                dst = user_font_dir / p.name
                if not dst.exists():
                    shutil.copy2(p, dst)
        except Exception:
            pass


def init_theme() -> None:
    """ตั้งโหมดสีและลงทะเบียนฟอนต์ Prompt ของ customtkinter (เรียกก่อนสร้าง CTk)"""
    register_local_fonts()
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")


def font_family() -> str:
    """ชื่อฟอนต์หลักของแอปพลิเคชัน ('Prompt')"""
    global _family
    if _family is None:
        register_local_fonts()
        try:
            installed = {f.lower(): f for f in tkfont.families()}
            if PRIMARY_FONT_FAMILY.lower() in installed:
                _family = installed[PRIMARY_FONT_FAMILY.lower()]
            elif (config.FONTS_DIR / "Prompt-Regular.ttf").exists():
                _family = PRIMARY_FONT_FAMILY
            else:
                _family = next(
                    (installed[n.lower()] for n in _FONT_CANDIDATES if n.lower() in installed),
                    PRIMARY_FONT_FAMILY,
                )
        except Exception:
            _family = PRIMARY_FONT_FAMILY
    return _family


def font(size: int = 14, bold: bool = False) -> ctk.CTkFont:
    """CTkFont ตามขนาดโดยใช้ฟอนต์ Prompt (ใช้ซ้ำจาก cache)"""
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ctk.CTkFont(family=font_family(), size=size,
                                       weight="bold" if bold else "normal")
    return _font_cache[key]


# ---------- จัดรูปแบบข้อความ ----------
def money(value: float | int | None) -> str:
    """1234.5 -> '1,234.50' (เสมอ 2 ตำแหน่ง)"""
    return f"{float(value or 0):,.2f}"


def baht(value: float | int | None) -> str:
    """1234.5 -> '1,234.50 บาท'"""
    return f"{money(value)} บาท"


def weight_text(grams: int | float | None) -> str:
    """น้ำหนักกรัม -> ข้อความ เช่น 1500 -> '1.5 กก. (15 ขีด)', 300 -> '3 ขีด'"""
    g = float(grams or 0)
    kheed = g / (config.GRAMS_PER_KG / config.KHEED_PER_KG)
    kheed_txt = f"{kheed:g}"
    if g >= config.GRAMS_PER_KG:
        return f"{g / config.GRAMS_PER_KG:g} กก. ({kheed_txt} ขีด)"
    return f"{kheed_txt} ขีด"


def _parse(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def fmt_time(text: str | None) -> str:
    """'2026-10-10 18:05:30' -> '18:05'"""
    dt = _parse(text)
    return dt.strftime("%H:%M") if dt else "-"


def fmt_datetime(text: str | None) -> str:
    """'2026-10-10 18:05:30' -> '10/10/2026 18:05'"""
    dt = _parse(text)
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "-"


def minutes_since(text: str | None, now: datetime | None = None) -> int:
    """จำนวนนาทีเต็มตั้งแต่เวลา text (0 ถ้าแปลงไม่ได้)"""
    dt = _parse(text)
    if dt is None:
        return 0
    return max(0, int(((now or datetime.now()) - dt).total_seconds() // 60))


def duration_text(text: str | None, now: datetime | None = None) -> str:
    """นานเท่าไรแล้ว เช่น '5 นาที', '1 ชม. 20 นาที'"""
    m = minutes_since(text, now)
    if m < 60:
        return f"{m} นาที"
    return f"{m // 60} ชม. {m % 60} นาที"


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status, COLORS["neutral"])


def status_text(status: str) -> str:
    return config.SESSION_STATUS_TH.get(status, status)
