"""ui/app.py — หน้าต่างหลักของแอป PC: ล็อกอิน -> เมนูซ้าย + แถบบน + แถบแจ้งเตือน + พื้นที่หน้า

ใช้งาน:  `from ui.app import App;  App().mainloop()`

การเพิ่มหน้า: เพิ่มบรรทัดใน NAV_ITEMS (key, ป้ายเมนู, สิทธิ์ขั้นต่ำ, โมดูล, กลุ่ม) — โมดูลต้องมีคลาส `Page`
(สืบทอด ui.widgets.BasePage) ; ถ้าโมดูลยังว่าง/ยังไม่มี `Page` แอปจะแสดงหน้า "ยังไม่พร้อมใช้งาน" แทน (ไม่ล่ม)

หมายเหตุ:
- นำเมนู "หน้าจอครัว" (kitchen) ออกจากทั้งฝั่งเจ้าของร้านและพนักงานตามข้อกำหนด
- รวมหน้า "รายงาน" (report) เข้ากับหน้า "แดชบอร์ด" (dashboard) ของเจ้าของร้าน โดยนำเมนูรายงานที่แยกต่างหากออก
"""
from __future__ import annotations

import importlib
import traceback
from dataclasses import dataclass

import customtkinter as ctk
from PIL import Image, ImageTk

import config
from services import auth_service, log_service, shop_service
from ui.alert_center import AlertCenter
from ui.login_page import LoginPage
from ui.theme import COLORS, font, init_theme
from ui.widgets import BasePage, StatusBadge, confirm, show_toast


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    role: str          # สิทธิ์ขั้นต่ำ: config.ROLE_STAFF / config.ROLE_OWNER
    module: str
    group: str


STAFF_GROUP = "หน้าร้าน"
OWNER_GROUP = "เจ้าของร้าน"

NAV_ITEMS: list[NavItem] = [
    NavItem("tables", "โต๊ะ", config.ROLE_STAFF, "ui.staff.tables_page", STAFF_GROUP),
    NavItem("takeaway", "สั่งกลับบ้าน", config.ROLE_STAFF, "ui.staff.takeaway_page", STAFF_GROUP),
    NavItem("weigh", "ชั่งน้ำหนัก", config.ROLE_STAFF, "ui.staff.weigh_page", STAFF_GROUP),
    NavItem("orders", "ออเดอร์", config.ROLE_STAFF, "ui.staff.orders_page", STAFF_GROUP),
    NavItem("checkout", "เช็คเอาท์", config.ROLE_STAFF, "ui.staff.checkout_page", STAFF_GROUP),
    NavItem("dashboard", "แดชบอร์ด", config.ROLE_OWNER, "ui.owner.dashboard_page", OWNER_GROUP),
    NavItem("menu", "เมนูและราคา", config.ROLE_OWNER, "ui.owner.menu_page", OWNER_GROUP),
    NavItem("stock", "สต๊อก", config.ROLE_OWNER, "ui.owner.stock_page", OWNER_GROUP),
    NavItem("promo", "โปรโมชั่น", config.ROLE_OWNER, "ui.owner.promo_page", OWNER_GROUP),
    NavItem("tables_manage", "จัดการโต๊ะ/QR", config.ROLE_OWNER, "ui.owner.tables_manage_page", OWNER_GROUP),
    NavItem("users", "ผู้ใช้", config.ROLE_OWNER, "ui.owner.users_page", OWNER_GROUP),
    NavItem("settings", "ตั้งค่า", config.ROLE_OWNER, "ui.owner.settings_page", OWNER_GROUP),
    NavItem("log", "ประวัติการใช้งาน", config.ROLE_OWNER, "ui.owner.log_page", OWNER_GROUP),
    NavItem("backup", "สำรองข้อมูล", config.ROLE_OWNER, "ui.owner.backup_page", OWNER_GROUP),
]
NAV_BY_KEY = {item.key: item for item in NAV_ITEMS}
DEFAULT_PAGE = {config.ROLE_STAFF: "tables", config.ROLE_OWNER: "dashboard"}


class PlaceholderPage(BasePage):
    """หน้าแทนที่ เมื่อหน้าจริงยังไม่ถูกสร้าง หรือโหลดไม่สำเร็จ"""
    def __init__(self, master, app, title: str, message: str):
        self._message = message
        self.title = title
        super().__init__(master, app)

    def build(self) -> None:
        box = ctk.CTkFrame(self, fg_color="transparent")
        box.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(box, text=self.title, font=font(26, True), text_color=COLORS["text"]).pack()
        ctk.CTkLabel(box, text=self._message, font=font(16), text_color=COLORS["text_muted"],
                     wraplength=520, justify="center").pack(pady=(8, 0))


class App(ctk.CTk):
    SIDEBAR_WIDTH = 230

    def __init__(self):
        init_theme()
        super().__init__(fg_color=COLORS["bg"])
        self.title(config.APP_NAME)
        self.geometry("1280x780")
        self.minsize(1040, 660)
        self._set_icon()
        self.user: dict | None = None
        self.alert_center: AlertCenter | None = None
        self.pages: dict[str, BasePage] = {}
        self.current_key: str | None = None
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._login: LoginPage | None = None
        self._main: ctk.CTkFrame | None = None
        self._status_job = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_login()

    # ================== ล็อกอิน / ล็อกเอาท์ ==================
    def _set_icon(self) -> None:
        try:
            with Image.open(config.LOGO_PATH) as im:
                self._icon = ImageTk.PhotoImage(im.resize((64, 64)))
            self.iconphoto(True, self._icon)
        except Exception:
            pass

    def show_login(self) -> None:
        self._teardown_main()
        self.user = None
        self._login = LoginPage(self, on_success=self.on_login)
        self._login.pack(fill="both", expand=True)

    def on_login(self, user: dict) -> None:
        self.user = user
        if self._login is not None:
            self._login.destroy()
            self._login = None
        self._build_main()
        self.navigate(DEFAULT_PAGE.get(user["role"], "tables"))

    def logout(self) -> None:
        if not confirm(self, "ออกจากระบบใช่หรือไม่?", title="ออกจากระบบ", confirm_text="ออกจากระบบ"):
            return
        try:
            log_service.log_action("logout", f"{self.user['display_name']} ออกจากระบบ",
                                   user_id=self.user["id"])
        except Exception:
            traceback.print_exc()
        self.show_login()

    def on_close(self) -> None:
        self._teardown_main()
        self.destroy()

    # ================== โครงหน้าหลัก ==================
    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)
        self._main = main
        self._build_sidebar(main)

        right = ctk.CTkFrame(main, fg_color=COLORS["bg"], corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)
        self._build_topbar(right)

        self.alert_center = AlertCenter(
            right, user_provider=lambda: self.user, on_change=self._on_alerts_changed,
            show_fn=lambda: self.alert_center.grid(row=1, column=0, sticky="ew"),
            hide_fn=lambda: self.alert_center.grid_remove())
        self.content = ctk.CTkFrame(right, fg_color=COLORS["bg"], corner_radius=0)
        self.content.grid(row=2, column=0, sticky="nsew")
        self.alert_center.start()
        self.refresh_shop_status()

    def _build_sidebar(self, parent) -> None:
        side = ctk.CTkFrame(parent, width=self.SIDEBAR_WIDTH, fg_color=COLORS["sidebar"], corner_radius=0)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.pack_propagate(False)

        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(18, 10))
        try:
            with Image.open(config.LOGO_PATH) as im:
                self._side_logo = ctk.CTkImage(im.copy(), size=(64, 64))
            ctk.CTkLabel(head, image=self._side_logo, text="").pack(side="left")
        except Exception:
            pass
        ctk.CTkLabel(head, text=config.APP_NAME_SHORT, font=font(22, True),
                     text_color=COLORS["sidebar_text"]).pack(side="left", padx=10)

        nav = ctk.CTkScrollableFrame(side, fg_color="transparent", corner_radius=0)
        nav.pack(fill="both", expand=True, padx=4)
        self._nav_buttons = {}
        last_group = None
        for item in NAV_ITEMS:
            if not auth_service.has_permission(self.user, item.role):
                continue
            if item.group != last_group:
                ctk.CTkLabel(nav, text=item.group, font=font(13, True), text_color=COLORS["sidebar_muted"]
                             ).pack(anchor="w", padx=14, pady=(14, 2))
                last_group = item.group
            btn = ctk.CTkButton(nav, text=item.label, anchor="w", height=38, font=font(16),
                                fg_color="transparent", hover_color=COLORS["sidebar_hover"],
                                text_color=COLORS["sidebar_text"], corner_radius=8,
                                command=lambda k=item.key: self.navigate(k))
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_buttons[item.key] = btn

        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=14)
        role_th = "เจ้าของร้าน" if self.user["role"] == config.ROLE_OWNER else "พนักงาน"
        ctk.CTkLabel(foot, text=self.user["display_name"], font=font(16, True),
                     text_color=COLORS["sidebar_text"], anchor="w").pack(fill="x")
        ctk.CTkLabel(foot, text=role_th, font=font(13), text_color=COLORS["sidebar_muted"],
                     anchor="w").pack(fill="x", pady=(0, 8))
        ctk.CTkButton(foot, text="ออกจากระบบ", height=36, font=font(14, True), fg_color="transparent",
                      border_width=1, border_color=COLORS["sidebar_muted"], hover_color=COLORS["sidebar_hover"],
                      text_color=COLORS["sidebar_text"], command=self.logout).pack(fill="x")

    def _build_topbar(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=0, height=60)
        bar.grid(row=0, column=0, sticky="ew")
        bar.pack_propagate(False)
        self.title_label = ctk.CTkLabel(bar, text="", font=font(20, True), text_color=COLORS["text"])
        self.title_label.pack(side="left", padx=22)
        self.topbar_right = ctk.CTkFrame(bar, fg_color="transparent")
        self.topbar_right.pack(side="right", padx=16)
        self.shop_widget = self._make_shop_widget(self.topbar_right)
        self.shop_widget.pack(side="right")

    def _make_shop_widget(self, parent):
        """ใช้ ShopControl ของขั้น 4 ถ้ามี ไม่งั้นใช้ป้ายสถานะร้านอย่างเดียว"""
        try:
            module = importlib.import_module("ui.staff.shop_control")
            return module.ShopControl(parent, self)
        except (ImportError, AttributeError):
            pass
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        self._shop_badge = StatusBadge(parent, "ร้านปิด", COLORS["neutral"], size=15)
        return self._shop_badge

    def refresh_shop_status(self) -> None:
        """อัปเดตป้ายสถานะร้านบนแถบบน (ShopControl ที่มี `refresh()` จะถูกเรียกด้วย) ; วนทุก 15 วินาที"""
        if self._main is None:
            return
        try:
            if hasattr(self.shop_widget, "refresh") and not hasattr(self, "_shop_badge"):
                self.shop_widget.refresh()
            elif hasattr(self, "_shop_badge"):
                opened = shop_service.is_open()
                self._shop_badge.set("ร้านเปิด" if opened else "ร้านปิด",
                                     COLORS["success"] if opened else COLORS["neutral"])
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        if self._status_job is not None:
            try:
                self.after_cancel(self._status_job)
            except Exception:
                pass
        self._status_job = self.after(15000, self.refresh_shop_status)

    def _teardown_main(self) -> None:
        if self.alert_center is not None:
            self.alert_center.stop()
            self.alert_center = None
        if self._status_job is not None:
            try:
                self.after_cancel(self._status_job)
            except Exception:
                pass
            self._status_job = None
        for page in self.pages.values():
            page.deactivate()
        self.pages = {}
        self.current_key = None
        self._nav_buttons = {}
        if hasattr(self, "_shop_badge"):
            del self._shop_badge
        if self._main is not None:
            self._main.destroy()
            self._main = None

    # ================== นำทางระหว่างหน้า ==================
    def navigate(self, key: str, **params) -> None:
        """เปิดหน้า key (ต้องมีสิทธิ์) ; params ส่งเข้า `Page.on_show(**params)`
        หากมีการเรียก key='report' จากจุดใด จะส่งต่อไปยังหน้า 'dashboard' ที่รวมรายงานไว้แล้วอย่างปลอดภัย"""
        if key == "report":
            key = "dashboard"
        if key == "kitchen":
            return
        item = NAV_BY_KEY.get(key)
        if item is None or self.user is None:
            return
        if not auth_service.has_permission(self.user, item.role):
            self.toast("คุณไม่มีสิทธิ์เข้าหน้านี้", "error")
            return
        if self.current_key and self.current_key in self.pages and self.current_key != key:
            self.pages[self.current_key].deactivate()
            self.pages[self.current_key].pack_forget()
        page = self.pages.get(key)
        if page is None:
            page = self._create_page(item)
            self.pages[key] = page
        elif self.current_key == key:
            page.deactivate()           # เปิดหน้าเดิมซ้ำ = โหลดใหม่ด้วย params ใหม่
        page.pack(fill="both", expand=True)
        self.current_key = key
        self.title_label.configure(text=item.label)
        for k, btn in self._nav_buttons.items():
            btn.configure(fg_color=COLORS["sidebar_active"] if k == key else "transparent")
        page.activate(**params)

    def _create_page(self, item: NavItem) -> BasePage:
        try:
            module = importlib.import_module(item.module)
            page_cls = getattr(module, "Page", None)
            if page_cls is None:
                return PlaceholderPage(self.content, self, item.label,
                                       "หน้านี้ยังไม่พร้อมใช้งาน (อยู่ระหว่างพัฒนา)")
            return page_cls(self.content, self)
        except Exception as e:  # noqa: BLE001 — หน้าเดียวพังต้องไม่ทำให้ทั้งแอปล่ม
            traceback.print_exc()
            return PlaceholderPage(self.content, self, item.label, f"เปิดหน้านี้ไม่สำเร็จ\n{e}")

    # ================== อื่น ๆ ==================
    def toast(self, text: str, kind: str = "info") -> None:
        show_toast(self, text, kind)

    def _on_alerts_changed(self) -> None:
        """แจ้งเตือนเปลี่ยน -> ให้หน้าปัจจุบันโหลดข้อมูลใหม่ (เช่น โต๊ะถูกยกเลิก)"""
        page = self.pages.get(self.current_key) if self.current_key else None
        if page is not None:
            page.reload()
