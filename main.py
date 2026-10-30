"""main.py — เปิดแอปร้านต้นมะค่า (เว็บแอป HTML/CSS/JS สำหรับพนักงาน/เจ้าของ + มือถือลูกค้า ในเซิร์ฟเวอร์เดียว)"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import traceback
from urllib.parse import urlparse
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from server.jobs import prepare_environment  # noqa: E402


class WebHandle:
    def __init__(self, mode: str):
        self.mode = mode
        self.error: str | None = None
        self.thread: threading.Thread | None = None
        self.process: subprocess.Popen | None = None

    @property
    def running(self) -> bool:
        if self.mode == "thread":
            return self.thread is not None and self.thread.is_alive()
        if self.mode == "process":
            return self.process is not None and self.process.poll() is None
        return False

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()


def start_web(mode: str = "thread", host: str | None = None, port: int | None = None) -> WebHandle:
    handle = WebHandle(mode)
    if mode == "off":
        return handle
    h = host or config.WEB_HOST
    p = port or config.WEB_PORT
    if mode == "process":
        try:
            handle.process = subprocess.Popen(
                [sys.executable, str(ROOT / "main.py"), "--no-browser", "--host", str(h), "--port", str(p)],
                cwd=str(ROOT),
            )
        except Exception as e:
            handle.error = f"เปิดเว็บเซิร์ฟเวอร์ (โปรเซสแยก) ไม่สำเร็จ: {e}"
        return handle
    try:
        import uvicorn
        from server.app import app
    except ImportError as e:
        handle.error = f"เปิดเว็บเซิร์ฟเวอร์ไม่ได้ — ยังไม่ได้ติดตั้งไลบรารี ({e}) รัน: pip install -r requirements.txt"
        return handle

    def _run() -> None:
        try:
            uvicorn.run(app, host=h, port=p, log_level="warning")
        except BaseException as e:
            handle.error = f"เว็บเซิร์ฟเวอร์หยุดทำงาน: {e}"
            traceback.print_exc()

    handle.thread = threading.Thread(target=_run, name="web-server", daemon=True)
    handle.thread.start()
    return handle


def _has_default_passwords() -> list[str]:
    from database import db
    from services import auth_service

    weak = []
    for uname, default_pw in (("owner", "owner1234"), ("staff1", "staff1234")):
        row = db.query_one("SELECT active, password_hash FROM users WHERE username = ?", (uname,))
        if row and row["active"] and auth_service.verify_password(default_pw, row["password_hash"]):
            weak.append(f"{uname}/{default_pw}")
    return weak


def run_system_check() -> int:
    from database import schema
    from services import checkout_service, qr_service, settings_service

    print(f"=== ตรวจสอบความพร้อมของระบบ: {config.APP_NAME} ===")
    errors: list[str] = []
    warnings: list[str] = []

    required_mods = ("fastapi", "uvicorn", "multipart", "PIL", "bcrypt", "reportlab", "qrcode")
    missing_mods = []
    for mod in required_mods:
        try:
            __import__(mod)
        except ImportError:
            missing_mods.append(mod)
    if missing_mods:
        errors.append(f"ขาดไลบรารี Python: {', '.join(missing_mods)}")
    else:
        print("[OK] ไลบรารี Python ครบถ้วน (fastapi, uvicorn, python-multipart, pillow, bcrypt, reportlab, qrcode)")

    try:
        import shutil as _shutil, tempfile as _tempfile
        _orig_db = config.DB_PATH
        _orig_bk = config.BACKUPS_DIR
        _tmp_d = Path(_tempfile.mkdtemp(prefix="tonmakha_chk_"))
        try:
            if Path(_orig_db).is_file():
                _shutil.copy2(_orig_db, _tmp_d / "chk.db")
            config.DB_PATH = _tmp_d / "chk.db"
            config.BACKUPS_DIR = _tmp_d / "backups"
            prepare_environment()
            tables = set(schema.list_tables())
        finally:
            config.DB_PATH = _orig_db
            config.BACKUPS_DIR = _orig_bk
            _shutil.rmtree(_tmp_d, ignore_errors=True)
        expected = set(schema.TABLE_NAMES)
        missing_tables = expected - tables
        extra_tables = tables - expected
        if missing_tables or len(tables) != 17:
            errors.append(f"ตารางในฐานข้อมูลไม่ตรง 17 ตาราง (พบ {len(tables)} ตาราง, ขาด: {missing_tables}, เกิน: {extra_tables})")
        else:
            print(f"[OK] ฐานข้อมูล SQLite พร้อมใช้งาน ครบ {len(tables)} ตาราง")
    except Exception as e:
        errors.append(f"ตรวจสอบฐานข้อมูลไม่สำเร็จ: {e}")

    expected_fonts = (
        "Prompt-Thin.ttf", "Prompt-ThinItalic.ttf",
        "Prompt-ExtraLight.ttf", "Prompt-ExtraLightItalic.ttf",
        "Prompt-Light.ttf", "Prompt-LightItalic.ttf",
        "Prompt-Regular.ttf", "Prompt-Italic.ttf",
        "Prompt-Medium.ttf", "Prompt-MediumItalic.ttf",
        "Prompt-SemiBold.ttf", "Prompt-SemiBoldItalic.ttf",
        "Prompt-Bold.ttf", "Prompt-BoldItalic.ttf",
        "Prompt-ExtraBold.ttf", "Prompt-ExtraBoldItalic.ttf",
        "Prompt-Black.ttf", "Prompt-BlackItalic.ttf",
    )
    missing_fonts = [f for f in expected_fonts if not (Path(config.FONTS_DIR) / f).is_file()]
    try:
        reg_f, bold_f = checkout_service._find_thai_fonts()
        print(f"[OK] ฟอนต์ใบเสร็จ PDF: {reg_f.name}, {bold_f.name}")
    except Exception as e:
        errors.append(f"ฟอนต์สำหรับสร้าง PDF ไม่พร้อม: {e}")

    if missing_fonts:
        warnings.append(f"ไฟล์ฟอนต์ Prompt บางน้ำหนักไม่พบ: {', '.join(missing_fonts)}")
    else:
        print(f"[OK] ฟอนต์ Prompt ครบทุกน้ำหนัก ({len(expected_fonts)} ไฟล์)")

    required_frontend = (
        "shared/css/fonts.css",
        "shared/css/tokens.css",
        "shared/css/base.css",
        "shared/css/table.css",
        "shared/css/components.css",
        "shared/js/api.js",
        "shared/js/format.js",
        "shared/js/dialogs.js",
        "shared/js/toast.js",
        "shared/js/data-table.js",
        "shared/js/date-picker.js",
        "shared/js/status-badge.js",
        "customer/index.html",
        "staff/index.html",
    )
    missing_fe = [rel for rel in required_frontend if not (Path(config.FRONTEND_DIR) / rel).is_file()]
    if missing_fe:
        errors.append(f"ขาดไฟล์ Frontend: {', '.join(missing_fe)}")
    else:
        print(f"[OK] ไฟล์ Frontend (HTML/CSS/JS) ครบถ้วน ({len(required_frontend)} ไฟล์หลัก)")

    try:
        pp_qr = qr_service.generate_promptpay_qr(100)
        print(f"[OK] PromptPay QR พร้อมใช้งาน ({pp_qr['promptpay_id']} - {pp_qr['promptpay_name']})")
    except Exception as e:
        warnings.append(f"ตั้งค่า PromptPay ยังไม่ถูกต้อง: {e}")

    base_url = settings_service.get_setting("public_base_url", config.PUBLIC_BASE_URL) or ""
    host_name = (urlparse(base_url).hostname or "").lower()
    if host_name in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        warnings.append(
            f"public_base_url ยังเป็น '{base_url}' (localhost) — มือถือลูกค้าจะสแกนเข้าไม่ได้จนกว่าจะตั้งเป็น IP เครื่องร้านที่หน้า 'ตั้งค่า'"
        )
    else:
        print(f"[OK] ลิงก์เว็บลูกค้า (public_base_url): {base_url}")

    # ตรวจสอบการตั้งค่า SMTP และ OTP_SECRET (เตือนแบบไม่ทำให้ล้ม และไม่แสดงค่าลับ)
    smtp_ready = bool(config.SMTP_HOST and config.SMTP_PORT and config.SMTP_USER and config.SMTP_PASSWORD)
    if not smtp_ready:
        warnings.append(
            "ยังไม่ได้ตั้งค่าอีเมลผู้ส่ง (SMTP_USER / SMTP_PASSWORD ในไฟล์ .env) — ระบบส่งรหัส OTP ทางอีเมลจะยังใช้งานไม่ได้ (ดูตัวอย่างใน .env.example)"
        )
    else:
        print(f"[OK] ตั้งค่า SMTP สำหรับส่งอีเมล OTP แล้ว ({config.SMTP_HOST}:{config.SMTP_PORT})")

    raw_otp_env = os.getenv("OTP_SECRET", "").strip()
    if not raw_otp_env or getattr(config, "OTP_SECRET_IS_EPHEMERAL", False):
        warnings.append(
            "ยังไม่ได้ตั้งค่า OTP_SECRET ใน .env — ระบบใช้คีย์สุ่มชั่วคราวต่อโปรเซส (รหัส OTP ที่ส่งไปแล้วจะใช้ไม่ได้หากรีสตาร์ตเซิร์ฟเวอร์)"
        )
    elif len(raw_otp_env) < 32:
        warnings.append(
            "OTP_SECRET ใน .env สั้นกว่า 32 ตัวอักษร — แนะนำให้ตั้งค่าความยาวอย่างน้อย 32 ตัวอักษรเพื่อความปลอดภัย"
        )
    else:
        print("[OK] ตั้งค่า OTP_SECRET สำหรับแฮชรหัส OTP แล้ว")

    weak_accounts = _has_default_passwords()
    if weak_accounts:
        warnings.append(
            f"พบบัญชีที่ยังใช้รหัสผ่านเริ่มต้น ({', '.join(weak_accounts)}) — กรุณาเปลี่ยนรหัสผ่านที่หน้า 'ผู้ใช้' ก่อนใช้งานจริง"
        )
    else:
        print("[OK] บัญชีเริ่มต้นเปลี่ยนรหัสผ่านแล้ว")

    for w in warnings:
        print(f"[WARN] ⚠️  {w}")
    for err in errors:
        print(f"[ERROR] ❌ {err}")

    if errors:
        print("=== ผลการตรวจสอบ: ไม่ผ่าน ===")
        return 1
    print("=== ผลการตรวจสอบ: ผ่านพร้อมใช้งาน ===")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=config.APP_NAME)
    parser.add_argument("--host", default=config.WEB_HOST)
    parser.add_argument("--port", type=int, default=config.WEB_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        return run_system_check()

    info = prepare_environment()
    if info["seeded"]:
        print("สร้างฐานข้อมูลใหม่แล้ว — บัญชีเริ่มต้น owner/owner1234 และ staff1/staff1234 (ต้องเปลี่ยนรหัสผ่านที่หน้า 'ผู้ใช้')")
    if info["backup"]:
        print(f"สำรองอัตโนมัติ: {info['backup']['filename']}")

    if getattr(config, "OTP_SECRET_IS_EPHEMERAL", False):
        print("⚠️  คำเตือน: ยังไม่ได้ตั้งค่า OTP_SECRET ใน .env — ระบบใช้คีย์สุ่มชั่วคราวต่อโปรเซส (OTP ที่ส่งไปแล้วจะใช้ไม่ได้หลังรีสตาร์ต)")

    weak = _has_default_passwords()
    if weak and args.host not in ("127.0.0.1", "::1", "localhost"):
        print("=" * 72)
        print(f"⚠️  คำเตือนความปลอดภัย: เซิร์ฟเวอร์เปิดรับเครือข่าย ({args.host}) และยังมีรหัสผ่านเริ่มต้นอยู่: {', '.join(weak)}")
        print("   (หน้า /staff ถูกจำกัดเฉพาะเครื่องที่รันเซิร์ฟเวอร์โดยค่าเริ่มต้น แต่ควรเปลี่ยนรหัสผ่านที่หน้า 'ผู้ใช้' ทันที)")
        print("=" * 72)

    from services import settings_service
    staff_url = f"http://127.0.0.1:{args.port}/staff"
    pub_url = settings_service.get_setting("public_base_url", config.PUBLIC_BASE_URL)
    print(f"เปิดเซิร์ฟเวอร์ {config.APP_NAME}")
    print(f"  • หน้าพนักงาน/เจ้าของร้าน (เครื่องนี้เท่านั้น): {staff_url}")
    print(f"  • ฐานลิงก์ QR มือถือลูกค้า:                 {pub_url}")

    if not args.no_browser:
        def _open_browser():
            time.sleep(1.0)
            try:
                webbrowser.open(staff_url)
            except Exception:
                pass
        threading.Thread(target=_open_browser, daemon=True).start()

    import uvicorn
    from server.app import app
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
