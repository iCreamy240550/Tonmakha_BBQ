"""tests/test_api_security.py — ชุดทดสอบความปลอดภัยของเว็บและ API ตาม PLAN.md หัวข้อ 6 และ P1-19"""
from __future__ import annotations

import ast
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import test_all_features  # noqa: F401

import config
from database import db, seed
from server import auth as server_auth
from server.app import create_app
from services import auth_service, qr_service, shop_service, table_service


class ApiSecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="tonmakha_sec_test_"))
        self._orig_db = config.DB_PATH
        self._orig_uploads = config.UPLOADS_DIR
        self._orig_menu_img = config.MENU_IMAGE_DIR
        self._orig_exports = config.EXPORTS_DIR
        self._orig_qr = config.QR_DIR
        self._orig_backups = config.BACKUPS_DIR
        self._orig_assets = config.ASSETS_DIR
        self._orig_fonts = config.FONTS_DIR
        self._orig_secret = config.SECRET_FILE

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
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_customer_session_isolation_and_cookie_tampering(self):
        client_a = TestClient(self.app)
        client_b = TestClient(self.app)

        t1 = table_service.get_table_by_no(1)
        scan_a = client_a.post("/api/customer/scan", json={"table_no": 1, "k": t1["secret_key"]}).json()
        self.assertEqual(scan_a["kind"], "ok")
        sid = scan_a["session_id"]

        scan_b = client_b.post("/api/customer/scan", json={"table_no": 1, "k": t1["secret_key"]}).json()
        self.assertEqual(scan_b["kind"], "fail")
        self.assertEqual(scan_b["code"], "table_busy")

        forged_token = server_auth.sign_payload({
            "st": {"device_id": "attacker_device_1234567890", "session_id": sid},
            "exp": 9999999999,
        })
        client_b.cookies.set(config.CUSTOMER_COOKIE_NAME, forged_token)
        state_b = client_b.get("/api/customer/state").json()
        self.assertFalse(state_b["has_session"])
        self.assertIsNone(state_b["snapshot"])

        client_b.cookies.set(config.CUSTOMER_COOKIE_NAME, "tampered.invalid_signature")
        self.assertFalse(client_b.get("/api/customer/state").json()["has_session"])

    def test_02_role_based_access_control_and_password_revocation(self):
        staff_client = TestClient(self.app)
        unauth_client = TestClient(self.app)

        self.assertEqual(unauth_client.get("/api/staff/tables").status_code, 401)
        self.assertEqual(unauth_client.get("/api/owner/dashboard/overview").status_code, 401)

        res = staff_client.post("/api/staff/login", json={"username": "staff1", "password": "staff1234"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(staff_client.get("/api/staff/tables").status_code, 200)

        owner_endpoints = [
            ("GET", "/api/owner/dashboard/overview"),
            ("GET", "/api/owner/dashboard/report"),
            ("GET", "/api/owner/menu"),
            ("GET", "/api/owner/stock"),
            ("GET", "/api/owner/promos"),
            ("GET", "/api/owner/tables_manage"),
            ("GET", "/api/owner/users"),
            ("GET", "/api/owner/settings"),
            ("GET", "/api/owner/logs"),
            ("GET", "/api/owner/backups"),
        ]
        for method, url in owner_endpoints:
            r = staff_client.request(method, url)
            self.assertEqual(r.status_code, 403, f"Staff should not access {url}")

        auth_service.change_password(2, "newpass5678", by_user_id=1)
        self.assertEqual(staff_client.get("/api/staff/tables").status_code, 401)

    def test_03_proxy_headers_and_network_restriction(self):
        client = TestClient(self.app)

        for header_name, header_val in (
            ("X-Forwarded-For", "203.0.113.50"),
            ("Forwarded", "for=203.0.113.50"),
            ("CF-Connecting-IP", "203.0.113.50"),
        ):
            r_page = client.get("/staff", headers={header_name: header_val})
            self.assertEqual(r_page.status_code, 403)
            r_api = client.post(
                "/api/staff/login",
                json={"username": "owner", "password": "owner1234"},
                headers={header_name: header_val},
            )
            self.assertEqual(r_api.status_code, 403)

        r_cust = client.get("/api/customer/state", headers={"X-Forwarded-For": "203.0.113.50"})
        self.assertEqual(r_cust.status_code, 200)

    def test_04_csrf_origin_check_and_rate_limiting(self):
        client = TestClient(self.app)
        client.post("/api/staff/login", json={"username": "owner", "password": "owner1234"})

        evil_res = client.post(
            "/api/staff/shop/close",
            json={"force": True},
            headers={"Origin": "http://evil-attacker.example.com"},
        )
        self.assertEqual(evil_res.status_code, 403)

        server_auth.reset_rate_limits()
        brute_client = TestClient(self.app)
        for _ in range(config.LOGIN_MAX_ATTEMPTS):
            r = brute_client.post("/api/staff/login", json={"username": "owner", "password": "wrongpassword"})
            self.assertEqual(r.status_code, 401)
        r_locked = brute_client.post("/api/staff/login", json={"username": "owner", "password": "owner1234"})
        self.assertEqual(r_locked.status_code, 429)
        self.assertIn("กรอกรหัสผ่านผิดเกินกำหนด", r_locked.json()["detail"])

    def test_05_no_secrets_leaked_and_qr_static_blocked(self):
        client = TestClient(self.app)
        client.post("/api/staff/login", json={"username": "owner", "password": "owner1234"})

        qr_service.generate_all_qr()
        self.assertEqual(client.get("/assets/qr_codes/table_1.png").status_code, 403)
        self.assertEqual(client.get("/qr_codes/table_1.png").status_code, 403)

        for url in ("/api/staff/me", "/api/staff/tables", "/api/owner/users", "/api/owner/tables_manage"):
            txt = client.get(url).text
            self.assertNotIn("password_hash", txt)
            self.assertNotIn("secret_key", txt)

    def test_06_customer_never_touches_activity_or_alerts(self):
        src = (ROOT / "server" / "routes" / "customer.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        called_attrs = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        self.assertNotIn("touch_session", called_attrs)
        self.assertNotIn("check_alerts", called_attrs)
        self.assertNotIn("pop_sound_alerts", called_attrs)

        t1 = table_service.get_table_by_no(1)
        cust = TestClient(self.app)
        scan = cust.post("/api/customer/scan", json={"table_no": 1, "k": t1["secret_key"]}).json()
        sid = scan["session_id"]
        table_service.confirm_session(sid, user_id=1)

        old_time = "2026-01-01 10:00:00"
        db.execute("UPDATE table_sessions SET last_activity = ? WHERE id = ?", (old_time, sid))
        for _ in range(3):
            res = cust.get("/api/customer/state")
            self.assertEqual(res.status_code, 200)
        self.assertEqual(table_service.get_session(sid)["last_activity"], old_time)


if __name__ == "__main__":
    unittest.main()
