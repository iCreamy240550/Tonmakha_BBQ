"""ui/owner/settings_page.py — ตั้งค่าร้าน (เจ้าของ)

ค่าทั้งหมดเก็บในตาราง settings ผ่าน `settings_service.set_many` (log การเปลี่ยนค่าให้เอง)
- ข้อมูลร้านสำหรับแสดงบนใบเสร็จรับเงิน: ชื่อร้าน, เลขประจำตัวผู้เสียภาษี + สวิตช์เปิด/ปิดการแสดงเลขผู้เสียภาษีบนใบเสร็จ,
  ที่อยู่ร้าน, ตำบล, อำเภอ, จังหวัด, รหัสไปรษณีย์, เบอร์โทรศัพท์ร้าน
- ลิงก์เว็บลูกค้า (public_base_url): ฐานของลิงก์ใน QR ; เปลี่ยนแล้วต้องสร้าง/พิมพ์ QR ใหม่
- แจ้งเตือนโต๊ะเงียบและเกณฑ์สต๊อกใกล้หมดเริ่มต้น (ค่าเริ่มต้น 5 หน่วย แก้ไขได้)
- อัตราราคาหมูกระทะชั่งกิโล (ค่าเริ่มต้น 299 บาท/กก.) และข้อมูลรับชำระด้วย PromptPay (หมายเลขและชื่อบัญชี)
- ค่าบริการ (%) และ ภาษีมูลค่าเพิ่ม (%) เปิด/ปิดได้ — มีผลกับบิลที่เช็คเอาท์ครั้งต่อไป (บิลเก่าไม่เปลี่ยน)
ปุ่มบันทึกจะตรวจทุกช่องก่อน ถ้าผิดช่องใดจะไม่บันทึกอะไรเลย
"""
from __future__ import annotations

from urllib.parse import urlparse

import customtkinter as ctk

import config
from services import qr_service, settings_service
from ui.owner._common import OwnerPage, detect_lan_ip, fmt_qty, parse_int, parse_number, parse_percent
from ui.theme import COLORS, font
from ui.widgets import ActionButton, Card, LabeledEntry, PageHeader, show_info

MAX_MINUTES = 1440


def normalize_base_url(text: str) -> str:
    """'http://192.168.1.50:8080/' -> 'http://192.168.1.50:8080' ; ผิดรูปแบบ -> ValueError"""
    t = (text or "").strip().rstrip("/")
    if not t:
        raise ValueError("กรุณากรอกลิงก์เว็บลูกค้า")
    parsed = urlparse(t)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("ลิงก์ต้องขึ้นต้นด้วย http:// หรือ https:// เช่น http://192.168.1.50:8080")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("ใส่เฉพาะที่อยู่เว็บ (ไม่ต้องมี /... ต่อท้าย) เช่น http://192.168.1.50:8080")
    return t


class Page(OwnerPage):
    title = "ตั้งค่า"

    def build(self) -> None:
        header = PageHeader(self, "ตั้งค่า", "ค่าที่ปรับได้ของร้าน — กด \"บันทึกการตั้งค่า\" ด้านล่างเมื่อแก้เสร็จ")
        header.pack(fill="x", padx=24, pady=(18, 8))
        self.header = header
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # --- ข้อมูลร้านและหัวใบเสร็จรับเงิน ---
        card = self._section(
            scroll,
            "ข้อมูลร้านและใบเสร็จรับเงิน",
            "กำหนดชื่อร้าน เลขประจำตัวผู้เสียภาษี (เลือกเปิด/ปิดการแสดงผลบนใบเสร็จได้) ที่อยู่ และเบอร์โทรศัพท์ที่จะพิมพ์บนใบเสร็จรับเงิน"
        )
        shop_row1 = ctk.CTkFrame(card, fg_color="transparent")
        shop_row1.pack(fill="x", padx=18, pady=(0, 8))
        shop_row1.grid_columnconfigure((0, 1, 2), weight=1, uniform="sh1")
        self.shop_name = LabeledEntry(shop_row1, "ชื่อร้าน", placeholder=config.DEFAULT_SHOP_NAME)
        self.shop_name.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.shop_tax_id = LabeledEntry(shop_row1, "เลขประจำตัวผู้เสียภาษี (13 หลัก)", placeholder="เว้นว่างได้หากไม่มี")
        self.shop_tax_id.grid(row=0, column=1, sticky="ew", padx=6)
        self.shop_phone = LabeledEntry(shop_row1, "เบอร์โทรศัพท์ร้าน", placeholder="เช่น 012-345-6789")
        self.shop_phone.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        tax_sw_row = ctk.CTkFrame(card, fg_color="transparent")
        tax_sw_row.pack(fill="x", padx=18, pady=(0, 8))
        self.shop_tax_id_switch = ctk.CTkSwitch(
            tax_sw_row,
            text="แสดงเลขประจำตัวผู้เสียภาษีในใบเสร็จรับเงิน",
            font=font(15, True),
            progress_color=COLORS["success"],
        )
        self.shop_tax_id_switch.pack(side="left")

        shop_row2 = ctk.CTkFrame(card, fg_color="transparent")
        shop_row2.pack(fill="x", padx=18, pady=(0, 8))
        shop_row2.grid_columnconfigure(0, weight=2, uniform="sh2")
        shop_row2.grid_columnconfigure(1, weight=1, uniform="sh2")
        shop_row2.grid_columnconfigure(2, weight=1, uniform="sh2")
        self.shop_address = LabeledEntry(shop_row2, "ที่อยู่ร้าน (บ้านเลขที่ / หมู่ที่ / ถนน)", placeholder="เช่น 99 หมู่ที่ 1")
        self.shop_address.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.shop_subdistrict = LabeledEntry(shop_row2, "ตำบล / แขวง", placeholder="วังตะเฆ่")
        self.shop_subdistrict.grid(row=0, column=1, sticky="ew", padx=6)
        self.shop_district = LabeledEntry(shop_row2, "อำเภอ / เขต", placeholder="หนองบัวระเหว")
        self.shop_district.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        shop_row3 = ctk.CTkFrame(card, fg_color="transparent")
        shop_row3.pack(fill="x", padx=18, pady=(0, 14))
        shop_row3.grid_columnconfigure((0, 1, 2), weight=1, uniform="sh3")
        self.shop_province = LabeledEntry(shop_row3, "จังหวัด", placeholder="ชัยภูมิ")
        self.shop_province.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.shop_postal_code = LabeledEntry(shop_row3, "รหัสไปรษณีย์ (5 หลัก)", placeholder="36250")
        self.shop_postal_code.grid(row=0, column=1, sticky="ew", padx=6)

        # --- ลิงก์เว็บลูกค้า ---
        card = self._section(scroll, "ลิงก์เว็บลูกค้า (QR โต๊ะ)",
                             "ที่อยู่ที่ลูกค้าเปิดจากมือถือหลังสแกน QR เช่น http://192.168.1.50:8080 (ใช้ IP เครื่องร้านใน Wi-Fi เดียวกัน)")
        self.base_url = LabeledEntry(card, "ลิงก์เว็บลูกค้า", placeholder="http://192.168.1.50:8080")
        self.base_url.pack(fill="x", padx=18, pady=(0, 6))
        lan_row = ctk.CTkFrame(card, fg_color="transparent")
        lan_row.pack(fill="x", padx=18, pady=(0, 14))
        self.lan_label = ctk.CTkLabel(lan_row, text="", font=font(13), text_color=COLORS["text_muted"], anchor="w")
        self.lan_label.pack(side="left")
        self.lan_button = ActionButton(lan_row, "ใช้ค่านี้", self.use_lan_ip, "ghost", height=30, width=90, size=13)

        # --- การชำระเงินด้วย PromptPay และราคาชั่งกิโล ---
        card = self._section(
            scroll,
            "การรับชำระเงิน PromptPay และอัตราราคาชั่งกิโล",
            "ข้อมูลบัญชีสำหรับสร้าง QR รับเงินตามยอดสุทธิอัตโนมัติในหน้าชำระเงิน และราคาหมูกระทะชั่งกิโล (ค่าเริ่มต้น 299 บาท/กก.)"
        )
        pp_row = ctk.CTkFrame(card, fg_color="transparent")
        pp_row.pack(fill="x", padx=18, pady=(0, 14))
        pp_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="pp")
        self.promptpay_id = LabeledEntry(
            pp_row, "หมายเลข PromptPay (เบอร์ 10 หลัก / บัตร 13 หลัก)", placeholder=config.DEFAULT_PROMPTPAY_ID
        )
        self.promptpay_id.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.promptpay_name = LabeledEntry(
            pp_row, "ชื่อบัญชีเจ้าของร้าน (แสดงให้พนักงานตรวจสอบ)", placeholder=config.DEFAULT_PROMPTPAY_NAME
        )
        self.promptpay_name.grid(row=0, column=1, sticky="ew", padx=6)
        self.weigh_price = LabeledEntry(
            pp_row, "ราคาชั่งกิโล (บาท/กก. · ค่าเริ่มต้น 299)", placeholder="299"
        )
        self.weigh_price.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        # --- แจ้งเตือนโต๊ะเงียบ และ เกณฑ์สต๊อกใกล้หมด ---
        card = self._section(
            scroll,
            "แจ้งเตือนโต๊ะเงียบ และ เกณฑ์สต๊อกใกล้หมด",
            "ระบบตรวจทุก 30 วินาที แล้วขึ้นแถบแจ้งเตือนให้พนักงาน — เกณฑ์สต๊อกใกล้หมดมีค่าเริ่มต้น 5 หน่วย (แก้ไขได้)"
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 14))
        row.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="a")
        self.pending_min = LabeledEntry(row, "โต๊ะรอยืนยันนานเกิน (นาที)")
        self.pending_min.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.idle_min = LabeledEntry(row, "โต๊ะเปิดแล้วเงียบเกิน (นาที)")
        self.idle_min.grid(row=0, column=1, sticky="ew", padx=6)
        self.snooze_min = LabeledEntry(row, "เตือนซ้ำหลังกด \"ปล่อยไว้\" (นาที)")
        self.snooze_min.grid(row=0, column=2, sticky="ew", padx=6)
        self.stock_threshold = LabeledEntry(row, "เกณฑ์สต๊อกใกล้หมดเริ่มต้น (ค่าเริ่มต้น 5 หน่วย)")
        self.stock_threshold.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        # --- ค่าบริการ / ภาษีมูลค่าเพิ่ม ---
        card = self._section(
            scroll,
            "ค่าบริการและภาษีมูลค่าเพิ่ม",
            "ค่าบริการคิดจากยอดหลังหักส่วนลด ; ภาษีมูลค่าเพิ่มคิดจาก (ยอดหลังหักส่วนลด + ค่าบริการ) — มีผลกับบิลถัดไป"
        )
        for attr, label in (("service", "เก็บค่าบริการ"), ("vat", "คิดภาษีมูลค่าเพิ่ม")):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=(0, 10))
            switch = ctk.CTkSwitch(row, text=label, font=font(16), progress_color=COLORS["success"], width=190)
            switch.pack(side="left")
            entry = LabeledEntry(row, "อัตรา (%)", width=120)
            entry.pack(side="left", padx=20)
            setattr(self, f"{attr}_switch", switch)
            setattr(self, f"{attr}_percent", entry)
        ctk.CTkLabel(card, text="", height=4).pack()

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=24, pady=(0, 16))
        ActionButton(bottom, "บันทึกการตั้งค่า", self.save, "success", height=46, width=200, size=17).pack(side="right")
        ActionButton(bottom, "ยกเลิกการแก้ไข (โหลดค่าเดิม)", self.refresh, "ghost", height=46, width=230, size=15).pack(side="right", padx=10)

    def _section(self, parent, title: str, hint: str):
        card = Card(parent)
        card.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(card, text=title, font=font(18, True), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(14, 0))
        ctk.CTkLabel(card, text=hint, font=font(13), text_color=COLORS["text_muted"], wraplength=900,
                     justify="left").pack(anchor="w", padx=18, pady=(0, 10))
        return card

    # ---------- โหลด/บันทึก ----------
    def on_open(self, **params) -> None:
        self.refresh()

    def refresh(self) -> None:
        s = settings_service
        shop = s.get_shop_info()
        self.shop_name.set(shop["shop_name"])
        self.shop_tax_id.set(shop["shop_tax_id"])
        if shop["shop_tax_id_enabled"]:
            self.shop_tax_id_switch.select()
        else:
            self.shop_tax_id_switch.deselect()
        self.shop_address.set(shop["shop_address"])
        self.shop_subdistrict.set(shop["shop_subdistrict"])
        self.shop_district.set(shop["shop_district"])
        self.shop_province.set(shop["shop_province"])
        self.shop_postal_code.set(shop["shop_postal_code"])
        self.shop_phone.set(shop["shop_phone"])

        self._loaded_url = s.get_setting("public_base_url", "") or ""
        self.base_url.set(self._loaded_url)
        self._show_lan_hint()
        self.promptpay_id.set(s.get_setting("promptpay_id", config.DEFAULT_PROMPTPAY_ID) or config.DEFAULT_PROMPTPAY_ID)
        self.promptpay_name.set(s.get_setting("promptpay_name", config.DEFAULT_PROMPTPAY_NAME) or config.DEFAULT_PROMPTPAY_NAME)
        self.weigh_price.set(fmt_qty(s.get_float("weigh_price_per_kg", config.DEFAULT_WEIGH_PRICE_PER_KG)))
        self.pending_min.set(str(s.get_int("alert_pending_minutes", 5)))
        self.idle_min.set(str(s.get_int("alert_idle_open_minutes", 10)))
        self.snooze_min.set(str(s.get_int("alert_snooze_minutes", 5)))
        self.stock_threshold.set(fmt_qty(s.get_float("stock_low_threshold", config.DEFAULT_STOCK_LOW_THRESHOLD)))
        for attr in ("service", "vat"):
            on = s.get_bool(f"{attr}_charge_enabled" if attr == "service" else "vat_enabled")
            switch = getattr(self, f"{attr}_switch")
            switch.select() if on else switch.deselect()
            pct = s.get_float(f"{attr}_charge_percent" if attr == "service" else "vat_percent")
            getattr(self, f"{attr}_percent").set(f"{pct:g}")

    def _lan_url(self) -> str | None:
        ip = detect_lan_ip()
        return f"http://{ip}:{config.WEB_PORT}" if ip else None

    def use_lan_ip(self) -> None:
        url = self._lan_url()
        if url:
            self.base_url.set(url)

    def _show_lan_hint(self) -> None:
        url = self._lan_url()
        if url:
            self.lan_label.configure(text=f"IP ของเครื่องนี้ในเครือข่าย: {url}  (มือถือต้องต่อ Wi-Fi เดียวกัน)")
            self.lan_button.pack(side="left", padx=10)
        else:
            self.lan_label.configure(text="หา IP ของเครื่องนี้ไม่ได้ — ตรวจว่าต่อเครือข่ายอยู่ แล้วกรอกเอง")
            self.lan_button.pack_forget()

    def _collect(self) -> dict:
        """อ่าน+ตรวจทุกช่อง -> dict พร้อมบันทึก ; ValueError ถ้าช่องใดผิด"""
        shop_name = (self.shop_name.get() or "").strip()
        if not shop_name:
            raise ValueError("กรุณากรอกชื่อร้าน")
        tax_id = (self.shop_tax_id.get() or "").strip().replace("-", "").replace(" ", "")
        tax_id_on = bool(self.shop_tax_id_switch.get())
        if tax_id and (not tax_id.isdigit() or len(tax_id) != 13):
            raise ValueError("เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลข 13 หลัก (หรือเว้นว่างไว้หากไม่มี)")
        postal = (self.shop_postal_code.get() or "").strip()
        if postal and (not postal.isdigit() or len(postal) != 5):
            raise ValueError("รหัสไปรษณีย์ต้องเป็นตัวเลข 5 หลัก (หรือเว้นว่างไว้)")

        clean_pp_id, _ = qr_service.validate_promptpay_id(self.promptpay_id.get())
        pp_name = (self.promptpay_name.get() or "").strip()
        if not pp_name:
            raise ValueError("กรุณากรอกชื่อบัญชีเจ้าของร้านสำหรับตรวจสอบ")
        weigh_rate = parse_number(self.weigh_price.get(), "ราคาชั่งกิโล", minimum=1, maximum=100000)
        stock_thresh = parse_number(self.stock_threshold.get(), "เกณฑ์สต๊อกใกล้หมด", minimum=0, maximum=100000)
        return {
            "shop_name": shop_name,
            "shop_tax_id": tax_id,
            "shop_tax_id_enabled": tax_id_on,
            "shop_address": (self.shop_address.get() or "").strip(),
            "shop_subdistrict": (self.shop_subdistrict.get() or "").strip(),
            "shop_district": (self.shop_district.get() or "").strip(),
            "shop_province": (self.shop_province.get() or "").strip(),
            "shop_postal_code": postal,
            "shop_phone": (self.shop_phone.get() or "").strip(),
            "public_base_url": normalize_base_url(self.base_url.get()),
            "promptpay_id": clean_pp_id,
            "promptpay_name": pp_name,
            "weigh_price_per_kg": weigh_rate,
            "alert_pending_minutes": parse_int(self.pending_min.get(), "เวลารอยืนยัน", minimum=1, maximum=MAX_MINUTES),
            "alert_idle_open_minutes": parse_int(self.idle_min.get(), "เวลาโต๊ะเงียบ", minimum=1, maximum=MAX_MINUTES),
            "alert_snooze_minutes": parse_int(self.snooze_min.get(), "เวลาเตือนซ้ำ", minimum=1, maximum=MAX_MINUTES),
            "stock_low_threshold": stock_thresh,
            "service_charge_enabled": bool(self.service_switch.get()),
            "service_charge_percent": parse_percent(self.service_percent.get(), "อัตราค่าบริการ"),
            "vat_enabled": bool(self.vat_switch.get()),
            "vat_percent": parse_percent(self.vat_percent.get(), "อัตราภาษีมูลค่าเพิ่ม"),
        }

    def save(self) -> None:
        try:
            values = self._collect()
        except ValueError as e:
            self.toast(str(e), "error")
            return
        ok, _ = self.call(settings_service.set_many, values, user_id=self.user_id, success="บันทึกการตั้งค่าแล้ว")
        if not ok:
            return
        if values["public_base_url"] != self._loaded_url:
            show_info(self, "คุณเปลี่ยนลิงก์เว็บลูกค้าแล้ว\nQR ที่พิมพ์ไว้เดิมจะยังชี้ไปลิงก์เก่า — "
                            "ไปหน้า \"จัดการโต๊ะ/QR\" กด \"สร้าง QR ทุกโต๊ะ\" แล้วพิมพ์ติดโต๊ะใหม่", title="ต้องสร้าง QR ใหม่")
        self.refresh()
        if self.app.alert_center:
            self.app.alert_center.refresh_view()
