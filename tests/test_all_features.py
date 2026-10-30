"""tests/test_all_features.py — ชุดทดสอบอัตโนมัติครอบคลุมข้อกำหนดทั้งหมด (รวมทั้ง 9 ข้อในเอกสาร PDF) และ regression flow เดิม

รันด้วย:  python3 -m unittest discover -s tests -v
หรือ:     python3 tests/test_all_features.py
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
import warnings

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# รองรับสภาพแวดล้อมทดสอบที่ไม่มีแพ็กเกจ bcrypt (เช่น CI/Sandbox) ด้วย crypt BLOWFISH มาตรฐานที่เข้ากันได้กับแฮช $2b$12$ เดิม
try:
    import bcrypt  # noqa: F401
except ImportError:
    if Path("/tmp/vm_vendor").exists() and "/tmp/vm_vendor" not in sys.path:
        sys.path.append("/tmp/vm_vendor")
    try:
        import bcrypt  # noqa: F401
    except ImportError:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import crypt as _std_crypt

        class _CompatBcryptModule(types.ModuleType):
            @staticmethod
            def gensalt(rounds: int = 12) -> bytes:
                if hasattr(_std_crypt, "METHOD_BLOWFISH"):
                    s = _std_crypt.mksalt(_std_crypt.METHOD_BLOWFISH)
                else:
                    s = "$2b$12$lTdudslGfF0exQM28dUaN."
                return s.encode("utf-8")

            @staticmethod
            def hashpw(password: bytes, salt: bytes) -> bytes:
                pw_str = password.decode("utf-8") if isinstance(password, (bytes, bytearray)) else str(password)
                salt_str = salt.decode("utf-8") if isinstance(salt, (bytes, bytearray)) else str(salt)
                hashed = _std_crypt.crypt(pw_str, salt_str)
                if not hashed or not hashed.startswith("$2"):
                    raise ValueError("Invalid bcrypt salt or hash")
                return hashed.encode("utf-8")

            @staticmethod
            def checkpw(password: bytes, hashed_password: bytes) -> bool:
                pw_str = password.decode("utf-8") if isinstance(password, (bytes, bytearray)) else str(password)
                h_str = hashed_password.decode("utf-8") if isinstance(hashed_password, (bytes, bytearray)) else str(hashed_password)
                if not h_str.startswith("$2"):
                    raise ValueError("Invalid hash")
                return _std_crypt.crypt(pw_str, h_str) == h_str

        sys.modules["bcrypt"] = _CompatBcryptModule("bcrypt")

from PIL import Image

import config
from database import db, schema, seed
from services import (
    alert_service,
    auth_service,
    backup_service,
    checkout_service,
    log_service,
    menu_service,
    notice_service,
    order_service,
    pricing_service,
    promo_service,
    qr_service,
    report_service,
    settings_service,
    shop_service,
    stock_service,
    table_service,
    weigh_service,
)
from web import session as web_session


def _install_nicegui_mock_if_needed():
    """หากสภาพแวดล้อมไม่มี nicegui ให้สร้าง mock เบา ๆ เพื่อทดสอบการวาดหน้า web/pages/ ได้ครบทุกกิ่ง"""
    try:
        import nicegui  # noqa: F401
        return
    except ImportError:
        pass

    class DummyElement:
        def __init__(self, kind: str, text: str = "", **kwargs):
            self.kind = kind
            self.text = str(text)
            self.kwargs = kwargs
            self.props_str = ""
            self.classes_str = ""
            self.style_str = ""
            self.enabled = True
            self.children = []
            _current_stack[-1].append(self)

        def classes(self, c: str = ""):
            self.classes_str += " " + c
            return self

        def props(self, p: str = ""):
            self.props_str += " " + p
            return self

        def style(self, s: str = ""):
            self.style_str += " " + s
            return self

        def set_text(self, t: str):
            self.text = str(t)

        def enable(self):
            self.enabled = True

        def disable(self):
            self.enabled = False

        def open(self):
            pass

        def close(self):
            pass

        def deactivate(self):
            pass

        def __enter__(self):
            _current_stack.append(self.children)
            return self

        def __exit__(self, *args):
            _current_stack.pop()

    _current_stack = [[]]

    class DummyUI:
        elements = _current_stack[0]
        notifications = []
        head_htmls = []

        @classmethod
        def reset(cls):
            _current_stack.clear()
            root = []
            _current_stack.append(root)
            cls.elements = root
            cls.notifications = []
            cls.head_htmls = []

        @staticmethod
        def colors(**kw):
            pass

        @staticmethod
        def add_head_html(html_str: str):
            DummyUI.head_htmls.append(html_str)

        @staticmethod
        def query(q):
            return DummyElement("query", q)

        @staticmethod
        def column():
            return DummyElement("column")

        @staticmethod
        def row():
            return DummyElement("row")

        @staticmethod
        def card():
            return DummyElement("card")

        @staticmethod
        def label(text=""):
            return DummyElement("label", text)

        @staticmethod
        def button(text="", on_click=None, icon=None):
            return DummyElement("button", text, on_click=on_click, icon=icon)

        @staticmethod
        def badge(text="", color=None):
            return DummyElement("badge", text, color=color)

        @staticmethod
        def icon(name="", color=None):
            return DummyElement("icon", name, color=color)

        @staticmethod
        def image(src=""):
            return DummyElement("image", src)

        @staticmethod
        def separator():
            return DummyElement("separator")

        @staticmethod
        def dialog():
            return DummyElement("dialog")

        @staticmethod
        def input(label=""):
            el = DummyElement("input", label)
            el.value = ""
            return el

        @staticmethod
        def spinner(size="md", color=None):
            return DummyElement("spinner", size, color=color)

        @staticmethod
        def notify(msg, type="info", position="top", **kw):
            DummyUI.notifications.append((str(msg), type))

        @staticmethod
        def refreshable(fn):
            fn.refresh = lambda: fn()
            return fn

        @staticmethod
        def timer(interval, callback, once=False):
            return DummyElement("timer", str(interval))

        @staticmethod
        def page(path):
            def _dec(fn):
                return fn
            return _dec

    class DummyStorage:
        def __init__(self):
            self.user = {}
            self.browser = {}

    class DummyApp:
        storage = DummyStorage()
        static_files = []

        @staticmethod
        def add_static_file(**kw):
            DummyApp.static_files.append(kw)

        @staticmethod
        def add_static_files(*a, **kw):
            DummyApp.static_files.append((a, kw))

    mod = types.ModuleType("nicegui")
    mod.ui = DummyUI
    mod.app = DummyApp
    mod.Client = object
    sys.modules["nicegui"] = mod


def _install_customtkinter_mock_if_needed():
    try:
        import customtkinter  # noqa: F401
        return
    except ImportError:
        pass

    class FakeVar:
        def __init__(self, value=""):
            self._v = str(value)
            self._cbs = []

        def get(self):
            return self._v

        def set(self, v):
            self._v = str(v)
            for cb in list(self._cbs):
                cb()

        def trace_add(self, mode, cb):
            self._cbs.append(cb)

    class FakeWidget:
        def __init__(self, master=None, **kw):
            self.master = master
            self.kw = dict(kw)
            self._children = []
            self._text = kw.get("text", "")
            self._values = list(kw.get("values", [""]))
            self._val = self._values[0] if self._values else ""
            self._selected = False
            self._var = kw.get("textvariable")
            self.grid_info_dict = {}
            self.pack_info_dict = {}
            self.col_configs = {}
            if master is not None and hasattr(master, "_children"):
                master._children.append(self)

        def pack(self, *a, **kw):
            self.pack_info_dict = dict(kw)
            return self

        def pack_forget(self, *a, **kw):
            self.pack_info_dict = {}

        def grid(self, *a, **kw):
            self.grid_info_dict = dict(kw)
            return self

        def grid_remove(self, *a, **kw):
            pass

        def place(self, *a, **kw):
            return self

        def grid_columnconfigure(self, idx, **kw):
            self.col_configs[idx] = dict(kw)

        def grid_rowconfigure(self, *a, **kw):
            pass

        def grid_propagate(self, *a, **kw):
            pass

        def pack_propagate(self, *a, **kw):
            pass

        def configure(self, **kw):
            self.kw.update(kw)
            if "text" in kw:
                self._text = kw["text"]
            if "values" in kw:
                self._values = list(kw["values"])

        def cget(self, k):
            if k == "text":
                return self._text
            return self.kw.get(k)

        def winfo_children(self):
            return list(self._children)

        def winfo_toplevel(self):
            return self

        def winfo_rootx(self):
            return 0

        def winfo_rooty(self):
            return 0

        def winfo_width(self):
            return 1280

        def winfo_height(self):
            return 780

        def winfo_reqheight(self):
            return 400

        def destroy(self):
            if self.master and self in getattr(self.master, "_children", []):
                self.master._children.remove(self)
            self._children.clear()

        def after(self, ms, fn=None, *a):
            return 1

        def after_cancel(self, j):
            pass

        def bind(self, *a, **kw):
            pass

        def focus_set(self):
            pass

        def focus_force(self):
            pass

        def lift(self):
            pass

        def grab_set(self):
            pass

        def grab_release(self):
            pass

        def wait_window(self, w=None):
            pass

        def update_idletasks(self):
            pass

        def geometry(self, *a):
            pass

        def minsize(self, *a):
            pass

        def winfo_exists(self):
            return True

        def clipboard_clear(self):
            pass

        def clipboard_append(self, *a):
            pass

        def title(self, *a):
            pass

        def resizable(self, *a):
            pass

        def transient(self, *a):
            pass

        def protocol(self, *a):
            pass

        def iconphoto(self, *a):
            pass

        def bell(self):
            pass

        def get(self, *a):
            if self._var is not None:
                return self._var.get()
            if a:
                return self._text
            return self._val if "values" in self.kw else (1 if self._selected else self._text)

        def set(self, v):
            self._val = v
            self._text = str(v)

        def insert(self, idx, val):
            self._text = str(val)
            if self._var is not None:
                self._var.set(val)

        def delete(self, *a):
            self._text = ""
            if self._var is not None:
                self._var.set("")

        def select(self):
            self._selected = True

        def deselect(self):
            self._selected = False

    tk_mod = types.ModuleType("tkinter")
    tk_font = types.ModuleType("tkinter.font")
    tk_font.families = lambda: ["Prompt", "Noto Sans Thai", "Tahoma"]
    tk_font.nametofont = lambda n: types.SimpleNamespace(actual=lambda k: "Prompt")
    tk_fd = types.ModuleType("tkinter.filedialog")
    tk_fd.askopenfilename = lambda **kw: ""
    tk_mod.font = tk_font
    tk_mod.filedialog = tk_fd

    ctk_mod = types.ModuleType("customtkinter")
    for cls_name in (
        "CTk", "CTkToplevel", "CTkFrame", "CTkScrollableFrame", "CTkLabel",
        "CTkButton", "CTkEntry", "CTkOptionMenu", "CTkSegmentedButton",
        "CTkSwitch", "CTkCheckBox", "CTkTextbox", "CTkProgressBar",
    ):
        setattr(ctk_mod, cls_name, FakeWidget)
    ctk_mod.StringVar = FakeVar
    ctk_mod.CTkFont = lambda **kw: kw
    ctk_mod.CTkImage = lambda **kw: kw
    ctk_mod.set_appearance_mode = lambda m: None
    ctk_mod.set_default_color_theme = lambda t: None

    sys.modules.setdefault("tkinter", tk_mod)
    sys.modules.setdefault("tkinter.font", tk_font)
    sys.modules.setdefault("tkinter.filedialog", tk_fd)
    sys.modules.setdefault("customtkinter", ctk_mod)


_install_nicegui_mock_if_needed()
_install_customtkinter_mock_if_needed()


def _flatten_elements(elements):
    out = []
    for el in elements:
        out.append(el)
        out.extend(_flatten_elements(getattr(el, "children", [])))
    return out


class TonmakhaTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="tonmakha_test_"))
        self._orig_db = config.DB_PATH
        self._orig_uploads = config.UPLOADS_DIR
        self._orig_menu_img = config.MENU_IMAGE_DIR
        self._orig_exports = config.EXPORTS_DIR
        self._orig_qr = config.QR_DIR
        self._orig_backups = config.BACKUPS_DIR
        self._orig_assets = config.ASSETS_DIR
        self._orig_fonts = config.FONTS_DIR

        config.DB_PATH = self.tmp_dir / "test_tonmakha.db"
        config.ASSETS_DIR = self.tmp_dir / "assets"
        config.FONTS_DIR = self._orig_fonts  # keep pointing to real project fonts directory
        config.UPLOADS_DIR = config.ASSETS_DIR / "uploads"
        config.MENU_IMAGE_DIR = config.UPLOADS_DIR / "menu"
        config.QR_DIR = config.ASSETS_DIR / "qr_codes"
        config.EXPORTS_DIR = self.tmp_dir / "exports"
        config.BACKUPS_DIR = self.tmp_dir / "backups"

        for d in (config.ASSETS_DIR, config.UPLOADS_DIR, config.MENU_IMAGE_DIR, config.QR_DIR, config.EXPORTS_DIR, config.BACKUPS_DIR):
            d.mkdir(parents=True, exist_ok=True)

        seed.seed_all()
        shop_service.open_shop(user_id=1)

    def tearDown(self):
        config.DB_PATH = self._orig_db
        config.ASSETS_DIR = self._orig_assets
        config.FONTS_DIR = self._orig_fonts
        config.UPLOADS_DIR = self._orig_uploads
        config.MENU_IMAGE_DIR = self._orig_menu_img
        config.EXPORTS_DIR = self._orig_exports
        config.QR_DIR = self._orig_qr
        config.BACKUPS_DIR = self._orig_backups
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 0. Syntax & Migration Tests
    # ------------------------------------------------------------------
    def test_00_syntax_and_compile_all_files(self):
        py_files = [p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts]
        self.assertGreaterEqual(len(py_files), 40)
        for p in py_files:
            source = p.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(p))
            self.assertIsNotNone(tree)

    def test_01_idempotent_migration_on_existing_db(self):
        orig_db = ROOT / "backups" / "tonmakha_pre_edit_backup.db"
        if not orig_db.exists():
            orig_db = ROOT / "tonmakha.db"
        migrated_db = self.tmp_dir / "migrated_real.db"
        shutil.copy2(orig_db, migrated_db)
        config.DB_PATH = migrated_db

        # รัน create_all ซ้ำ 2 รอบ ต้องไม่พังและไม่ทำข้อมูลเดิมหาย
        schema.create_all()
        schema.create_all()

        bills = checkout_service.list_bills()
        self.assertGreaterEqual(len(bills), 3)
        for b in bills:
            self.assertEqual(b["amount_received"], b["total"])
            self.assertEqual(b["change_amount"], 0.0)

        self.assertEqual(settings_service.get_setting("promptpay_id"), "0123456789")
        self.assertEqual(settings_service.get_setting("promptpay_name"), "นางสาวพะพินพอ เพิ่มพูนพูน")
        self.assertEqual(settings_service.get_float("weigh_price_per_kg"), 299.0)
        self.assertEqual(settings_service.get_float("stock_low_threshold"), 5.0)
        self.assertEqual(settings_service.get_setting("shop_name"), config.APP_NAME)
        self.assertFalse(settings_service.get_bool("shop_tax_id_enabled"))

        weighed_items = [m for m in menu_service.list_items() if m["item_type"] == config.MENU_TYPE_WEIGHED]
        for m in weighed_items:
            self.assertEqual(m["price"], 299.0)

    # ------------------------------------------------------------------
    # 2.1 สต๊อกและหน้าลูกค้า NiceGUI
    # ------------------------------------------------------------------
    def test_02_customer_stock_display_and_out_of_stock_protection(self):
        from nicegui import app, ui
        from web.pages import order as order_page

        t1 = table_service.get_table_by_no(1)
        scan = qr_service.resolve_scan(1, t1["secret_key"], "device_cust_0000001")
        self.assertTrue(scan["ok"])
        sid = scan["session"]["id"]
        table_service.confirm_session(sid, user_id=1)

        water = next(m for m in menu_service.list_items() if m["name"] == "น้ำเปล่า")
        stock_id = water["stock_item_id"]
        cur_stock = stock_service.get_item(stock_id)
        stock_service.adjust(stock_id, -(cur_stock["quantity"] - 3), "ตั้งค่าทดสอบ", user_id=1)

        snap = web_session.get_snapshot(sid)
        cust_water = next(it for cat in snap["menu"] for it in cat["items"] if it["id"] == water["id"])
        self.assertEqual(cust_water["stock_quantity"], 3.0)
        self.assertEqual(cust_water["stock_unit"], "ขวด")
        self.assertIn("คงเหลือ 3 ขวด", cust_water["stock_text"])

        cart = {}
        self.assertEqual(web_session.cart_change_item(cart, snap["menu"], water["id"], 2), 2)
        self.assertEqual(web_session.cart_change_item(cart, snap["menu"], water["id"], 1), 3)
        with self.assertRaises(ValueError) as ctx_err:
            web_session.cart_change_item(cart, snap["menu"], water["id"], 1)
        self.assertIn("สั่งได้สูงสุด 3 ขวด", str(ctx_err.exception))
        self.assertEqual(cart[water["id"]], 3)

        pork = next(m for m in menu_service.list_items() if m["item_type"] == config.MENU_TYPE_WEIGHED)
        with self.assertRaises(ValueError):
            web_session.cart_change_item(cart, snap["menu"], pork["id"], 1)

        stock_service.adjust(stock_id, -3, "ขายหมด", user_id=1)
        snap2 = web_session.get_snapshot(sid)
        self.assertNotEqual(web_session.signature(snap), web_session.signature(snap2))

        ui.reset()
        app.storage.user = {"device_id": "device_cust_0000001", "session_id": sid}
        state = {"cart": dict(cart), "tab": "menu", "cat": water["category_id"]}
        order_page.render(snap2, {"session_id": sid, "device_id": "device_cust_0000001"}, state, lambda: None)

        self.assertNotIn(water["id"], state["cart"])
        all_els = _flatten_elements(ui.elements)
        badges = [e.text for e in all_els if getattr(e, "kind", "") == "badge"]
        self.assertIn("สินค้าหมด", badges)

        with self.assertRaises(ValueError) as err_zero:
            web_session.cart_change_item(state["cart"], snap2["menu"], water["id"], 1)
        self.assertIn("สินค้าหมด", str(err_zero.exception))

        veg = next(m for m in menu_service.list_items() if m["name"] == "ผักรวม")
        menu_service.set_sold_out(veg["id"], True, user_id=1)
        snap3 = web_session.get_snapshot(sid)
        with self.assertRaises(ValueError):
            web_session.cart_change_item(state["cart"], snap3["menu"], veg["id"], 1)
        with self.assertRaises(ValueError):
            order_service.create_order(sid, [{"menu_item_id": veg["id"], "quantity": 1}])

    def test_03_stock_changed_after_page_open_and_concurrent_last_item(self):
        t1 = table_service.get_table_by_no(1)
        t2 = table_service.get_table_by_no(2)
        s1 = qr_service.resolve_scan(1, t1["secret_key"], "device_table_1_aaaa")["session"]["id"]
        s2 = qr_service.resolve_scan(2, t2["secret_key"], "device_table_2_bbbb")["session"]["id"]
        table_service.confirm_session(s1, user_id=1)
        table_service.confirm_session(s2, user_id=1)

        coke = next(m for m in menu_service.list_items() if m["name"] == "โค้ก")
        egg = next(m for m in menu_service.list_items() if m["name"] == "ไข่ไก่")
        st_coke = stock_service.get_item(coke["stock_item_id"])
        stock_service.adjust(coke["stock_item_id"], -(st_coke["quantity"] - 1), "เหลือขวดสุดท้าย", user_id=1)

        cart_t1 = {coke["id"]: 2, egg["id"]: 1}
        with self.assertRaises(ValueError) as err_over:
            web_session.place_order(s1, "device_table_1_aaaa", cart_t1)
        self.assertIn("เหลือไม่พอ", str(err_over.exception))
        self.assertEqual(cart_t1, {coke["id"]: 2, egg["id"]: 1})
        self.assertEqual(stock_service.get_item(coke["stock_item_id"])["quantity"], 1.0)

        def _try_order(sess_id, dev_id):
            try:
                return ("ok", web_session.place_order(sess_id, dev_id, {coke["id"]: 1}))
            except ValueError as e:
                return ("err", str(e))

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_try_order, s1, "device_table_1_aaaa")
            f2 = pool.submit(_try_order, s2, "device_table_2_bbbb")
            results = [f1.result(), f2.result()]

        oks = [r for r in results if r[0] == "ok"]
        errs = [r for r in results if r[0] == "err"]
        self.assertEqual(len(oks), 1)
        self.assertEqual(len(errs), 1)
        after_stock = stock_service.get_item(coke["stock_item_id"])
        self.assertEqual(after_stock["quantity"], 0.0)
        self.assertTrue(menu_service.get_item(coke["id"])["is_sold_out"])

    # ------------------------------------------------------------------
    # 2.2 แจ้งเตือนสต๊อกใกล้หมดและสินค้าหมด
    # ------------------------------------------------------------------
    def test_04_stock_alerts_threshold_dedup_and_recovery(self):
        settings_service.set_setting("stock_low_threshold", 5, user_id=1)
        item = stock_service.add_item("ลูกชิ้นปลา", "ถุง", quantity=10, min_quantity=0, user_id=1)
        sid = item["id"]

        res0 = alert_service.check_alerts()
        self.assertFalse(any(a["stock_item_id"] == sid for a in res0["new"]))

        stock_service.adjust(sid, -5, "เบิกใช้", user_id=1)
        res1 = alert_service.check_alerts()
        new_alerts = [a for a in res1["new"] if a["stock_item_id"] == sid]
        self.assertEqual(len(new_alerts), 1)
        self.assertEqual(new_alerts[0]["kind"], alert_service.KIND_LOW_STOCK)
        self.assertEqual(new_alerts[0]["message"], "สต๊อกใกล้หมด: ลูกชิ้นปลา เหลือ 5 ถุง")

        res_dup = alert_service.check_alerts()
        self.assertEqual(len([a for a in res_dup["new"] if a["stock_item_id"] == sid]), 0)

        alert_service.mark_checked(new_alerts[0]["id"], user_id=1)
        res_after_check = alert_service.check_alerts()
        self.assertEqual(len([a for a in res_after_check["new"] if a["stock_item_id"] == sid]), 0)

        stock_service.adjust(sid, -5, "ใช้หมด", user_id=1)
        res_zero = alert_service.check_alerts()
        out_alerts = [a for a in res_zero["new"] if a["stock_item_id"] == sid]
        self.assertEqual(len(out_alerts), 1)
        self.assertEqual(out_alerts[0]["kind"], alert_service.KIND_OUT_OF_STOCK)
        self.assertEqual(out_alerts[0]["message"], "สินค้าหมด: ลูกชิ้นปลา เหลือ 0 ถุง")

        self.assertEqual(len([a for a in alert_service.check_alerts()["new"] if a["stock_item_id"] == sid]), 0)

        stock_service.restock(sid, 10, user_id=1)
        self.assertEqual(stock_service.get_item(sid)["alert_level"], "normal")
        active_for_item = [a for a in alert_service.list_active_alerts() if a["stock_item_id"] == sid]
        self.assertEqual(len(active_for_item), 0)

        stock_service.adjust(sid, -6, "ขายรอบใหม่", user_id=1)
        res_again = alert_service.check_alerts()
        again_alerts = [a for a in res_again["new"] if a["stock_item_id"] == sid]
        self.assertEqual(len(again_alerts), 1)
        self.assertEqual(again_alerts[0]["kind"], alert_service.KIND_LOW_STOCK)
        self.assertEqual(again_alerts[0]["message"], "สต๊อกใกล้หมด: ลูกชิ้นปลา เหลือ 4 ถุง")

    # ------------------------------------------------------------------
    # 2.3 รูปสินค้าในแต่ละเมนู
    # ------------------------------------------------------------------
    def test_05_menu_images_upload_crop_validation_and_delete(self):
        veg = next(m for m in menu_service.list_items() if m["name"] == "ผักรวม")
        egg = next(m for m in menu_service.list_items() if m["name"] == "ไข่ไก่")

        img_rect = Image.new("RGB", (800, 500), (220, 100, 50))
        buf = BytesIO()
        img_rect.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        with self.assertRaises(ValueError):
            menu_service.set_item_image(veg["id"], png_bytes, original_filename="veg.png", user_id=2)

        updated = menu_service.set_item_image(veg["id"], png_bytes, original_filename="veg.png", user_id=1)
        self.assertTrue(updated["has_image"])
        self.assertIsNotNone(updated["image_path"])
        self.assertTrue(updated["image_url"].startswith("/uploads/menu/"))
        saved_file = menu_service.get_item_image_file(updated)
        self.assertIsNotNone(saved_file)
        with Image.open(saved_file) as im:
            self.assertEqual(im.width, im.height)
            self.assertLessEqual(im.width, config.MENU_IMAGE_MAX_DIM)

        cust_menu = menu_service.get_menu_for_customer()
        cust_veg = next(it for cat in cust_menu for it in cat["items"] if it["id"] == veg["id"])
        cust_egg = next(it for cat in cust_menu for it in cat["items"] if it["id"] == egg["id"])
        self.assertEqual(cust_veg["image_url"], updated["image_url"])
        self.assertIsNone(cust_egg["image_url"])

        with self.assertRaises(ValueError):
            menu_service.set_item_image(veg["id"], b"not an image", original_filename="bad.png", user_id=1)
        with self.assertRaises(ValueError):
            menu_service.set_item_image(veg["id"], png_bytes, original_filename="hack.exe", user_id=1)
        with self.assertRaises(ValueError):
            menu_service.set_item_image(veg["id"], b"x" * (config.MAX_IMAGE_SIZE_BYTES + 10), original_filename="big.jpg", user_id=1)

        db.execute("UPDATE menu_items SET image_path = ? WHERE id = ?", (updated["image_path"], egg["id"]))
        menu_service.delete_item_image(veg["id"], user_id=1)
        self.assertFalse(menu_service.get_item(veg["id"])["has_image"])
        self.assertTrue(saved_file.exists())

        menu_service.delete_item_image(egg["id"], user_id=1)
        self.assertFalse(menu_service.get_item(egg["id"])["has_image"])
        self.assertFalse(saved_file.exists())

    # ------------------------------------------------------------------
    # 2.4, 2.5, 2.6 ชำระเงิน (2 รูปแบบ), PromptPay QR และใบเสร็จ PDF/TXT
    # ------------------------------------------------------------------
    def test_06_checkout_validation_promptpay_qr_and_receipts(self):
        t1 = table_service.get_table_by_no(1)
        s1 = qr_service.resolve_scan(1, t1["secret_key"], "dev_checkout_1111")["session"]["id"]
        table_service.confirm_session(s1, user_id=1)

        # ชั่งหมูกระทะ 1 กก. (299 บาท) + สั่งน้ำเปล่า 1 ขวด (15 บาท) = 314.00 บาท
        weigh_service.add_entry(s1, None, 1000, user_id=1)
        water = next(m for m in menu_service.list_items() if m["name"] == "น้ำเปล่า")
        order = order_service.create_order(s1, [{"menu_item_id": water["id"], "quantity": 1}])
        order_service.set_order_status(order["id"], "served", user_id=1)

        bill_prev = checkout_service.start_checkout(s1, user_id=1)
        self.assertEqual(bill_prev["subtotal"], 314.0)
        self.assertEqual(bill_prev["total"], 314.0)

        # ตรวจสอบว่าไม่สามารถชำระเงินแบบบัตร ('card') ได้อีกต่อไป
        with self.assertRaises(ValueError):
            checkout_service.pay(s1, "card", user_id=1)
        with self.assertRaises(ValueError):
            checkout_service.validate_payment(314.0, "card")

        # ตรวจสอบยอดเงินสดรับ: ติดลบ / ตัวอักษร / ค่าว่าง / ต่ำกว่ายอดชำระ ต้องไม่ผ่าน
        for invalid_val in (-100, "abc", "", None, 200.00, 313.99):
            with self.assertRaises(ValueError):
                checkout_service.pay(s1, "cash", user_id=1, amount_received=invalid_val)
            self.assertEqual(table_service.get_session(s1)["status"], config.SESSION_AWAITING_PAYMENT)
            self.assertIsNone(checkout_service.get_bill(s1))

        v_exact = checkout_service.validate_payment(314.0, "cash", amount_received="314.00")
        self.assertEqual(v_exact["change_amount"], 0.0)
        v_more = checkout_service.validate_payment(314.0, "cash", amount_received="500")
        self.assertEqual(v_more["change_amount"], 186.0)

        qr_200 = qr_service.generate_promptpay_qr(200)
        self.assertEqual(qr_200["promptpay_id"], "0123456789")
        self.assertEqual(qr_200["promptpay_name"], "นางสาวพะพินพอ เพิ่มพูนพูน")
        self.assertEqual(qr_200["amount"], 200.0)
        self.assertEqual(qr_200["status_th"], "รอตรวจสอบการโอน")
        self.assertIn("5406200.00", qr_200["payload"])
        self.assertTrue(qr_service.verify_promptpay_payload(qr_200["payload"], expected_amount=200))

        qr_bill = qr_service.generate_promptpay_qr(bill_prev["total"])
        self.assertIn("5406314.00", qr_bill["payload"])
        self.assertEqual(table_service.get_session(s1)["status"], config.SESSION_AWAITING_PAYMENT)
        self.assertIsNone(checkout_service.get_bill(s1))

        for bad_pp in ("", "abc1234567", "08123", "1234567890"):
            with self.assertRaises(ValueError):
                qr_service.generate_promptpay_qr(200, promptpay_id=bad_pp)

        # ตั้งค่าข้อมูลร้านสำหรับใบเสร็จ (เปิดแสดงเลขผู้เสียภาษี + ที่อยู่ + เบอร์โทร)
        settings_service.set_many({
            "shop_name": "ต้นมะค่า แคมป์ปิ้งบาร์หมูกระทะ",
            "shop_tax_id": "1234567890123",
            "shop_tax_id_enabled": True,
            "shop_address": "99 หมู่ที่ 1",
            "shop_subdistrict": "วังตะเฆ่",
            "shop_district": "หนองบัวระเหว",
            "shop_province": "ชัยภูมิ",
            "shop_postal_code": "36250",
            "shop_phone": "012-345-6789",
        }, user_id=1)

        # ชำระจริงด้วยเงินสด (รับ 400.00 ทอน 86.00) โดยเจ้าของร้าน (user_id=1)
        paid_cash = checkout_service.pay(s1, "cash", user_id=1, amount_received=400.0)
        self.assertEqual(paid_cash["total"], 314.0)
        self.assertEqual(paid_cash["amount_received"], 400.0)
        self.assertEqual(paid_cash["change_amount"], 86.0)
        self.assertEqual(paid_cash["cashier_name"], "เจ้าของร้าน")
        self.assertEqual(table_service.get_session(s1)["status"], config.SESSION_CLOSED)

        with self.assertRaises(ValueError):
            checkout_service.pay(s1, "cash", user_id=1, amount_received=400.0)

        txt_path = checkout_service.export_receipt_txt(paid_cash)
        pdf_path = checkout_service.export_receipt_pdf(paid_cash)
        self.assertTrue(txt_path.exists())
        self.assertTrue(pdf_path.exists())
        txt_content = txt_path.read_text(encoding="utf-8")
        self.assertIn("ต้นมะค่า แคมป์ปิ้งบาร์หมูกระทะ", txt_content)
        self.assertIn("เลขผู้เสียภาษี 1234567890123", txt_content)
        self.assertIn("ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน", txt_content)
        self.assertIn("99 หมู่ที่ 1 ต.วังตะเฆ่ อ.หนองบัวระเหว", txt_content)
        self.assertIn("จ.ชัยภูมิ 36250", txt_content)
        self.assertIn("โทร.012-345-6789", txt_content)
        self.assertIn("พนักงานขาย   เจ้าของร้าน", txt_content)
        self.assertIn("รวมเป็นเงิน", txt_content)
        self.assertIn("จำนวนเงินหลังหักส่วนลด", txt_content)
        self.assertIn("ราคาไม่รวมภาษีมูลค่าเพิ่ม", txt_content)
        self.assertIn("ภาษีมูลค่าเพิ่ม 7%", txt_content)
        self.assertIn("รวมทั้งสิ้น", txt_content)
        self.assertIn("ช่องทางการชำระ :   เงินสด", txt_content)
        self.assertIn("รับเงินมา", txt_content)
        self.assertIn("เงินทอน", txt_content)
        self.assertIn("400.00 บาท", txt_content)
        self.assertIn("86.00 บาท", txt_content)
        self.assertIn("ขอบคุณที่ใช้บริการ", txt_content)

        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        self.assertIn("ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน", pdf_text)
        self.assertIn("เลขผู้เสียภาษี 1234567890123", pdf_text)
        self.assertIn("314.00", pdf_text)
        self.assertIn("400.00", pdf_text)
        self.assertIn("86.00", pdf_text)

        # ปิดการแสดงเลขผู้เสียภาษี และทดสอบบิลชำระด้วย โอน/PromptPay (โต๊ะ 2, ชั่งครั้งแรก 1.00 กก. = 299.00 บาท, พนักงานขาย staff1 user_id=2)
        settings_service.set_setting("shop_tax_id_enabled", False, user_id=1)
        t2 = table_service.get_table_by_no(2)
        s2 = qr_service.resolve_scan(2, t2["secret_key"], "dev_checkout_2222")["session"]["id"]
        table_service.confirm_session(s2, user_id=2)
        weigh_service.add_entry(s2, None, 1000, user_id=2)  # 1.0 กก. * 299 = 299.00 บาท
        checkout_service.start_checkout(s2, user_id=2)
        paid_pp = checkout_service.pay(s2, "promptpay", user_id=2)
        self.assertEqual(paid_pp["payment_method"], "transfer")
        self.assertEqual(paid_pp["payment_method_th"], "โอน/PromptPay")
        self.assertEqual(paid_pp["cashier_name"], "พนักงาน 1")
        self.assertEqual(paid_pp["total"], 299.00)
        self.assertEqual(paid_pp["amount_received"], 299.00)
        self.assertEqual(paid_pp["change_amount"], 0.0)

        pp_txt = checkout_service.export_receipt_txt(paid_pp).read_text(encoding="utf-8")
        self.assertNotIn("เลขผู้เสียภาษี", pp_txt)
        self.assertIn("พนักงานขาย   พนักงาน 1", pp_txt)
        self.assertIn("ช่องทางการชำระ :   โอน/PromptPay", pp_txt)
        # กรณีโอน/PromptPay ต้องไม่มีบรรทัดเงินทอนในใบเสร็จ
        self.assertNotIn("เงินทอน", pp_txt)
        self.assertNotIn("รับเงินมา", pp_txt)

    # ------------------------------------------------------------------
    # 2.7 เงื่อนไขการชั่งน้ำหนักครั้งแรก >= 1 กก. และ 2.8 การลบสต๊อก/เมนู
    # ------------------------------------------------------------------
    def test_07_weigh_first_time_rule_and_menu_stock_deletion(self):
        t1 = table_service.get_table_by_no(1)
        t2 = table_service.get_table_by_no(2)
        s1 = qr_service.resolve_scan(1, t1["secret_key"], "dev_w_t1")["session"]["id"]
        s2 = qr_service.resolve_scan(2, t2["secret_key"], "dev_w_t2")["session"]["id"]
        table_service.confirm_session(s1, user_id=1)
        table_service.confirm_session(s2, user_id=1)

        # สถานการณ์ 1: โต๊ะ 1 ชั่งครั้งแรก 0.50 กก. (500 กรัม) -> ไม่อนุญาตให้บันทึก
        self.assertTrue(weigh_service.is_first_weigh(s1))
        with self.assertRaises(ValueError) as err1:
            weigh_service.add_entry(s1, None, 500, user_id=1)
        self.assertIn("การชั่งครั้งแรกของโต๊ะต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม", str(err1.exception))
        self.assertEqual(len(weigh_service.list_entries(s1)), 0)

        # สถานการณ์ 2: โต๊ะ 1 ชั่งครั้งแรก 1.00 กก. (1,000 กรัม) -> อนุญาตให้บันทึก
        e1 = weigh_service.add_entry(s1, None, 1000, user_id=1)
        self.assertEqual(e1["weight_grams"], 1000)
        self.assertFalse(weigh_service.is_first_weigh(s1))

        # สถานการณ์ 3: โต๊ะ 1 ชั่งครั้งที่สอง 0.20 กก. (200 กรัม) -> อนุญาตให้บันทึก
        e2 = weigh_service.add_entry(s1, None, 200, user_id=1)
        self.assertEqual(e2["weight_grams"], 200)
        self.assertEqual(len(weigh_service.list_entries(s1)), 2)

        # สถานการณ์ 4: โต๊ะ 2 ยังไม่เคยชั่ง ชั่ง 0.80 กก. (800 กรัม) -> ไม่อนุญาตให้บันทึก (แยกสถานะตามโต๊ะ)
        self.assertTrue(weigh_service.is_first_weigh(s2))
        with self.assertRaises(ValueError) as err2:
            weigh_service.add_entry(s2, None, 800, user_id=1)
        self.assertIn("การชั่งครั้งแรกของโต๊ะต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม", str(err2.exception))

        # สถานการณ์ 5: โต๊ะ 2 ชั่งครั้งแรก 1.50 กก. (1,500 กรัม) -> อนุญาตให้บันทึก
        e_t2 = weigh_service.add_entry(s2, None, 1500, user_id=1)
        self.assertEqual(e_t2["weight_grams"], 1500)
        self.assertFalse(weigh_service.is_first_weigh(s2))

        # หากโต๊ะ 2 ยกเลิกรายการชั่งครั้งแรกออกจนไม่เหลือรายการ active -> ต้องกลับมาตรวจเงื่อนไขครั้งแรกใหม่
        weigh_service.cancel_entry(e_t2["id"], "ชั่งผิดโต๊ะ", user_id=1)
        self.assertTrue(weigh_service.is_first_weigh(s2))
        with self.assertRaises(ValueError):
            weigh_service.add_entry(s2, None, 600, user_id=1)

        # สถานการณ์ 6: โต๊ะ 1 ปิดบิลแล้วเริ่มรอบใหม่ -> ต้องตรวจเงื่อนไขครั้งแรกใหม่
        checkout_service.start_checkout(s1, user_id=1)
        checkout_service.pay(s1, "cash", user_id=1, amount_received=500.0)
        s1_new = qr_service.resolve_scan(1, t1["secret_key"], "dev_w_t1_round2")["session"]["id"]
        table_service.confirm_session(s1_new, user_id=1)
        self.assertTrue(weigh_service.is_first_weigh(s1_new))
        with self.assertRaises(ValueError):
            weigh_service.add_entry(s1_new, None, 500, user_id=1)
        e_new_ok = weigh_service.add_entry(s1_new, None, 1000, user_id=1)
        self.assertEqual(e_new_ok["weight_grams"], 1000)

        # ทดสอบข้อ 5: ลบรายการเมนูในหน้า "เมนูและราคา"
        temp_menu = menu_service.add_item(2, "เห็ดเข็มทองทดสอบ", config.MENU_TYPE_NORMAL, 25, user_id=1)
        del_res = menu_service.delete_item(temp_menu["id"], user_id=1)
        self.assertTrue(del_res["deleted"])
        self.assertIsNone(menu_service.get_item(temp_menu["id"]))

        pork_del = menu_service.delete_item(1, user_id=1)
        self.assertFalse(pork_del["deleted"])
        self.assertTrue(pork_del["soft_deleted"])
        self.assertFalse(menu_service.get_item(1)["active"])
        cust_ids = [it["id"] for cat in menu_service.get_menu_for_customer() for it in cat["items"]]
        self.assertNotIn(1, cust_ids)

        unused = stock_service.add_item("ถ้วยกระดาษทดสอบ", "ใบ", quantity=0, min_quantity=5, user_id=1)
        with self.assertRaises(ValueError):
            stock_service.delete_item(unused["id"], user_id=2)
        res_del = stock_service.delete_item(unused["id"], user_id=1)
        self.assertTrue(res_del["deleted"])

    # ------------------------------------------------------------------
    # 3. Full E2E Regression
    # ------------------------------------------------------------------
    def test_08_full_regression_and_ui_smoke(self):
        owner = auth_service.login("owner", "owner1234")
        self.assertIsNotNone(owner)
        self.assertTrue(auth_service.is_owner(owner))
        staff = auth_service.login("staff1", "staff1234")
        self.assertIsNotNone(staff)
        self.assertFalse(auth_service.is_owner(staff))
        self.assertIsNone(auth_service.login("owner", "wrongpass"))

        qr_paths = qr_service.generate_all_qr()
        self.assertEqual(len(qr_paths), 10)
        t3 = table_service.get_table_by_no(3)
        scan = qr_service.resolve_scan(3, t3["secret_key"], "dev_reg_table3")
        self.assertTrue(scan["ok"])
        sid = scan["session"]["id"]

        future_a = datetime.now() + timedelta(minutes=10)
        alerts_a = alert_service.check_alerts(now=future_a)
        self.assertTrue(any(a["session_id"] == sid and a["kind"] == alert_service.KIND_PENDING for a in alerts_a["new"]))
        sound_a = alert_service.pop_sound_alerts()
        self.assertGreaterEqual(len(sound_a), 1)
        self.assertEqual(len(alert_service.pop_sound_alerts()), 0)

        table_service.confirm_session(sid, user_id=staff["id"])
        alerts_clear = alert_service.check_alerts(now=datetime.now())
        self.assertTrue(any(a["session_id"] == sid for a in alerts_clear["cleared"]))

        future_b = datetime.now() + timedelta(minutes=15)
        alerts_b = alert_service.check_alerts(now=future_b)
        b_alert = next(a for a in alerts_b["new"] if a["session_id"] == sid and a["kind"] == alert_service.KIND_IDLE_OPEN)
        alert_service.snooze(b_alert["id"], user_id=staff["id"], now=future_b)
        woken = alert_service.check_alerts(now=future_b + timedelta(minutes=10))
        self.assertTrue(any(a["id"] == b_alert["id"] for a in woken["woken"]))
        alert_service.mark_checked(b_alert["id"], user_id=staff["id"])

        settings_service.set_many({
            "service_charge_enabled": True,
            "service_charge_percent": 10,
            "vat_enabled": True,
            "vat_percent": 7,
        }, user_id=owner["id"])
        promo = promo_service.add_promo("ลด 10%", "percent", 10, min_amount=100, user_id=owner["id"])

        w_entry = weigh_service.add_entry(sid, None, 1000, user_id=staff["id"])  # 299.00
        self.assertEqual(w_entry["amount"], 299.0)

        water = next(m for m in menu_service.list_items() if m["name"] == "น้ำเปล่า")
        ord1 = order_service.create_order(sid, [{"menu_item_id": water["id"], "quantity": 2}], user_id=staff["id"])
        self.assertEqual(len(order_service.list_active_orders()), 1)
        order_service.cancel_item(ord1["items"][0]["id"], "ลูกค้าเปลี่ยนใจ", user_id=staff["id"])
        self.assertGreaterEqual(notice_service.unread_count(sid), 1)

        ord2 = order_service.create_order(sid, [{"menu_item_id": water["id"], "quantity": 1}], user_id=staff["id"])
        order_service.set_order_status(ord2["id"], "preparing", user_id=staff["id"])
        order_service.set_order_status(ord2["id"], "served", user_id=staff["id"])

        checkout_service.start_checkout(sid, user_id=staff["id"])
        prev = checkout_service.preview(sid, promo_id=promo["id"])
        self.assertEqual(prev["subtotal"], 314.0)
        self.assertEqual(prev["discount"], 31.4)
        self.assertEqual(prev["service_charge"], 28.26)
        self.assertEqual(prev["vat"], 21.76)
        self.assertEqual(prev["total"], 332.62)

        paid = checkout_service.pay(sid, "cash", user_id=staff["id"], promo_id=promo["id"], amount_received=400.0)
        self.assertEqual(paid["total"], 332.62)
        self.assertEqual(paid["amount_received"], 400.0)
        self.assertEqual(paid["change_amount"], 67.38)

        overview = report_service.today_overview()
        self.assertGreaterEqual(overview["sales"]["bill_count"], 1)
        csv_path = report_service.export_sales_csv()
        self.assertTrue(csv_path.exists())
        csv_text = csv_path.read_text(encoding="utf-8-sig")
        self.assertIn("ภาษีมูลค่าเพิ่ม", csv_text)

        shop_service.close_shop(user_id=owner["id"])
        bkp = backup_service.create_backup(user_id=owner["id"])
        self.assertTrue(bkp["path"].exists())

    # ------------------------------------------------------------------
    # 4. All 9 Requirements UI & Integration Smoke Tests
    # ------------------------------------------------------------------
    def test_09_all_nine_requirements_ui_and_integration(self):
        from ui import theme
        from ui.app import App, NAV_ITEMS
        from ui.owner._common import be_to_ce_year, ce_to_be_year, format_thai_date, parse_date
        from ui.widgets.order_card import OrderCard

        # ข้อ 1: ตรวจสอบฟอนต์ Prompt
        self.assertEqual(theme.PRIMARY_FONT_FAMILY, "Prompt")
        self.assertEqual(theme.font_family(), "Prompt")
        self.assertTrue((ROOT / "assets" / "fonts" / "Prompt-Regular.ttf").exists())
        self.assertTrue((ROOT / "assets" / "fonts" / "Prompt-Bold.ttf").exists())

        # ข้อ 7 & 8: ตรวจสอบเมนูนำทาง (ไม่มี kitchen และไม่มี report แยกต่างหาก)
        nav_keys = [item.key for item in NAV_ITEMS]
        self.assertNotIn("kitchen", nav_keys)
        self.assertNotIn("report", nav_keys)
        self.assertIn("dashboard", nav_keys)

        owner = auth_service.login("owner", "owner1234")
        app = App()
        app.on_login(owner)

        # เปิดครบทุกหน้าใน NAV_ITEMS
        for nav in NAV_ITEMS:
            app.navigate(nav.key)
            page = app.pages[nav.key]
            self.assertNotEqual(page.__class__.__name__, "PlaceholderPage", f"Page {nav.key} failed to load")
            page.refresh()

        # ทดสอบว่า navigate('kitchen') ไม่เปิดหน้าจอครัว และ navigate('report') พาไป 'dashboard'
        app.navigate("tables")
        app.navigate("kitchen")
        self.assertEqual(app.current_key, "tables")
        app.navigate("report")
        self.assertEqual(app.current_key, "dashboard")

        # ข้อ 2: หน้าชั่งน้ำหนัก — ครั้งแรก < 1 กก. ต้องไม่ผ่าน, >= 1 กก. ผ่าน, ครั้งถัดไป < 1 กก. ผ่าน
        t1 = table_service.get_table_by_no(1)
        s1 = qr_service.resolve_scan(1, t1["secret_key"], "dev_ui_test_1")["session"]["id"]
        table_service.confirm_session(s1, user_id=owner["id"])
        app.navigate("weigh", session_id=s1)
        w_page = app.pages["weigh"]
        w_page.weight_var.set("5")  # 5 ขีด = 500 กรัม (< 1 กก. สำหรับครั้งแรก)
        w_page.save()
        self.assertEqual(weigh_service.session_total(s1), 0.0)

        w_page.weight_var.set("10")  # 10 ขีด = 1,000 กรัม (1 กก.)
        w_page.save()
        self.assertEqual(weigh_service.session_total(s1), 299.0)

        w_page.weight_var.set("2")  # ครั้งที่สอง 2 ขีด = 200 กรัม
        w_page.save()
        self.assertEqual(weigh_service.session_total(s1), round(299.0 + 59.8, 2))

        # ข้อ 6: หน้าออเดอร์และ OrderCard — แสดงทีละปุ่มตามลำดับ (เริ่มทำ -> เสิร์ฟแล้ว) และไม่มีปุ่มยกเลิก
        water = next(m for m in menu_service.list_items() if m["name"] == "น้ำเปล่า")
        ord_new = order_service.create_order(s1, [{"menu_item_id": water["id"], "quantity": 1}], user_id=owner["id"])
        app.navigate("orders", session_id=s1)
        o_page = app.pages["orders"]

        card_new = OrderCard(o_page.area, ord_new, on_status=o_page.set_status)
        self.assertTrue(hasattr(card_new, "action_btn"))
        self.assertEqual(card_new.action_btn.cget("text"), "เริ่มทำ")

        o_page.set_status(ord_new, "preparing")
        ord_prep = order_service.get_order(ord_new["id"])
        self.assertEqual(ord_prep["status"], "preparing")
        card_prep = OrderCard(o_page.area, ord_prep, on_status=o_page.set_status)
        self.assertTrue(hasattr(card_prep, "action_btn"))
        self.assertEqual(card_prep.action_btn.cget("text"), "เสิร์ฟแล้ว")

        o_page.set_status(ord_prep, "served")
        ord_served = order_service.get_order(ord_new["id"])
        self.assertEqual(ord_served["status"], "served")
        card_served = OrderCard(o_page.area, ord_served, on_status=o_page.set_status)
        self.assertFalse(hasattr(card_served, "action_btn"))

        # ข้อ 3: หน้าเช็คเอาท์ — มีเฉพาะ เงินสด และ โอน/PromptPay (ไม่มีบัตร)
        checkout_service.start_checkout(s1, user_id=owner["id"])
        app.navigate("checkout", session_id=s1)
        c_page = app.pages["checkout"]
        from ui.staff.checkout_page import METHOD_LABELS
        self.assertEqual(METHOD_LABELS, ["เงินสด", "โอน/PromptPay"])
        self.assertNotIn("บัตร", METHOD_LABELS)

        c_page.method.set("เงินสด")
        c_page._on_method_changed()
        c_page.cash_var.set("100")
        ok_cash, _, _, _ = c_page._parse_cash_status()
        self.assertFalse(ok_cash)
        c_page.cash_var.set("500")
        ok_cash2, rec_d, chg_d, _ = c_page._parse_cash_status()
        self.assertTrue(ok_cash2)

        c_page.method.set("โอน/PromptPay")
        c_page._on_method_changed()
        self.assertTrue(c_page._qr_valid)
        self.assertEqual(c_page.change_label.cget("text"), "")

        # ข้อ 8: แดชบอร์ดรวมรายงาน + ปฏิทิน พ.ศ.
        self.assertEqual(ce_to_be_year(2026), 2569)
        self.assertEqual(ce_to_be_year(2569), 2569)
        self.assertEqual(be_to_ce_year(2569), 2026)
        self.assertEqual(be_to_ce_year(2026), 2026)
        self.assertEqual(parse_date("24/10/2569", "วันที่"), "2026-10-24")
        self.assertIn("2569", format_thai_date("2026-10-24"))

        app.navigate("dashboard")
        d_page = app.pages["dashboard"]
        d_page.date_from.set("2026-10-01")
        d_page.date_to.set("2026-10-31")
        d_page.show_report()
        self.assertEqual(d_page.range, ("2026-10-01", "2026-10-31"))

        # ข้อ 9: ตรวจสอบการจัดแนวคอลัมน์ในตารางทุกหน้าตามข้อกำหนดใน PDF
        expected_centers = {
            "menu": {"has_image", "status"},
            "stock": {"status"},
            "promo": {"status"},
            "tables_manage": {"status"},
            "users": {"status"},
            "log": set(),
            "backup": set(),
        }
        for page_key, center_keys in expected_centers.items():
            p = app.pages[page_key]
            for col in p.table.columns:
                expected_anchor = "center" if col["key"] in center_keys else "w"
                self.assertEqual(
                    col.get("anchor", "w"),
                    expected_anchor,
                    f"Page '{page_key}' column '{col['key']}' anchor should be '{expected_anchor}'",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
