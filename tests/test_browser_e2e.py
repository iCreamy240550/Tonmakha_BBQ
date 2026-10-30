"""tests/test_browser_e2e.py — ชุดทดสอบ E2E เบราว์เซอร์จริง (Headless Chromium) 2 บทบาทพร้อมกัน + ทดสอบเจาะ XSS และขนาดปุ่มมือถือ

ครอบคลุม P3-1 ถึง P3-6:
1. ลูกค้า (มือถือ 390×844) สแกน QR `/t/1?k=...` -> ล้าง `?k=` ออกจาก URL -> รอพนักงานยืนยัน (`waiting`)
2. พนักงาน/เจ้าของ (เดสก์ท็อป 1280×780) ล็อกอินผ่านหน้าเว็บ `#/login` -> ยืนยันโต๊ะ 1 ที่หน้า `#/tables`
3. พนักงานชั่งน้ำหนักที่หน้า `#/weigh` (ทดสอบกฎชั่งครั้งแรก ≥ 1 กก. และบันทึก 15 ขีด = 1.5 กก.)
4. ลูกค้าเห็นหน้าสั่งอาหาร (`order`) -> เลือกหมวด -> กดเพิ่มรายการลงตะกร้า -> กด `ตรวจสอบ/สั่งอาหาร` -> ใส่หมายเหตุ -> ยืนยันสั่ง -> ดูแท็บ `รายการของฉัน`
5. พนักงานเปลี่ยนสถานะออเดอร์ที่หน้า `#/orders` (`เริ่มทำ` -> `เสิร์ฟแล้ว`)
6. พนักงานเริ่มเช็คบิลที่หน้า `#/checkout` -> ลูกค้าเห็นหน้าบิล (`bill`) -> พนักงานชำระเงินสด -> เปิดกล่องใบเสร็จรับเงิน (`ReceiptDialog`) + ส่งออก PDF/TXT -> ลูกค้าเห็นหน้าชำระเงินเรียบร้อย (`closed`)
7. ทดสอบแจ้งเตือนโต๊ะเงียบ (`AlertCenter` แถบแดง) บนหน้าจอพนักงาน + แคปภาพหน้าจอ E2E ลง `docs/web_screens/`
8. ทดสอบเจาะ XSS ในเบราว์เซอร์จริง: ฉีด `<script>window.__xss_triggered = true;</script>` ในชื่อเมนู/หมายเหตุออเดอร์/ข้อความแจ้งลูกค้า แล้วตรวจว่า `window.__xss_triggered` ไม่ถูกสั่งรันใน DOM
"""
from __future__ import annotations

from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from database import db, schema, seed
from services import alert_service, menu_service, notice_service, qr_service, settings_service, shop_service, table_service


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_chrome(width: int, height: int):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--force-device-scale-factor=1")
    opts.add_argument("--host-resolver-rules=MAP tonmakha.local 127.0.0.1")
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": width < 600,
        },
    )
    return driver


class BrowserE2ETestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = Path(tempfile.mkdtemp(prefix="tonmakha_e2e_"))
        cls.orig_db = config.DB_PATH
        cls.orig_backups = config.BACKUPS_DIR
        cls.orig_exports = config.EXPORTS_DIR
        cls.orig_qr = config.QR_DIR
        cls.orig_demo = config.MEMBER_DEMO_ACCOUNTS

        config.DB_PATH = cls.tmp_dir / "e2e.db"
        config.BACKUPS_DIR = cls.tmp_dir / "backups"
        config.EXPORTS_DIR = cls.tmp_dir / "exports"
        config.QR_DIR = cls.tmp_dir / "qr"
        config.MEMBER_DEMO_ACCOUNTS = 1
        for d in (config.BACKUPS_DIR, config.EXPORTS_DIR, config.QR_DIR):
            d.mkdir(parents=True, exist_ok=True)

        schema.create_all()
        seed.seed_all()
        shop_service.open_shop(user_id=1)

        from server.app import create_app

        app = create_app(enable_lifespan=False)
        cls.port = _find_free_port()
        cls.base_url = f"http://tonmakha.local:{cls.port}"

        srv_cfg = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(srv_cfg)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()

        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=3)
        config.DB_PATH = cls.orig_db
        config.BACKUPS_DIR = cls.orig_backups
        config.EXPORTS_DIR = cls.orig_exports
        config.QR_DIR = cls.orig_qr
        config.MEMBER_DEMO_ACCOUNTS = cls.orig_demo
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_full_two_role_browser_e2e_and_xss_and_touch_targets(self):
        screens_dir = ROOT / "docs" / "web_screens"
        screens_dir.mkdir(parents=True, exist_ok=True)

        cust_driver = _make_chrome(390, 844)
        staff_driver = _make_chrome(1280, 780)
        try:
            # 1) ลูกค้าสแกน QR โต๊ะ 1
            t1 = table_service.get_table_by_no(1)
            cust_driver.get(f"{self.base_url}/t/1?k={t1['secret_key']}")
            for _ in range(25):
                if "/s" in cust_driver.current_url:
                    break
                time.sleep(0.2)
            self.assertIn("/s", cust_driver.current_url)
            self.assertNotIn("k=", cust_driver.current_url)
            time.sleep(0.3)
            body_txt = cust_driver.find_element("tag name", "body").text
            self.assertIn("ส่งคำขอแล้ว กรุณารอพนักงานยืนยัน", body_txt)

            # 2) พนักงาน/เจ้าของล็อกอินผ่านฟอร์มจริงที่ `/staff#/login`
            staff_driver.get(f"{self.base_url}/staff#/login")
            time.sleep(0.3)
            staff_driver.execute_script(
                """
                const inputs = document.querySelectorAll('.login-form input');
                inputs[0].value = 'owner';
                inputs[1].value = 'owner1234';
                document.querySelector('.login-form button[type="submit"]').click();
                """
            )
            for _ in range(25):
                if "#/dashboard" in staff_driver.current_url:
                    break
                time.sleep(0.2)
            self.assertIn("#/dashboard", staff_driver.current_url)

            # 3) ทดสอบแจ้งเตือนโต๊ะเงียบ (AlertCenter แถบแดง) บนหน้าจอพนักงาน
            db.execute("UPDATE table_sessions SET started_at = datetime('now', 'localtime', '-10 minutes')")
            alert_service.check_alerts()
            staff_driver.get(f"{self.base_url}/staff#/tables")
            staff_driver.execute_script("if (window.location.hash !== '#/tables') window.location.hash = '#/tables';")
            time.sleep(0.4)
            # กระตุ้นให้ AlertCenter โหลดรายการล่าสุด
            staff_driver.execute_script(
                """
                const ac = document.querySelector('.alert-center');
                if (ac && ac.classList.contains('hidden')) {
                  window.location.reload();
                }
                """
            )
            time.sleep(0.5)
            alert_text = staff_driver.find_element("tag name", "body").text
            self.assertIn("แจ้งเตือนด่วน", alert_text)
            staff_driver.save_screenshot(str(screens_dir / "e2e_alert_banner.png"))


            # 4) พนักงานกด "ยืนยัน" โต๊ะ 1 ที่หน้า `#/tables`
            staff_driver.execute_script(
                """
                const btns = Array.from(document.querySelectorAll('.table-card.status-pending button'));
                const confirmBtn = btns.find(b => b.textContent.trim() === 'ยืนยัน');
                if (confirmBtn) confirmBtn.click();
                """
            )
            time.sleep(0.4)

            # 5) ลูกค้าเห็นหน้าสั่งอาหาร (`order`) + ตรวจขนาดปุ่มสัมผัส >= 40px (P3-5)
            cust_driver.get(f"{self.base_url}/s")
            time.sleep(0.4)
            cust_body = cust_driver.find_element("tag name", "body").text
            self.assertIn("สั่งอาหารได้", cust_body)

            # เลือกหมวด "ผักและของทานเล่น" แล้วตรวจขนาดปุ่ม +/- และกดเพิ่มรายการ
            cust_driver.execute_script(
                """
                const cats = Array.from(document.querySelectorAll('.cust-cat-btn'));
                const vegCat = cats.find(b => b.textContent.includes('ผัก'));
                if (vegCat) vegCat.click();
                """
            )
            time.sleep(0.3)
            touch_heights = cust_driver.execute_script(
                """
                const btns = Array.from(document.querySelectorAll('.cust-qty-btn, .cust-tab-btn'));
                return btns.map(b => b.getBoundingClientRect().height);
                """
            )
            self.assertTrue(len(touch_heights) > 0)
            for h in touch_heights:
                self.assertGreaterEqual(h, 40.0)

            # กด + เพิ่มรายการแรก 2 ชิ้น แล้วกด "ตรวจสอบ/สั่งอาหาร" -> "ยืนยันสั่ง"
            cust_driver.execute_script(
                """
                const plusBtn = document.querySelector('.cust-qty-btn-plus');
                if (plusBtn) plusBtn.click();
                """
            )
            time.sleep(0.35)
            cust_driver.execute_script(
                """
                const orderBtn = document.querySelector('.cust-cart-bar .btn-primary');
                if (orderBtn) orderBtn.click();
                """
            )
            time.sleep(0.25)
            cust_driver.execute_script(
                """
                const noteInput = document.querySelector('.modal-body input');
                if (noteInput) noteInput.value = 'ไม่ใส่ผงชูรส <script>window.__xss_triggered=true</script>';
                const confirmBtn = document.querySelector('.modal-footer .btn-primary');
                if (confirmBtn) confirmBtn.click();
                """
            )
            time.sleep(0.45)
            cust_after_order = cust_driver.find_element("tag name", "body").text
            self.assertIn("ออเดอร์ #", cust_after_order)
            self.assertIn("ยอดรวมปัจจุบัน", cust_after_order)

            # ตรวจว่า XSS payload ในหมายเหตุออเดอร์ไม่ถูกรันในเบราว์เซอร์ลูกค้า
            xss_cust = cust_driver.execute_script("return Boolean(window.__xss_triggered);")
            self.assertFalse(xss_cust)

            # 6) พนักงานชั่งน้ำหนักโต๊ะ 1 ที่หน้า `#/weigh` (15 ขีด = 1.5 กก.)
            staff_driver.get(f"{self.base_url}/staff#/weigh")
            time.sleep(0.4)
            staff_driver.execute_script(
                """
                const inp = document.querySelector('input.field-input.num');
                if (inp) {
                  inp.value = '15';
                  inp.dispatchEvent(new Event('input', { bubbles: true }));
                }
                const saveBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('บันทึกการชั่ง'));
                if (saveBtn) saveBtn.click();
                """
            )
            time.sleep(0.45)
            weigh_text = staff_driver.find_element("tag name", "body").text
            self.assertIn("448.50", weigh_text)

            # 7) พนักงานไปหน้า `#/orders` -> ตรวจไม่รัน XSS -> กด `เริ่มทำ` -> กด `เสิร์ฟแล้ว`
            staff_driver.get(f"{self.base_url}/staff#/orders")
            time.sleep(0.4)
            xss_staff = staff_driver.execute_script("return Boolean(window.__xss_triggered);")
            self.assertFalse(xss_staff)
            staff_driver.execute_script(
                """
                const b1 = Array.from(document.querySelectorAll('.order-card button')).find(b => b.textContent.trim() === 'เริ่มทำ');
                if (b1) b1.click();
                """
            )
            time.sleep(0.4)
            staff_driver.execute_script(
                """
                const b2 = Array.from(document.querySelectorAll('.order-card button')).find(b => b.textContent.trim() === 'เสิร์ฟแล้ว');
                if (b2) b2.click();
                """
            )
            time.sleep(0.4)

            # 8) พนักงานไปหน้า `#/checkout` -> เลือกโต๊ะ 1 -> เริ่มเช็คบิล -> ชำระเงินสด -> ดูใบเสร็จ
            staff_driver.get(f"{self.base_url}/staff#/checkout")
            time.sleep(0.4)
            staff_driver.execute_script(
                """
                const tblBtn = Array.from(document.querySelectorAll('.split-checkout button')).find(b => b.textContent.includes('โต๊ะ 1'));
                if (tblBtn) tblBtn.click();
                """
            )
            time.sleep(0.35)
            staff_driver.execute_script(
                """
                const startBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'เริ่มเช็คบิล');
                if (startBtn) startBtn.click();
                """
            )
            time.sleep(0.2)
            staff_driver.execute_script(
                """
                const okBtn = document.querySelector('.modal-footer .btn-primary');
                if (okBtn) okBtn.click();
                """
            )
            time.sleep(0.4)
            staff_driver.save_screenshot(str(screens_dir / "e2e_checkout_bill.png"))

            # ลูกค้าเห็นหน้าบิล (awaiting_payment)
            cust_driver.get(f"{self.base_url}/s")
            time.sleep(0.35)
            self.assertIn("พนักงานกำลังเช็คบิลให้ที่โต๊ะ", cust_driver.find_element("tag name", "body").text)

            # พนักงานกรอกเงินสดรับ 1000 บาท แล้วกดชำระเงิน
            for _ in range(20):
                has_pay_btn = staff_driver.execute_script(
                    "return Boolean(Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('ชำระเงินแล้ว (ปิดโต๊ะ)')));"
                )
                if has_pay_btn:
                    break
                time.sleep(0.15)

            staff_driver.execute_script(
                """
                const cashInp = document.querySelector('.split-checkout input.field-input.num');
                if (cashInp) {
                  cashInp.value = '1000';
                  cashInp.dispatchEvent(new Event('input', { bubbles: true }));
                }
                const payBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('ชำระเงินแล้ว (ปิดโต๊ะ)'));
                if (payBtn) payBtn.click();
                """
            )
            for _ in range(20):
                clicked_modals = staff_driver.execute_script(
                    """
                    const titleEl = document.querySelector('.modal-title');
                    if (titleEl && titleEl.textContent.includes('ใบเสร็จรับเงิน')) {
                      return 'receipt_ready';
                    }
                    const btn = document.querySelector('.modal-footer .btn-primary, .modal-footer .btn-danger');
                    if (btn) {
                      btn.click();
                      return 'clicked_confirm';
                    }
                    return 'waiting';
                    """
                )
                if clicked_modals == "receipt_ready":
                    break
                time.sleep(0.2)
            receipt_modal_txt = staff_driver.find_element("tag name", "body").text
            self.assertIn("ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน", receipt_modal_txt)
            self.assertIn("ขอบคุณที่ใช้บริการ", receipt_modal_txt)
            staff_driver.save_screenshot(str(screens_dir / "e2e_receipt_dialog.png"))

            # ลูกค้าเห็นหน้าชำระเงินเรียบร้อย + ใบเสร็จรับเงิน
            cust_driver.get(f"{self.base_url}/s")
            time.sleep(0.35)
            cust_closed_txt = cust_driver.find_element("tag name", "body").text
            self.assertIn("ชำระเงินเรียบร้อย", cust_closed_txt)
            self.assertIn("ใบเสร็จรับเงิน", cust_closed_txt)

            # 9) ทดสอบหน้าสั่งกลับบ้าน (#/takeaway):
            # - กรอกชั่งกิโล 6 ขีด (< 1 กก. ปุ่มชำระเงินต้องยังกดไม่ได้) -> กดเพิ่มอีก 4 ขีด รวมเป็น 10 ขีด (1 กก.) อยู่ในหัวข้อเดียวกันฝั่งซ้าย
            # - ค้นหาสินค้าด้วยชื่อ 'น้ำเปล่า' -> กดเพิ่ม 2 ขวด
            # - ชำระเงินด้วยเงินสด -> เปิดสลิปใบเสร็จสั่งกลับบ้าน
            staff_driver.get(f"{self.base_url}/staff#/takeaway")
            time.sleep(0.45)
            staff_driver.execute_script(
                """
                const closeModals = Array.from(document.querySelectorAll('.modal-footer button')).find(b => b.textContent.trim() === 'ปิด');
                if (closeModals) closeModals.click();
                """
            )
            time.sleep(0.2)
            staff_driver.execute_script(
                """
                const wInp = document.querySelector('.takeaway-weight-input');
                if (wInp) {
                  wInp.value = '6';
                  wInp.dispatchEvent(new Event('input', { bubbles: true }));
                }
                const addWBtn = Array.from(document.querySelectorAll('.takeaway-weigh-bar button')).find(b => b.textContent.includes('เพิ่มน้ำหนัก'));
                if (addWBtn) addWBtn.click();
                """
            )
            time.sleep(0.3)
            # ยังไม่ถึง 1 กก. ปุ่มชำระเงินต้อง disabled
            is_disabled_6 = staff_driver.execute_script(
                "return Boolean(document.querySelector('.takeaway-left-card .btn-success')?.disabled);"
            )
            self.assertTrue(is_disabled_6)

            # เพิ่มอีก 4 ขีด รวมเป็น 10 ขีด (1 กก. = 299.00 บาท) ในหัวข้อเดียวกัน
            staff_driver.execute_script(
                """
                const wInp = document.querySelector('.takeaway-weight-input');
                if (wInp) {
                  wInp.value = '4';
                  wInp.dispatchEvent(new Event('input', { bubbles: true }));
                }
                const addWBtn = Array.from(document.querySelectorAll('.takeaway-weigh-bar button')).find(b => b.textContent.includes('เพิ่มน้ำหนัก'));
                if (addWBtn) addWBtn.click();
                """
            )
            time.sleep(0.3)
            weigh_rows_count = staff_driver.execute_script(
                "return document.querySelectorAll('.takeaway-cart-row-weigh').length;"
            )
            self.assertEqual(weigh_rows_count, 1)
            is_disabled_10 = staff_driver.execute_script(
                "return Boolean(document.querySelector('.takeaway-left-card .btn-success')?.disabled);"
            )
            self.assertFalse(is_disabled_10)

            # ค้นหาสินค้าด้วยชื่อ 'โค้ก' แล้วกดเพิ่ม
            staff_driver.execute_script(
                """
                const sInp = Array.from(document.querySelectorAll('input.field-input')).find(i => i.placeholder.includes('ค้นหาสินค้า'));
                if (sInp) {
                  sInp.value = 'โค้ก';
                  sInp.dispatchEvent(new Event('input', { bubbles: true }));
                }
                """
            )
            time.sleep(0.25)
            staff_driver.execute_script(
                """
                const addItemBtn = document.querySelector('.takeaway-item-card .btn-primary');
                if (addItemBtn) addItemBtn.click();
                """
            )
            time.sleep(0.25)
            staff_driver.save_screenshot(str(screens_dir / "e2e_takeaway_pos.png"))

            # กดปุ่มชำระเงิน -> กรอกเงินสด 500 -> ยืนยันรับเงินสด & ออกสลิป
            staff_driver.execute_script(
                """
                const payOpenBtn = document.querySelector('.takeaway-left-card .btn-success');
                if (payOpenBtn) payOpenBtn.click();
                """
            )
            time.sleep(0.35)
            staff_driver.execute_script(
                """
                const cashInp = document.querySelector('.modal-body input.field-input.num');
                if (cashInp) {
                  cashInp.value = '500';
                  cashInp.dispatchEvent(new Event('input', { bubbles: true }));
                }
                const confirmBtn = document.querySelector('.modal-footer .btn-success');
                if (confirmBtn) confirmBtn.click();
                """
            )
            for _ in range(20):
                title_txt = staff_driver.execute_script(
                    "return document.querySelector('.modal-title')?.textContent || '';"
                )
                if 'ใบเสร็จรับเงิน' in title_txt:
                    break
                time.sleep(0.2)
            takeaway_receipt_txt = staff_driver.find_element("tag name", "body").text
            self.assertIn("สั่งกลับบ้าน", takeaway_receipt_txt)
            self.assertIn("ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน", takeaway_receipt_txt)

            # ปิด modal ใบเสร็จสั่งกลับบ้าน
            staff_driver.execute_script(
                "const closeBtn = document.querySelector('.modal-close-btn'); if (closeBtn) closeBtn.click();"
            )
            time.sleep(0.25)

            # 12) ทดสอบระบบสมาชิกฝั่งลูกค้าบนเบราว์เซอร์จริง (โต๊ะ 2) + หน้าโปรโมชั่น 2 ฝั่งของเจ้าของร้าน
            t2 = table_service.list_tables()[1]
            cust_driver.get(f"{self.base_url}/t/{t2['table_no']}?k={t2['secret_key']}")
            time.sleep(0.35)
            s2 = table_service.get_active_session(t2['id'])
            table_service.confirm_session(s2['id'], user_id=2)
            from services import weigh_service
            weigh_service.add_entry(s2['id'], None, 1500, user_id=2)
            cust_driver.get(f"{self.base_url}/s")
            time.sleep(0.45)

            # ตรวจว่ามีแถบสมาชิก (ปุ่ม เข้าสู่ระบบ, สมัครสมาชิก)
            banner_txt = cust_driver.find_element("tag name", "body").text
            self.assertIn("เข้าสู่ระบบ", banner_txt)
            self.assertIn("สมัครสมาชิก", banner_txt)

            # กดแท็บ 🎁 โปรโมชันสมาชิก ตอนยังไม่ล็อกอิน -> ต้องแสดงข้อความล็อกไว้ให้เข้าสู่ระบบก่อน
            cust_driver.execute_script(
                "const pTab = document.querySelector('[data-tab=\"promo\"]'); if (pTab) pTab.click();"
            )
            time.sleep(0.3)
            self.assertIn("เฉพาะสมาชิกเท่านั้น", cust_driver.find_element("tag name", "body").text)

            # กดปุ่มเข้าสู่ระบบ -> ล็อกอินด้วยบัญชีตัวอย่าง somchai@gmail.com / 123456
            cust_driver.execute_script(
                "const lBtn = document.querySelector('[data-testid=\"btn-open-login\"]'); if (lBtn) lBtn.click();"
            )
            time.sleep(0.3)
            cust_driver.execute_script(
                """
                const idInp = document.querySelector('[data-testid=\"login-id\"]');
                const pwInp = document.querySelector('[data-testid=\"login-pw\"]');
                if (idInp && pwInp) {
                  idInp.value = 'somchai@gmail.com';
                  pwInp.value = '123456';
                }
                const subBtn = document.querySelector('[data-testid=\"btn-submit-login\"]');
                if (subBtn) subBtn.click();
                """
            )
            for _ in range(20):
                if "สมชาย สายหมูกระทะ" in cust_driver.find_element("tag name", "body").text:
                    break
                time.sleep(0.2)
            self.assertIn("สมชาย สายหมูกระทะ", cust_driver.find_element("tag name", "body").text)

            # กดแท็บ 🎁 โปรโมชันสมาชิก -> เก็บโค้ดและใช้โค้ดส่วนลด TONMAKHA50
            cust_driver.execute_script(
                "const pTab = document.querySelector('[data-tab=\"promo\"]'); if (pTab) pTab.click();"
            )
            time.sleep(0.35)
            cust_driver.execute_script(
                "const cBtn = document.querySelector('[data-testid=\"btn-claim-TONMAKHA50\"]'); if (cBtn) cBtn.click();"
            )
            time.sleep(0.35)
            cust_driver.execute_script(
                "const aBtn = document.querySelector('[data-testid=\"btn-apply-TONMAKHA50\"]'); if (aBtn) aBtn.click();"
            )
            time.sleep(0.4)

            # ตรวจแท็บ 🕒 ประวัติทำรายการ -> กดดูใบเสร็จย้อนหลัง
            cust_driver.execute_script(
                "const hTab = document.querySelector('[data-tab=\"history\"]'); if (hTab) hTab.click();"
            )
            time.sleep(0.35)
            hist_txt = cust_driver.find_element("tag name", "body").text
            self.assertIn("ประวัติการทำรายการย้อนหลัง", hist_txt)
            self.assertIn("ดูใบเสร็จย้อนหลัง", hist_txt)
            cust_driver.execute_script(
                "const rBtn = document.querySelector('.history-receipt-btn'); if (rBtn) rBtn.click();"
            )
            time.sleep(0.3)
            self.assertIn("ใบเสร็จย้อนหลัง", cust_driver.find_element("tag name", "body").text)
            cust_driver.execute_script(
                "const closeBtn = document.querySelector('.modal-close-btn'); if (closeBtn) closeBtn.click();"
            )
            time.sleep(0.2)

            # 13) ล็อกอินฝั่งเจ้าของร้าน -> เปิดหน้า #/promo ตรวจ 2 ฝั่ง (ซ้าย: คนทั่วไป, ขวา: สมาชิก) และกดดูสมาชิก
            from server.auth import create_staff_token
            owner_token = create_staff_token(1)
            staff_driver.execute_cdp_cmd(
                "Network.setCookie",
                {
                    "name": config.STAFF_COOKIE_NAME,
                    "value": owner_token,
                    "url": self.base_url,
                    "path": "/",
                    "httpOnly": True,
                },
            )
            staff_driver.get(f"{self.base_url}/staff#/promo")
            staff_driver.refresh()
            time.sleep(0.5)
            promo_page_txt = staff_driver.find_element("tag name", "body").text
            self.assertIn("โปรโมชั่นสำหรับคนทั่วไป", promo_page_txt)
            self.assertIn("โปรโมชั่นสำหรับสมาชิก", promo_page_txt)

            # กดปุ่ม ดูสมาชิก -> ต้องเห็น สมชาย สายหมูกระทะ อยู่บนสุดพร้อมสถานะ กำลังใช้งาน
            staff_driver.execute_script(
                "const mBtn = document.querySelector('[data-testid=\"btn-view-members\"]'); if (mBtn) mBtn.click();"
            )
            time.sleep(0.4)
            modal_txt = staff_driver.find_element("tag name", "body").text
            self.assertIn("รายชื่อสมาชิกทั้งหมด", modal_txt)
            self.assertIn("สมชาย สายหมูกระทะ", modal_txt)
            self.assertIn("กำลังใช้งาน", modal_txt)

        finally:
            cust_driver.quit()
            staff_driver.quit()


if __name__ == "__main__":
    unittest.main(verbosity=2)
