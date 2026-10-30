"""tests/test_member_otp.py — ชุดทดสอบครบวงจรสำหรับระบบสมาชิกลูกค้า, OTP ทางอีเมลจริง, ความปลอดภัยรหัสผ่าน และการแยกบัญชี/เซสชัน"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import test_all_features  # noqa: F401

import config
from database import db, schema, seed
from server import auth as server_auth
from server.app import create_app
from services import (
    email_service,
    log_service,
    member_service,
    otp_service,
    promo_service,
    settings_service,
    shop_service,
    table_service,
    weigh_service,
)


class MemberOtpAndIsolationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="tonmakha_member_otp_"))
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
        config.MEMBER_DEMO_ACCOUNTS = 0

        for d in (
            config.ASSETS_DIR,
            config.UPLOADS_DIR,
            config.MENU_IMAGE_DIR,
            config.QR_DIR,
            config.EXPORTS_DIR,
            config.BACKUPS_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)

        schema.create_all()
        seed.seed_all()
        shop_service.open_shop(user_id=1)
        promo_service.ensure_default_member_promos()
        server_auth.reset_rate_limits()

        self.app = create_app(enable_lifespan=False)

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
        server_auth.reset_rate_limits()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @staticmethod
    def _extract_otp_from_text(text: str) -> str:
        m = re.search(r"\b(\d{6})\b", text or "")
        if not m:
            raise AssertionError(f"ไม่พบรหัส OTP 6 หลักในเนื้อหาอีเมล: {text!r}")
        return m.group(1)

    def _signup_via_api(self, client: TestClient, name: str, email: str, phone: str, password: str) -> tuple[dict, str]:
        captured: list[tuple] = []

        def _fake_send(to_email, subject, text, html=None):
            captured.append((to_email, subject, text, html))

        with patch.object(email_service, "send_mail", side_effect=_fake_send):
            r_otp = client.post("/api/customer/member/otp", json={"email": email})
            self.assertEqual(r_otp.status_code, 200, r_otp.text)
            otp_json = r_otp.json()
            self.assertNotIn("otp_code", otp_json)
            code = self._extract_otp_from_text(captured[-1][2])
            self.assertNotIn(code, json.dumps(otp_json, ensure_ascii=False))

        r_signup = client.post(
            "/api/customer/member/signup",
            json={
                "name": name,
                "email": email,
                "phone": phone,
                "password": password,
                "password_confirm": password,
                "otp_code": code,
            },
        )
        self.assertEqual(r_signup.status_code, 200, r_signup.text)
        return r_signup.json(), code

    def test_01_no_otp_in_response_or_logs_and_email_template_safe(self):
        client = TestClient(self.app)
        res_data, otp_code = self._signup_via_api(
            client,
            name="นัท ทดสอบ",
            email="nat@example.com",
            phone="081-234-5678",
            password="SecurePass!99",
        )
        self.assertEqual(res_data["member"]["email"], "nat@example.com")
        self.assertTrue(res_data["member"]["email_verified"])

        # ตรวจว่าในตาราง activity_log ไม่มีรหัส OTP หรือรหัสผ่านของสมาชิก
        logs = log_service.get_logs(limit=200, offset=0)
        log_dump = json.dumps(logs, ensure_ascii=False)
        self.assertNotIn(otp_code, log_dump)
        self.assertNotIn("SecurePass!99", log_dump)

        # ตรวจว่าในตาราง settings (members_otp_sessions_json) ไม่มี key "code" และไม่มีรหัสตรง ๆ
        otp_row = db.query_one("SELECT value FROM settings WHERE key = ?", (otp_service.OTP_SETTING_KEY,))
        self.assertIsNotNone(otp_row)
        self.assertNotIn(otp_code, otp_row["value"])
        self.assertNotIn('"code"', otp_row["value"])

    def test_02_otp_expiry_attempts_single_use_purpose_cooldown_quota_and_rollback(self):
        captured: list[tuple] = []

        def _fake_send(to_email, subject, text, html=None):
            captured.append((to_email, subject, text, html))

        with patch.object(email_service, "send_mail", side_effect=_fake_send):
            # 1) OTP หมดอายุ (เกิน 10 นาที = 600 วินาที)
            otp_service.request_otp("exp@example.com", purpose="signup", now=1000.0)
            code_exp = self._extract_otp_from_text(captured[-1][2])
            with self.assertRaises(ValueError) as ctx_exp:
                otp_service.verify_and_consume_otp("exp@example.com", code_exp, purpose="signup", now=1601.0)
            self.assertIn("หมดอายุ", str(ctx_exp.exception))

            # 2) กรอกผิดครบ 5 ครั้งแล้วรหัสถูกยกเลิกทันที (ครั้งที่ 6 แม้ใส่รหัสถูกก็ใช้ไม่ได้)
            otp_service.request_otp("five@example.com", purpose="signup", now=2000.0)
            code_five = self._extract_otp_from_text(captured[-1][2])
            wrong_code = "000000" if code_five != "000000" else "999999"
            for i in range(4):
                with self.assertRaises(ValueError) as cm:
                    otp_service.verify_and_consume_otp("five@example.com", wrong_code, purpose="signup", now=2010.0 + i)
                self.assertIn("ไม่ถูกต้อง", str(cm.exception))
            with self.assertRaises(ValueError) as cm5:
                otp_service.verify_and_consume_otp("five@example.com", wrong_code, purpose="signup", now=2020.0)
            self.assertIn("ยกเลิก", str(cm5.exception))
            # ลองใส่รหัสที่ถูกต้องหลังถูกยกเลิกแล้ว ต้องไม่ผ่าน
            with self.assertRaises(ValueError):
                otp_service.verify_and_consume_otp("five@example.com", code_five, purpose="signup", now=2021.0)

            # 3) ใช้ข้าม purpose หรือข้ามอีเมลไม่ได้ และใช้ซ้ำไม่ได้
            otp_service.request_otp("purpose@example.com", purpose="signup", now=3000.0)
            code_p = self._extract_otp_from_text(captured[-1][2])
            with self.assertRaises(ValueError):
                otp_service.verify_and_consume_otp("purpose@example.com", code_p, purpose="reset", now=3010.0)
            with self.assertRaises(ValueError):
                otp_service.verify_and_consume_otp("other@example.com", code_p, purpose="signup", now=3010.0)
            self.assertTrue(otp_service.verify_and_consume_otp("purpose@example.com", code_p, purpose="signup", now=3010.0))
            with self.assertRaises(ValueError):
                otp_service.verify_and_consume_otp("purpose@example.com", code_p, purpose="signup", now=3011.0)

            # 4) ส่งซ้ำก่อน 60 วินาทีถูกปฏิเสธ; ขอรหัสใหม่หลัง 60 วินาทีแล้วรหัสเก่าใช้ไม่ได้ทันที; เกิน 5 ครั้งต่อชั่วโมงถูกปฏิเสธ
            otp_service.request_otp("quota@example.com", purpose="signup", now=5000.0)
            first_code = self._extract_otp_from_text(captured[-1][2])
            with self.assertRaises(ValueError) as cm_cd:
                otp_service.request_otp("quota@example.com", purpose="signup", now=5030.0)
            self.assertIn("วินาที", str(cm_cd.exception))

            otp_service.request_otp("quota@example.com", purpose="signup", now=5065.0)
            second_code = self._extract_otp_from_text(captured[-1][2])
            if first_code != second_code:
                with self.assertRaises(ValueError):
                    otp_service.verify_and_consume_otp("quota@example.com", first_code, purpose="signup", now=5070.0)
            self.assertTrue(otp_service.verify_and_consume_otp("quota@example.com", second_code, purpose="signup", now=5071.0))

            # ส่งครั้งที่ 3, 4, 5 ในชั่วโมงเดียวกัน
            otp_service.request_otp("quota@example.com", purpose="signup", now=5130.0)
            otp_service.request_otp("quota@example.com", purpose="signup", now=5200.0)
            otp_service.request_otp("quota@example.com", purpose="signup", now=5270.0)
            # ครั้งที่ 6 ในชั่วโมงเดียวกันต้องถูกปฏิเสธ
            with self.assertRaises(ValueError) as cm_hr:
                otp_service.request_otp("quota@example.com", purpose="signup", now=5350.0)
            self.assertIn("5 ครั้งต่อชั่วโมง", str(cm_hr.exception))

        # 5) ส่งเมลล้มเหลวแล้วไม่เหลือ OTP ค้างในฐานข้อมูลและไม่นับโควตา
        with patch.object(email_service, "send_mail", side_effect=ValueError("ส่งอีเมลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")):
            with self.assertRaises(ValueError):
                otp_service.request_otp("failmail@example.com", purpose="signup", now=6000.0)
        row = db.query_one("SELECT value FROM settings WHERE key = ?", (otp_service.OTP_SETTING_KEY,))
        otp_map = json.loads(row["value"]) if row and row["value"] else {}
        self.assertNotIn("signup:failmail@example.com", otp_map)

        # ขอใหม่ทันทีที่ 6001.0 ต้องไม่ติด cooldown เพราะครั้งก่อนส่งล้มเหลว
        with patch.object(email_service, "send_mail", side_effect=_fake_send):
            res_ok = otp_service.request_otp("failmail@example.com", purpose="signup", now=6001.0)
            self.assertEqual(res_ok["email"], "fa***@example.com")

    def test_03_concurrent_otp_verification_succeeds_at_most_once(self):
        captured: list[tuple] = []
        with patch.object(email_service, "send_mail", side_effect=lambda *a, **kw: captured.append(a)):
            otp_service.request_otp("race@example.com", purpose="signup", now=7000.0)
            code = self._extract_otp_from_text(captured[-1][2])

        def _try_verify(_idx: int) -> bool:
            try:
                return otp_service.verify_and_consume_otp("race@example.com", code, purpose="signup", now=7005.0)
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(_try_verify, range(6)))

        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 5)

    def test_04_ip_rate_limit_429_and_ignores_x_forwarded_for(self):
        client = TestClient(self.app)
        server_auth.reset_rate_limits()

        with patch.object(email_service, "send_mail", return_value=None):
            for i in range(10):
                # พยายามปลอม X-Forwarded-For ทุกคำขอ
                r = client.post(
                    "/api/customer/member/reset/start",
                    json={"email": f"user{i}@example.com"},
                    headers={"X-Forwarded-For": f"203.0.113.{i + 1}"},
                )
                self.assertEqual(r.status_code, 200)

            # คำขอที่ 11 จากเครื่องเดียวกัน แม้เปลี่ยน X-Forwarded-For ต้องได้ 429
            r_11 = client.post(
                "/api/customer/member/reset/start",
                json={"email": "user11@example.com"},
                headers={"X-Forwarded-For": "198.51.100.99"},
            )
            self.assertEqual(r_11.status_code, 429)
            self.assertIn("เกินจำนวนครั้ง", r_11.json()["detail"])

    def test_05_password_hashing_migration_demo_accounts_login_rules_and_google_removed(self):
        # 1) จำลองฐานข้อมูลเดิมที่มี password ข้อความตรง ๆ และมีรายการ OTP แบบเก่าที่มี key "code"
        legacy_members = [
            {
                "id": 1,
                "name": "สมชาย สายหมูกระทะ",
                "email": "somchai@gmail.com",
                "phone": "081-234-5678",
                "password": "123456",
                "provider": "password",
                "claimed_promos": ["TONMAKHA50"],
                "created_at": "2026-10-01 12:00:00",
                "sample_history": member_service.DEFAULT_SAMPLE_HISTORY,
            },
            {
                "id": 2,
                "name": "แพรวา ชอบกินหมู",
                "email": "praewa.google@gmail.com",
                "phone": "089-888-7766",
                "password": "",
                "provider": "google",
                "claimed_promos": [],
                "created_at": "2026-10-12 18:00:00",
                "sample_history": [],
            },
            {
                "id": 3,
                "name": "ลูกค้าจริง เดิม",
                "email": "realold@example.com",
                "phone": "082-333-4444",
                "password": "oldPassword88",
                "provider": "password",
                "claimed_promos": [],
                "created_at": "2026-10-20 12:00:00",
                "sample_history": [],
            },
        ]
        with db.transaction() as c:
            c.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (member_service.MEMBERS_SETTING_KEY, json.dumps(legacy_members, ensure_ascii=False), db.now_str()),
            )
            c.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (otp_service.OTP_SETTING_KEY, json.dumps({"somchai@gmail.com": {"code": "654321"}}), db.now_str()),
            )

        # โหลดสมาชิก -> ต้องย้าย password เป็น password_hash (bcrypt) ลบฟิลด์ password และลบ OTP เก่าทิ้ง
        loaded = member_service._load_raw_members()
        self.assertEqual(len(loaded), 3)
        raw_row = db.query_one("SELECT value FROM settings WHERE key = ?", (member_service.MEMBERS_SETTING_KEY,))
        persisted = json.loads(raw_row["value"])
        for m in persisted:
            self.assertNotIn("password", m)
            self.assertIn("password_hash", m)
        self.assertTrue(persisted[0]["password_hash"].startswith("$2"))
        self.assertTrue(persisted[0].get("demo"))
        self.assertTrue(persisted[1].get("demo"))
        self.assertFalse(persisted[2].get("demo", False))

        otp_row = db.query_one("SELECT value FROM settings WHERE key = ?", (otp_service.OTP_SETTING_KEY,))
        self.assertEqual(json.loads(otp_row["value"]), {})

        # 2) เมื่อ MEMBER_DEMO_ACCOUNTS=0: บัญชีตัวอย่าง somchai@gmail.com ล็อกอินไม่ได้ แต่ข้อมูล/ประวัติยังอยู่ในฐานข้อมูล
        config.MEMBER_DEMO_ACCOUNTS = 0
        with self.assertRaises(ValueError) as cm_demo:
            member_service.login_member("somchai@gmail.com", "123456")
        self.assertEqual(str(cm_demo.exception), "อีเมลหรือรหัสผ่านไม่ถูกต้อง")

        # เมื่อ MEMBER_DEMO_ACCOUNTS=1: somchai@gmail.com ล็อกอินได้ด้วยรหัสที่แฮชแล้ว
        config.MEMBER_DEMO_ACCOUNTS = 1
        server_auth.reset_rate_limits()
        somchai = member_service.login_member("somchai@gmail.com", "123456")
        self.assertEqual(somchai["email"], "somchai@gmail.com")
        self.assertGreaterEqual(len(somchai["history"]), 2)
        config.MEMBER_DEMO_ACCOUNTS = 0

        # 3) บัญชีจริงเดิม (realold@example.com) ล็อกอินด้วยอีเมลได้ แต่ล็อกอินด้วยชื่อไม่ได้
        real_logged = member_service.login_member("realold@example.com", "oldPassword88")
        self.assertEqual(real_logged["email"], "realold@example.com")

        with self.assertRaises(ValueError) as cm_name:
            member_service.login_member("ลูกค้าจริง เดิม", "oldPassword88")
        with self.assertRaises(ValueError) as cm_wrong_pw:
            member_service.login_member("realold@example.com", "wrongPassword")
        with self.assertRaises(ValueError) as cm_no_email:
            member_service.login_member("nonexistent@example.com", "oldPassword88")
        with self.assertRaises(ValueError) as cm_google_provider:
            config.MEMBER_DEMO_ACCOUNTS = 1
            member_service.login_member("praewa.google@gmail.com", "")
        config.MEMBER_DEMO_ACCOUNTS = 0

        # ข้อความล็อกอินผิดต้องเหมือนกันทุกกรณี
        expected_err = "อีเมลหรือรหัสผ่านไม่ถูกต้อง"
        self.assertEqual(str(cm_name.exception), expected_err)
        self.assertEqual(str(cm_wrong_pw.exception), expected_err)
        self.assertEqual(str(cm_no_email.exception), expected_err)
        self.assertEqual(str(cm_google_provider.exception), expected_err)

        # 4) ล็อกอินผิดซ้ำครบ LOGIN_MAX_ATTEMPTS ถูกล็อก (HTTP 429)
        server_auth.reset_rate_limits()
        client = TestClient(self.app)
        for _ in range(config.LOGIN_MAX_ATTEMPTS):
            r_fail = client.post(
                "/api/customer/member/login",
                json={"identifier": "realold@example.com", "password": "badpassword"},
            )
            self.assertEqual(r_fail.status_code, 400)
            self.assertEqual(r_fail.json()["detail"], expected_err)
        r_locked = client.post(
            "/api/customer/member/login",
            json={"identifier": "realold@example.com", "password": "oldPassword88"},
        )
        self.assertEqual(r_locked.status_code, 429)
        self.assertIn("กรอกรหัสผ่านผิดเกินกำหนด", r_locked.json()["detail"])

        # 5) /api/customer/member/google ไม่มีอยู่แล้ว
        server_auth.reset_rate_limits()
        r_google = client.post("/api/customer/member/google", json={"email": "realold@example.com"})
        self.assertIn(r_google.status_code, (404, 405))

    def test_06_password_reset_uniform_response_and_session_revocation(self):
        client_a = TestClient(self.app)
        client_b = TestClient(self.app)

        # สมัครสมาชิกและล็อกอินทั้งใน client_a และ client_b
        self._signup_via_api(
            client_a,
            name="กานดา สายปิ้งย่าง",
            email="kanda@example.com",
            phone="086-555-7788",
            password="InitialPassword123",
        )
        r_login_b = client_b.post(
            "/api/customer/member/login",
            json={"identifier": "kanda@example.com", "password": "InitialPassword123"},
        )
        self.assertEqual(r_login_b.status_code, 200)
        self.assertEqual(client_a.get("/api/customer/state").json()["member"]["email"], "kanda@example.com")
        self.assertEqual(client_b.get("/api/customer/state").json()["member"]["email"], "kanda@example.com")

        # ทดสอบลืมรหัสผ่าน: อีเมลไม่มีในระบบ vs มีในระบบ ต้องตอบข้อความเหมือนกัน
        captured: list[tuple] = []
        with patch.object(email_service, "send_mail", side_effect=lambda *a, **kw: captured.append(a)):
            r_non = client_a.post("/api/customer/member/reset/start", json={"email": "nobody@example.com"})
            self.assertEqual(r_non.status_code, 200)
            self.assertEqual(len(captured), 0)

            r_exist = client_a.post("/api/customer/member/reset/start", json={"email": "kanda@example.com"})
            self.assertEqual(r_exist.status_code, 200)
            self.assertEqual(len(captured), 1)
            self.assertEqual(r_non.json()["message"], r_exist.json()["message"])
            reset_otp = self._extract_otp_from_text(captured[-1][2])

        # ตั้งรหัสผ่านใหม่
        r_verify = client_a.post(
            "/api/customer/member/reset/verify",
            json={
                "email": "kanda@example.com",
                "otp_code": reset_otp,
                "new_password": "UpdatedPassword456",
                "new_password_confirm": "UpdatedPassword456",
            },
        )
        self.assertEqual(r_verify.status_code, 200)

        # คุกกี้เดิมทั้งใน client_a และ client_b ต้องใช้ไม่ได้ทันที (member เป็น None)
        self.assertIsNone(client_a.get("/api/customer/state").json()["member"])
        self.assertIsNone(client_b.get("/api/customer/state").json()["member"])

        # ล็อกอินด้วยรหัสผ่านเก่าต้องไม่ผ่าน ต้องใช้รหัสผ่านใหม่เท่านั้น
        server_auth.reset_rate_limits()
        r_old_pw = client_a.post(
            "/api/customer/member/login",
            json={"identifier": "kanda@example.com", "password": "InitialPassword123"},
        )
        self.assertEqual(r_old_pw.status_code, 400)

        r_new_pw = client_a.post(
            "/api/customer/member/login",
            json={"identifier": "kanda@example.com", "password": "UpdatedPassword456"},
        )
        self.assertEqual(r_new_pw.status_code, 200)
        self.assertEqual(r_new_pw.json()["member"]["email"], "kanda@example.com")

    def test_07_account_and_session_isolation_across_devices_and_roles(self):
        client_a = TestClient(self.app)
        client_b = TestClient(self.app)
        client_unauth = TestClient(self.app)
        staff_client = TestClient(self.app)
        owner_client = TestClient(self.app)

        staff_client.post("/api/staff/login", json={"username": "staff1", "password": "staff1234"})
        owner_client.post("/api/staff/login", json={"username": "owner", "password": "owner1234"})

        # สมัครสมาชิก A และ B คนละเบราว์เซอร์
        self._signup_via_api(client_a, "สมาชิก A", "member_a@example.com", "081-111-1111", "PasswordA123")
        server_auth.reset_rate_limits()
        self._signup_via_api(client_b, "สมาชิก B", "member_b@example.com", "089-222-2222", "PasswordB123")

        # โต๊ะ 1: สมาชิก A สแกนเข้าโต๊ะและเก็บโค้ดส่วนลด TONMAKHA50
        t1 = table_service.get_table_by_no(1)
        scan_a = client_a.post("/api/customer/scan", json={"table_no": 1, "k": t1["secret_key"]}).json()
        sid1 = scan_a["session_id"]
        staff_client.post(f"/api/staff/tables/{sid1}/confirm")
        weigh_service.add_entry(sid1, None, 1500, user_id=2)

        client_a.post("/api/customer/member/promo/claim", json={"code": "TONMAKHA50"})
        client_a.post("/api/customer/member/promo/apply", json={"code": "TONMAKHA50"})

        state_a = client_a.get("/api/customer/state").json()
        state_b = client_b.get("/api/customer/state").json()

        # 1) สมาชิก A กับ B ต้องไม่เห็นข้อมูลของกันและกัน
        self.assertEqual(state_a["member"]["email"], "member_a@example.com")
        self.assertIn("TONMAKHA50", state_a["member"]["claimed_promos"])
        self.assertEqual(state_b["member"]["email"], "member_b@example.com")
        self.assertNotIn("TONMAKHA50", state_b["member"]["claimed_promos"])
        self.assertNotIn("member_a@example.com", json.dumps(state_b, ensure_ascii=False))

        # 2) อุปกรณ์ที่ไม่ได้ล็อกอินที่อยู่ในรอบโต๊ะเดียวกันกับสมาชิก A ต้องไม่ได้ข้อมูลส่วนตัวของสมาชิก A
        ctx_a = state_a["context"]
        same_table_token = server_auth.sign_payload({
            "st": {"device_id": ctx_a["device_id"], "session_id": sid1, "cart": {}},
            "exp": 9999999999,
        })
        client_unauth.cookies.set(config.CUSTOMER_COOKIE_NAME, same_table_token)
        state_unauth = client_unauth.get("/api/customer/state").json()
        self.assertTrue(state_unauth["has_session"])
        self.assertIsNone(state_unauth["member"])
        self.assertIsNone(state_unauth["applied_promo_code"])
        self.assertNotIn("member_a@example.com", json.dumps(state_unauth, ensure_ascii=False))
        # แต่ส่วนลดในบิลของโต๊ะยังคงคำนวณให้โต๊ะได้ตามปกติ
        self.assertEqual(state_unauth["snapshot"]["member_discount"], 50.0)

        # 3) ส่ง member_id ปลอมใน body หรือ query ต้องไม่มีผล
        r_fake_query = client_unauth.get(f"/api/customer/state?member_id={state_a['member']['id']}").json()
        self.assertIsNone(r_fake_query["member"])
        r_fake_claim = client_unauth.post(
            "/api/customer/member/promo/claim",
            json={"code": "TONMAKHA50", "member_id": state_a["member"]["id"]},
        )
        self.assertEqual(r_fake_claim.status_code, 400)

        # 4) คุกกี้ปลอมที่มี member_id แต่ไม่มี mfp ที่ถูกต้องต้องถูกปฏิเสธ
        forged_mfp_token = server_auth.sign_payload({
            "st": {
                "device_id": ctx_a["device_id"],
                "session_id": sid1,
                "member_id": state_a["member"]["id"],
                "mfp": "0000000000000000",
            },
            "exp": 9999999999,
        })
        client_unauth.cookies.set(config.CUSTOMER_COOKIE_NAME, forged_mfp_token)
        self.assertIsNone(client_unauth.get("/api/customer/state").json()["member"])

        # 5) คุกกี้ลูกค้าใช้เรียก /api/staff/* และ /api/owner/* ไม่ได้ และคุกกี้พนักงานไม่ให้ตัวตนสมาชิก
        self.assertEqual(client_a.get("/api/staff/tables").status_code, 401)
        self.assertEqual(client_a.get("/api/owner/members").status_code, 401)
        self.assertIsNone(staff_client.get("/api/customer/state").json()["member"])

        # 6) ไม่มีสมาชิกถูกสร้างในตาราง users และฐานข้อมูลยังคงมี 17 ตาราง
        user_rows = db.query_all("SELECT username FROM users")
        usernames = {r["username"] for r in user_rows}
        self.assertNotIn("member_a@example.com", usernames)
        self.assertNotIn("member_b@example.com", usernames)
        self.assertEqual(len(schema.list_tables()), 17)

        # 7) response ของ owner และ settings_service.get_all() ไม่มี password_hash หรือข้อมูล OTP
        owner_members_res = owner_client.get("/api/owner/members")
        self.assertEqual(owner_members_res.status_code, 200)
        owner_txt = owner_members_res.text
        self.assertNotIn("password_hash", owner_txt)
        self.assertNotIn("code_hash", owner_txt)

        all_settings = settings_service.get_all()
        self.assertNotIn("members_registry_json", all_settings)
        self.assertNotIn("members_otp_sessions_json", all_settings)


if __name__ == "__main__":
    unittest.main(verbosity=2)
