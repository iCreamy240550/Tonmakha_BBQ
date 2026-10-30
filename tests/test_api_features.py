"""tests/test_api_features.py — ชุดทดสอบอัตโนมัติสำหรับชั้น API หลังบ้าน (FastAPI) ครบทุก endpoint และ flow ธุรกิจ
ตาม PLAN.md เฟส 1 (P1-18)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import test_all_features  # noqa: F401

import config
from database import seed
from server import auth as server_auth
from server.app import create_app
from services import alert_service, email_service, menu_service, shop_service, stock_service, table_service


class ApiFeaturesTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="tonmakha_api_test_"))
        self._orig_db = config.DB_PATH
        self._orig_uploads = config.UPLOADS_DIR
        self._orig_menu_img = config.MENU_IMAGE_DIR
        self._orig_exports = config.EXPORTS_DIR
        self._orig_qr = config.QR_DIR
        self._orig_backups = config.BACKUPS_DIR
        self._orig_assets = config.ASSETS_DIR
        self._orig_fonts = config.FONTS_DIR
        self._orig_secret = config.SECRET_FILE
        self._orig_demo = config.MEMBER_DEMO_ACCOUNTS

        config.DB_PATH = self.tmp_dir / "test_tonmakha.db"
        config.ASSETS_DIR = self.tmp_dir / "assets"
        config.FONTS_DIR = self._orig_fonts
        config.UPLOADS_DIR = config.ASSETS_DIR / "uploads"
        config.MENU_IMAGE_DIR = config.UPLOADS_DIR / "menu"
        config.QR_DIR = config.ASSETS_DIR / "qr_codes"
        config.EXPORTS_DIR = self.tmp_dir / "exports"
        config.BACKUPS_DIR = self.tmp_dir / "backups"
        config.SECRET_FILE = self.tmp_dir / "web_secret.key"

        for d in (
            config.ASSETS_DIR,
            config.UPLOADS_DIR,
            config.MENU_IMAGE_DIR,
            config.QR_DIR,
            config.EXPORTS_DIR,
            config.BACKUPS_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)

        seed.seed_all()
        shop_service.open_shop(user_id=1)
        server_auth.reset_rate_limits()

        self.app = create_app(enable_lifespan=False)
        self.owner_client = TestClient(self.app)
        self.staff_client = TestClient(self.app)
        self.cust_client = TestClient(self.app)

    def tearDown(self):
        config.DB_PATH = self._orig_db
        config.ASSETS_DIR = self._orig_assets
        config.FONTS_DIR = self._orig_fonts
        config.UPLOADS_DIR = self._orig_uploads
        config.MENU_IMAGE_DIR = self._orig_menu_img
        config.EXPORTS_DIR = self._orig_exports
        config.QR_DIR = self._orig_qr
        config.BACKUPS_DIR = self._orig_backups
        config.SECRET_FILE = self._orig_secret
        config.MEMBER_DEMO_ACCOUNTS = self._orig_demo
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _login_owner(self):
        res = self.owner_client.post("/api/staff/login", json={"username": "owner", "password": "owner1234"})
        self.assertEqual(res.status_code, 200)
        return res.json()

    def _login_staff(self):
        res = self.staff_client.post("/api/staff/login", json={"username": "staff1", "password": "staff1234"})
        self.assertEqual(res.status_code, 200)
        return res.json()

    def test_01_auth_and_shop_control(self):
        me0 = self.staff_client.get("/api/staff/me").json()
        self.assertFalse(me0["authenticated"])

        bad_empty = self.staff_client.post("/api/staff/login", json={"username": "", "password": ""})
        self.assertEqual(bad_empty.status_code, 400)
        self.assertIn("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน", bad_empty.json()["detail"])

        bad_pw = self.staff_client.post("/api/staff/login", json={"username": "staff1", "password": "wrong"})
        self.assertEqual(bad_pw.status_code, 401)
        self.assertIn("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", bad_pw.json()["detail"])

        login_data = self._login_staff()
        self.assertEqual(login_data["user"]["username"], "staff1")
        self.assertEqual(login_data["default_page"], "tables")

        me1 = self.staff_client.get("/api/staff/me").json()
        self.assertTrue(me1["authenticated"])

        st = self.staff_client.get("/api/staff/shop").json()
        self.assertTrue(st["is_open"])

        cl = self.staff_client.post("/api/staff/shop/close", json={"force": False})
        self.assertEqual(cl.status_code, 200)
        self.assertFalse(cl.json()["is_open"])

        op = self.staff_client.post("/api/staff/shop/open")
        self.assertEqual(op.status_code, 200)
        self.assertTrue(op.json()["is_open"])

        lo = self.staff_client.post("/api/staff/logout")
        self.assertEqual(lo.status_code, 200)
        self.assertFalse(self.staff_client.get("/api/staff/me").json()["authenticated"])

    def test_02_full_customer_staff_e2e_flow(self):
        self._login_staff()
        self._login_owner()

        t1 = table_service.get_table_by_no(1)

        page_res = self.cust_client.get(f"/t/1?k={t1['secret_key']}")
        self.assertEqual(page_res.status_code, 200)
        self.assertIsNone(table_service.get_active_session(t1["id"]))

        scan_res = self.cust_client.post("/api/customer/scan", json={"table_no": 1, "k": t1["secret_key"]})
        self.assertEqual(scan_res.status_code, 200)
        scan_data = scan_res.json()
        self.assertEqual(scan_data["kind"], "ok")
        sid = scan_data["session_id"]

        st1 = self.cust_client.get("/api/customer/state").json()
        self.assertTrue(st1["has_session"])
        self.assertEqual(st1["snapshot"]["view"], "waiting")

        t2 = table_service.get_table_by_no(2)
        other_res = self.cust_client.post("/api/customer/scan", json={"table_no": 2, "k": t2["secret_key"]}).json()
        self.assertEqual(other_res["kind"], "other_table")
        self.assertEqual(other_res["table_name"], "โต๊ะ 1")

        tbls = self.staff_client.get("/api/staff/tables").json()
        self.assertEqual(tbls["pending"], 1)
        conf_res = self.staff_client.post(f"/api/staff/tables/{sid}/confirm")
        self.assertEqual(conf_res.status_code, 200)

        st2 = self.cust_client.get("/api/customer/state").json()
        self.assertEqual(st2["snapshot"]["view"], "order")

        w_fail = self.staff_client.post("/api/staff/weigh", json={"session_id": sid, "weight_grams": 500})
        self.assertEqual(w_fail.status_code, 400)
        self.assertIn("อย่างน้อย 1 กิโลกรัม", w_fail.json()["detail"])

        w_ok = self.staff_client.post("/api/staff/weigh", json={"session_id": sid, "weight_grams": 1000})
        self.assertEqual(w_ok.status_code, 200)
        self.assertEqual(w_ok.json()["entry"]["amount"], 299.0)

        w_ok2 = self.staff_client.post("/api/staff/weigh", json={"session_id": sid, "weight_grams": 500})
        self.assertEqual(w_ok2.status_code, 200)
        self.assertEqual(w_ok2.json()["entry"]["amount"], 149.5)

        water = next(m for m in menu_service.list_items() if m["name"] == "น้ำเปล่า")
        cur_st = stock_service.get_item(water["stock_item_id"])
        stock_service.adjust(water["stock_item_id"], -(cur_st["quantity"] - 2), "ตั้งสต๊อกเหลือ 2", user_id=1)

        c1 = self.cust_client.post("/api/customer/cart/change", json={"item_id": water["id"], "delta": 2})
        self.assertEqual(c1.status_code, 200)
        self.assertEqual(c1.json()["cart_count"], 2)

        c_over = self.cust_client.post("/api/customer/cart/change", json={"item_id": water["id"], "delta": 1})
        self.assertEqual(c_over.status_code, 400)
        self.assertIn("สั่งได้สูงสุด 2 ขวด", c_over.json()["detail"])
        self.assertEqual(c_over.json()["cart_count"], 2)

        ord_res = self.cust_client.post("/api/customer/order", json={"note": "ไม่ใส่น้ำแข็ง"})
        self.assertEqual(ord_res.status_code, 200)
        ord_id = ord_res.json()["order"]["id"]
        self.assertEqual(ord_res.json()["cart_count"], 0)

        st3 = self.cust_client.get("/api/customer/state").json()
        self.assertGreaterEqual(len(st3["snapshot"]["unread"]), 1)
        unread_ids = [n["id"] for n in st3["snapshot"]["unread"]]
        mk_res = self.cust_client.post("/api/customer/notices/read", json={"notice_ids": unread_ids})
        self.assertEqual(mk_res.status_code, 200)

        skip_srv = self.staff_client.post(f"/api/staff/orders/{ord_id}/status", json={"status": "served"})
        self.assertEqual(skip_srv.status_code, 400)

        prep_res = self.staff_client.post(f"/api/staff/orders/{ord_id}/status", json={"status": "preparing"})
        self.assertEqual(prep_res.status_code, 200)
        srv_res = self.staff_client.post(f"/api/staff/orders/{ord_id}/status", json={"status": "served"})
        self.assertEqual(srv_res.status_code, 200)

        promo_res = self.owner_client.post("/api/owner/promos", json={
            "name": "ลดพิเศษ 10%",
            "promo_type": "percent",
            "value": 10,
            "min_amount": 100,
            "active": True,
        })
        self.assertEqual(promo_res.status_code, 200)
        promo_id = promo_res.json()["promo"]["id"]

        chk_start = self.staff_client.post(f"/api/staff/checkout/{sid}/start")
        self.assertEqual(chk_start.status_code, 200)

        st_bill = self.cust_client.get("/api/customer/state").json()
        self.assertEqual(st_bill["snapshot"]["view"], "bill")

        chk_state = self.staff_client.get(f"/api/staff/checkout?session_id={sid}&promo_id={promo_id}").json()
        bill_prev = chk_state["bill"]
        self.assertEqual(bill_prev["subtotal"], 478.5)
        self.assertEqual(bill_prev["discount"], 47.85)
        self.assertEqual(bill_prev["total"], 430.65)
        self.assertTrue(chk_state["promptpay"]["valid"])

        pay_low = self.staff_client.post(f"/api/staff/checkout/{sid}/pay", json={
            "payment_method": "cash",
            "promo_id": promo_id,
            "amount_received": 400,
        })
        self.assertEqual(pay_low.status_code, 400)

        pay_ok = self.staff_client.post(f"/api/staff/checkout/{sid}/pay", json={
            "payment_method": "cash",
            "promo_id": promo_id,
            "amount_received": 500,
        })
        self.assertEqual(pay_ok.status_code, 200)
        paid_data = pay_ok.json()
        self.assertEqual(paid_data["bill"]["change_amount"], 69.35)

        exp_pdf = self.staff_client.post(f"/api/staff/checkout/{sid}/export/pdf")
        self.assertEqual(exp_pdf.status_code, 200)
        dl_pdf = self.staff_client.get(exp_pdf.json()["download_url"])
        self.assertEqual(dl_pdf.status_code, 200)
        self.assertEqual(dl_pdf.headers["content-type"], "application/pdf")

        exp_txt = self.staff_client.post(f"/api/staff/checkout/{sid}/export/txt")
        self.assertEqual(exp_txt.status_code, 200)
        dl_txt = self.staff_client.get(exp_txt.json()["download_url"])
        self.assertEqual(dl_txt.status_code, 200)

        st_closed = self.cust_client.get("/api/customer/state").json()
        self.assertEqual(st_closed["snapshot"]["view"], "closed")
        self.assertEqual(st_closed["snapshot"]["bill"]["total"], 430.65)

    def test_03_alerts_case_a_b_and_stock(self):
        self._login_staff()
        t3 = table_service.get_table_by_no(3)
        scan = self.cust_client.post("/api/customer/scan", json={"table_no": 3, "k": t3["secret_key"]}).json()
        sid = scan["session_id"]

        alert_service.check_alerts(now=datetime.now() + timedelta(minutes=10))
        alerts_res = self.staff_client.get("/api/staff/alerts?check=false").json()
        self.assertTrue(alerts_res["play_sound"])
        a_pending = next(a for a in alerts_res["alerts"] if a["session_id"] == sid)
        self.assertEqual(a_pending["kind"], alert_service.KIND_PENDING)

        self.staff_client.post(f"/api/staff/tables/{sid}/confirm")
        alert_service.check_alerts(now=datetime.now())

        alert_service.check_alerts(now=datetime.now() + timedelta(minutes=15))
        alerts_b = self.staff_client.get("/api/staff/alerts?check=false").json()["alerts"]
        a_idle = next(a for a in alerts_b if a["session_id"] == sid and a["kind"] == alert_service.KIND_IDLE_OPEN)

        snz = self.staff_client.post(f"/api/staff/alerts/{a_idle['id']}/snooze")
        self.assertEqual(snz.status_code, 200)

        alert_service.check_alerts(now=datetime.now() + timedelta(minutes=25))
        canc = self.staff_client.post(f"/api/staff/alerts/{a_idle['id']}/cancel_table")
        self.assertEqual(canc.status_code, 200)
        self.assertEqual(table_service.get_session(sid)["status"], config.SESSION_CANCELLED)

    def test_04_owner_endpoints_complete(self):
        self._login_owner()

        ov = self.owner_client.get("/api/owner/dashboard/overview")
        self.assertEqual(ov.status_code, 200)
        rep = self.owner_client.get("/api/owner/dashboard/report?quick=today")
        self.assertEqual(rep.status_code, 200)
        csv_res = self.owner_client.post("/api/owner/report/export_csv", json={
            "date_from": rep.json()["date_from"],
            "date_to": rep.json()["date_to"],
        })
        self.assertEqual(csv_res.status_code, 200)
        dl_csv = self.owner_client.get(csv_res.json()["download_url"])
        self.assertEqual(dl_csv.status_code, 200)

        cat_res = self.owner_client.post("/api/owner/menu/categories", json={"name": "ของหวาน"})
        self.assertEqual(cat_res.status_code, 200)
        cat_id = cat_res.json()["category"]["id"]

        it_res = self.owner_client.post("/api/owner/menu/items", json={
            "category_id": cat_id,
            "name": "ไอศกรีมกะทิ",
            "item_type": "normal",
            "price": 35,
        })
        self.assertEqual(it_res.status_code, 200)
        item_id = it_res.json()["item"]["id"]

        img = Image.new("RGB", (600, 400), (200, 120, 80))
        buf = BytesIO()
        img.save(buf, format="PNG")
        up_res = self.owner_client.post(
            f"/api/owner/menu/items/{item_id}/image",
            files={"file": ("icecream.png", buf.getvalue(), "image/png")},
        )
        self.assertEqual(up_res.status_code, 200)
        self.assertTrue(up_res.json()["item"]["has_image"])

        img_url = up_res.json()["item"]["image_url"]
        self.assertEqual(self.owner_client.get(img_url).status_code, 200)

        self.assertEqual(self.owner_client.delete(f"/api/owner/menu/items/{item_id}/image").status_code, 200)
        imp = self.owner_client.get(f"/api/owner/menu/items/{item_id}/delete_impact").json()
        self.assertTrue(imp["can_hard_delete"])
        self.assertEqual(self.owner_client.delete(f"/api/owner/menu/items/{item_id}").status_code, 200)

        st_add = self.owner_client.post("/api/owner/stock", json={
            "name": "ตะเกียบไม้ไผ่",
            "unit": "คู่",
            "quantity": 0,
            "min_quantity": 10,
        })
        self.assertEqual(st_add.status_code, 200)
        st_id = st_add.json()["item"]["id"]
        self.assertEqual(self.owner_client.delete(f"/api/owner/stock/{st_id}").status_code, 200)

        tm = self.owner_client.get("/api/owner/tables_manage").json()
        t_id = tm["tables"][0]["id"]
        self.assertEqual(self.owner_client.post(f"/api/owner/tables_manage/{t_id}/qr").status_code, 200)
        qr_img = self.owner_client.get(f"/api/owner/tables_manage/{t_id}/qr_image")
        self.assertEqual(qr_img.status_code, 200)
        self.assertEqual(qr_img.headers["content-type"], "image/png")

        u_add = self.owner_client.post("/api/owner/users", json={
            "username": "staff2",
            "display_name": "พนักงาน 2",
            "role": "staff",
            "password": "pass1234",
            "password_confirm": "pass1234",
        })
        self.assertEqual(u_add.status_code, 200)

        cur_settings = self.owner_client.get("/api/owner/settings").json()
        bad_payload = {
            **cur_settings["shop"],
            "shop_name": "ชื่อใหม่ที่ไม่ควรบันทึก",
            "public_base_url": cur_settings["public_base_url"],
            "promptpay_id": "invalid_pp",
            "promptpay_name": cur_settings["promptpay_name"],
            "weigh_price_per_kg": cur_settings["weigh_price_per_kg"],
            "alert_pending_minutes": cur_settings["alert_pending_minutes"],
            "alert_idle_open_minutes": cur_settings["alert_idle_open_minutes"],
            "alert_snooze_minutes": cur_settings["alert_snooze_minutes"],
            "stock_low_threshold": cur_settings["stock_low_threshold"],
            "service_charge_enabled": cur_settings["service_charge_enabled"],
            "service_charge_percent": cur_settings["service_charge_percent"],
            "vat_enabled": cur_settings["vat_enabled"],
            "vat_percent": cur_settings["vat_percent"],
        }
        bad_save = self.owner_client.put("/api/owner/settings", json=bad_payload)
        self.assertEqual(bad_save.status_code, 400)
        after_settings = self.owner_client.get("/api/owner/settings").json()
        self.assertNotEqual(after_settings["shop"]["shop_name"], "ชื่อใหม่ที่ไม่ควรบันทึก")

        logs = self.owner_client.get("/api/owner/logs").json()
        self.assertGreater(logs["total"], 0)

        self.owner_client.post("/api/staff/shop/close", json={"force": True})
        bkp = self.owner_client.post("/api/owner/backups")
        self.assertEqual(bkp.status_code, 200)
        bkp_name = bkp.json()["filename"]
        dl_bkp = self.owner_client.get(f"/api/owner/backups/{bkp_name}/download")
        self.assertEqual(dl_bkp.status_code, 200)

        res_bad = self.owner_client.post(f"/api/owner/backups/{bkp_name}/restore", json={"confirm_text": "ผิด"})
        self.assertEqual(res_bad.status_code, 400)

        res_ok = self.owner_client.post(f"/api/owner/backups/{bkp_name}/restore", json={"confirm_text": "กู้คืน"})
        self.assertEqual(res_ok.status_code, 200)

    def test_05_takeaway_pos_flow_and_validation(self):
        self._login_staff()
        self._login_owner()

        # ดึงข้อมูลหน้าสั่งกลับบ้าน
        st = self.staff_client.get('/api/staff/takeaway').json()
        self.assertEqual(st['rate'], 299.0)
        self.assertEqual(st['min_weigh_grams'], 1000)
        self.assertTrue(len(st['categories']) > 0)
        self.assertTrue(len(st['normal_items']) > 0)

        water = next(m for m in st['normal_items'] if m['name'] == 'น้ำเปล่า')
        veg = next(m for m in st['normal_items'] if m['name'] == 'ผักรวม')

        # ทดสอบ preview
        prev = self.staff_client.post('/api/staff/takeaway/preview', json={
            'weigh_grams': 1500,
            'items': [{'menu_item_id': water['id'], 'quantity': 2}, {'menu_item_id': veg['id'], 'quantity': 1}],
        }).json()
        self.assertEqual(prev['weigh_total'], 448.5)
        self.assertEqual(prev['order_total'], 70.0)
        self.assertEqual(prev['subtotal'], 518.5)
        self.assertEqual(prev['total'], 518.5)
        self.assertTrue(prev['promptpay']['valid'])

        # ทดสอบสั่งเนื้อน้อยกว่า 1 กก. (< 1,000 กรัม) ต้องไม่ผ่าน
        bad_weigh = self.staff_client.post('/api/staff/takeaway/pay', json={
            'weigh_grams': 800,
            'items': [{'menu_item_id': water['id'], 'quantity': 1}],
            'payment_method': 'cash',
            'amount_received': 500,
        })
        self.assertEqual(bad_weigh.status_code, 400)
        self.assertIn('ขั้นต่ำ 1 กิโลกรัม', bad_weigh.json()['detail'])

        # ทดสอบชำระด้วยเงินสดสำเร็จ
        before_water_stock = stock_service.get_item(water['stock_item_id'])['quantity']
        pay_cash = self.staff_client.post('/api/staff/takeaway/pay', json={
            'weigh_grams': 1500,
            'items': [{'menu_item_id': water['id'], 'quantity': 2}, {'menu_item_id': veg['id'], 'quantity': 1}],
            'payment_method': 'cash',
            'amount_received': 600,
        })
        self.assertEqual(pay_cash.status_code, 200)
        paid_data = pay_cash.json()
        self.assertEqual(paid_data['bill']['total'], 518.5)
        self.assertEqual(paid_data['bill']['amount_received'], 600.0)
        self.assertEqual(paid_data['bill']['change_amount'], 81.5)
        self.assertEqual(paid_data['receipt_info']['table_label'], 'สั่งกลับบ้าน')
        self.assertIn('สั่งกลับบ้าน', paid_data['receipt_text'])

        # ตรวจว่าตัดสต๊อกจริง
        after_water_stock = stock_service.get_item(water['stock_item_id'])['quantity']
        self.assertEqual(after_water_stock, before_water_stock - 2)

        # ทดสอบส่งออกสลิป PDF และ TXT
        takeaway_sid = paid_data['session_id']
        exp_pdf = self.staff_client.post(f'/api/staff/checkout/{takeaway_sid}/export/pdf')
        self.assertEqual(exp_pdf.status_code, 200)
        exp_txt = self.staff_client.post(f'/api/staff/checkout/{takeaway_sid}/export/txt')
        self.assertEqual(exp_txt.status_code, 200)

        # ทดสอบชำระด้วยพร้อมเพย์ (ซื้อแต่เนื้อ 1 กก. อย่างเดียว ของเสริมไม่ซื้อก็ได้)
        pay_pp = self.owner_client.post('/api/staff/takeaway/pay', json={
            'weigh_grams': 1000,
            'items': [],
            'payment_method': 'transfer',
        })
        self.assertEqual(pay_pp.status_code, 200)
        self.assertEqual(pay_pp.json()['bill']['total'], 299.0)
        self.assertEqual(pay_pp.json()['bill']['payment_method'], 'transfer')

        # ตรวจว่าบันทึกเข้ารายรับ (dashboard report) และบันทึกการทำงาน (activity_log)
        rep = self.owner_client.get('/api/owner/dashboard/report?quick=today').json()
        self.assertGreaterEqual(rep['summary']['bill_count'], 2)
        self.assertTrue(any(b['table_no'] == 'สั่งกลับบ้าน' for b in rep['bills']))

        logs = self.owner_client.get('/api/owner/logs?action=takeaway_checkout').json()
        self.assertGreaterEqual(logs['total'], 2)

        # ตรวจว่าโต๊ะพิเศษสั่งกลับบ้าน (table_no=0) ไม่โผล่ในหน้าโต๊ะปกติ
        tables_res = self.staff_client.get('/api/staff/tables').json()
        self.assertFalse(any(t['table_no'] == 0 for t in tables_res['tables']))

    def test_06_customer_member_auth_otp_promos_history_and_owner_split_promos(self):
        # เปิดโหมดบัญชีตัวอย่างเฉพาะการทดสอบ flow ตัวอย่างเดิมใน test_06
        config.MEMBER_DEMO_ACCOUNTS = 1
        self._login_staff()
        self._login_owner()

        t2 = table_service.get_table_by_no(2)
        scan_res = self.cust_client.post('/api/customer/scan', json={'table_no': 2, 'k': t2['secret_key']})
        self.assertEqual(scan_res.status_code, 200)
        sid = table_service.get_active_session(t2['id'])['id']
        self.staff_client.post(f'/api/staff/tables/{sid}/confirm')

        # 1) ลูกค้ายังไม่สมัครสมาชิก สั่งอาหารได้ตามปกติ
        from services import weigh_service
        weigh_service.add_entry(sid, None, 1500, user_id=2)
        items = [it for it in menu_service.list_items() if it['item_type'] == 'normal']
        r_add = self.cust_client.post('/api/customer/cart/change', json={'item_id': items[0]['id'], 'delta': 1})
        self.assertEqual(r_add.status_code, 200)
        r_ord = self.cust_client.post('/api/customer/order', json={'note': 'ลูกค้าทั่วไปไม่สมัครสมาชิก'})
        self.assertEqual(r_ord.status_code, 200)

        # 2) ทดสอบขอ OTP และสมัครสมาชิกใหม่ (Sign up + OTP) โดย mock email_service.send_mail
        captured_mails: list[tuple] = []

        def _capture_send_mail(to_email, subject, text, html=None):
            captured_mails.append((to_email, subject, text, html))

        with patch.object(email_service, 'send_mail', side_effect=_capture_send_mail):
            r_otp = self.cust_client.post('/api/customer/member/otp', json={'email': 'newuser@example.com'})
            self.assertEqual(r_otp.status_code, 200)
            otp_resp = r_otp.json()
            self.assertNotIn('otp_code', otp_resp)
            self.assertEqual(otp_resp['email'], 'ne***@example.com')
            self.assertEqual(len(captured_mails), 1)
            m = re.search(r'\b(\d{6})\b', captured_mails[-1][2])
            self.assertIsNotNone(m)
            otp_code = m.group(1)
            self.assertEqual(len(otp_code), 6)

        r_signup = self.cust_client.post('/api/customer/member/signup', json={
            'name': 'ลูกค้าใหม่ ทดสอบ',
            'email': 'newuser@example.com',
            'phone': '089-111-2233',
            'password': 'password123',
            'password_confirm': 'password123',
            'otp_code': otp_code,
        })
        self.assertEqual(r_signup.status_code, 200)
        self.assertEqual(r_signup.json()['member']['email'], 'newuser@example.com')

        # 3) ทดสอบออกจากระบบและเข้าสู่ระบบด้วยบัญชีตัวอย่าง somchai@gmail.com / 123456 (เมื่อ MEMBER_DEMO_ACCOUNTS=1)
        self.cust_client.post('/api/customer/member/logout')
        r_login = self.cust_client.post('/api/customer/member/login', json={
            'identifier': 'somchai@gmail.com',
            'password': '123456',
        })
        self.assertEqual(r_login.status_code, 200)
        member_data = r_login.json()['member']
        self.assertEqual(member_data['email'], 'somchai@gmail.com')
        self.assertGreaterEqual(len(member_data['history']), 2)

        # 4) ทดสอบเก็บโค้ดส่วนลดและกดใช้โค้ดส่วนลดสมาชิก (TONMAKHA50)
        r_claim = self.cust_client.post('/api/customer/member/promo/claim', json={'code': 'TONMAKHA50'})
        self.assertEqual(r_claim.status_code, 200)
        self.assertIn('TONMAKHA50', r_claim.json()['member']['claimed_promos'])

        r_apply = self.cust_client.post('/api/customer/member/promo/apply', json={'code': 'TONMAKHA50'})
        self.assertEqual(r_apply.status_code, 200)
        self.assertEqual(r_apply.json()['applied_promo_code'], 'TONMAKHA50')

        # ตรวจว่าในหน้า รายการของฉัน มีส่วนลดสมาชิก 50 บาทแสดงทันที
        st_open = self.cust_client.get('/api/customer/state').json()
        self.assertEqual(st_open['applied_promo_code'], 'TONMAKHA50')
        self.assertEqual(st_open['snapshot']['member_discount'], 50.0)

        # 5) เจ้าของร้านดูหน้าโปรโมชั่น (แบ่งเป็น general_promos และ member_promos) และดูรายชื่อสมาชิก
        owner_promos = self.owner_client.get('/api/owner/promos').json()
        self.assertIn('general_promos', owner_promos)
        self.assertIn('member_promos', owner_promos)
        self.assertGreaterEqual(len(owner_promos['member_promos']), 3)

        # เจ้าของร้านเพิ่มโปรคนทั่วไป และเพิ่มโปรสมาชิกใหม่
        add_gen = self.owner_client.post('/api/owner/promos', json={
            'name': 'ลดวันธรรมดา 5%',
            'promo_type': 'percent',
            'value': 5,
            'min_amount': 200,
            'target': 'general',
            'active': True,
        })
        self.assertEqual(add_gen.status_code, 200)
        self.assertEqual(add_gen.json()['promo']['target'], 'general')

        add_mem = self.owner_client.post('/api/owner/promos', json={
            'name': 'ลดพิเศษสมาชิก VIP 80฿',
            'promo_type': 'fixed',
            'value': 80,
            'min_amount': 300,
            'target': 'member',
            'code': 'VIP80',
            'description': 'เฉพาะสมาชิกทานครบ 300 บาท',
            'active': True,
        })
        self.assertEqual(add_mem.status_code, 200)
        self.assertEqual(add_mem.json()['promo']['target'], 'member')
        self.assertEqual(add_mem.json()['promo']['code'], 'VIP80')

        # เจ้าของร้านกดดูสมาชิก -> สมาชิกที่กำลังทานอยู่ (somchai@gmail.com) ต้องขึ้นสถานะ กำลังใช้งาน และอยู่บนสุด!
        owner_members = self.owner_client.get('/api/owner/members').json()
        self.assertGreaterEqual(owner_members['total'], 3)
        self.assertGreaterEqual(owner_members['active_dining_count'], 1)
        top_member = owner_members['members'][0]
        self.assertTrue(top_member['is_active_dining'])
        self.assertEqual(top_member['email'], 'somchai@gmail.com')
        self.assertIn('กำลังใช้งาน', top_member['status_text'])
        for m in owner_members['members']:
            self.assertNotIn('password', m)
            self.assertNotIn('password_hash', m)
            self.assertIn('name', m)
            self.assertIn('email', m)
            self.assertIn('phone', m)

        # 6) เมื่อเริ่มเช็คเอาท์ (รอชำระเงิน/ดูบิล) ส่วนลดสมาชิก TONMAKHA50 ต้องถูกนำไปหักในบิลทันที
        self.staff_client.post(f'/api/staff/checkout/{sid}/start')
        st_bill = self.cust_client.get('/api/customer/state').json()
        self.assertEqual(st_bill['snapshot']['view'], 'bill')
        self.assertEqual(st_bill['snapshot']['bill']['discount'], 50.0)


if __name__ == "__main__":
    unittest.main()
