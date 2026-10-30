"""web/server.py — เว็บมือถือลูกค้า (NiceGUI) : ลงทะเบียนหน้า + สตาร์ทเซิร์ฟเวอร์

เส้นทาง:
    /t/<เลขโต๊ะ>?k=<รหัสลับ>   หน้าเข้าจาก QR (pages/enter.py)
    /s                          หน้าหลักของลูกค้า สลับเนื้อหาตามสถานะรอบ (รอยืนยัน/สั่งอาหาร/บิล/จบ)
    /                           บอกให้สแกน QR
    /logo.png                   โลโก้ร้านไฟล์เดียว (ไม่เปิดโฟลเดอร์ assets ทั้งหมดเพราะมีรูป QR ที่มีรหัสลับ)
    /fonts/...                  ไฟล์ฟอนต์ Prompt สำหรับแสดงผลบนเว็บมือถือลูกค้าโดยไม่ต้องพึ่งอินเทอร์เน็ต
    /uploads/...                รูปเมนูที่เจ้าของร้านอัปโหลด (โฟลเดอร์ assets/uploads/)

ใช้งาน:  run()                -> เปิดเซิร์ฟเวอร์ (บล็อก) ใช้กับ run_web.py
         start_in_thread()   -> เปิดเป็น thread (ใช้กับ main.py ที่เปิดแอป PC พร้อมกัน)
"""
from __future__ import annotations

import secrets
import threading

from nicegui import app, ui

import config
from web import components, session
from web.pages import bill, closed, enter, notice, order, waiting

POLL_SECONDS = 3.0                      # ลูกค้าเช็คสถานะ/ข้อความ/สต๊อกทุกกี่วินาที
SECRET_FILE = config.BASE_DIR / "web_secret.key"
_registered = False


def get_storage_secret() -> str:
    """รหัสเซ็นคุกกี้/storage ของ NiceGUI — สุ่มครั้งแรกแล้วเก็บในไฟล์ web_secret.key (ไม่เก็บใน DB ไม่ log)
    ต้องคงที่ข้ามการรีสตาร์ต ไม่งั้นลูกค้าที่กำลังใช้งานจะหลุดจากรอบ"""
    try:
        text = SECRET_FILE.read_text(encoding="utf-8").strip()
        if len(text) >= 32:
            return text
    except FileNotFoundError:
        pass
    text = secrets.token_hex(32)
    SECRET_FILE.write_text(text, encoding="utf-8")
    try:
        SECRET_FILE.chmod(0o600)
    except OSError:
        pass
    return text


# ---------------------------------------------------------------- หน้าหลักของลูกค้า (/s)

def _root_page() -> None:
    components.apply_theme()
    with components.page_column():
        components.header(config.APP_NAME_SHORT)
        closed.render_no_session()


def _customer_page() -> None:
    """หน้าหลักของลูกค้า: โหลดรอบที่เครื่องนี้จำไว้ แล้ววาดตามสถานะ ; โพลทุก POLL_SECONDS วินาที
    วาดใหม่เฉพาะเมื่อ signature ของข้อมูลเปลี่ยน (กันกะพริบ/ค่าที่กรอกหาย)"""
    components.apply_theme()
    storage = app.storage.user
    ctx = session.load_context(storage)
    if ctx is None:
        with components.page_column():
            components.header(config.APP_NAME_SHORT)
            closed.render_no_session()
        return

    sid = ctx["session_id"]
    state = {"cart": session.cart_load(storage, sid), "tab": "menu", "cat": None, "snap": None, "sig": None,
             "timer": None}

    @ui.refreshable
    def body() -> None:
        snap = state["snap"]
        with components.page_column():
            if snap is None:
                components.header(config.APP_NAME_SHORT)
                closed.render_no_session()
                return
            components.header(snap["table"]["name"], snap["session"]["status"])
            view = snap["view"]
            if view == session.VIEW_WAITING:
                waiting.render(ctx, snap, on_change)
            elif view == session.VIEW_ORDER:
                order.render(snap, ctx, state, on_change)
            elif view == session.VIEW_BILL:
                bill.render(snap)
            elif view == session.VIEW_CLOSED:
                closed.render_paid(snap)
            else:
                closed.render_cancelled(snap)

    def tick(force: bool = False) -> None:
        snap = session.get_snapshot(sid)
        notice.show_unread(snap)
        sig = session.signature(snap)
        if force or sig != state["sig"]:
            state["snap"], state["sig"] = snap, sig
            body.refresh()
        if (snap is None or snap["view"] in session.TERMINAL_VIEWS) and state["timer"] is not None:
            state["timer"].deactivate()  # จบรอบแล้ว ไม่ต้องโพลต่อ (สแกนใหม่จะได้หน้าใหม่)

    def on_change() -> None:
        tick(force=True)

    state["snap"] = session.get_snapshot(sid)
    state["sig"] = session.signature(state["snap"])
    body()
    # ข้อความที่ยังไม่อ่านเด้งหลังเบราว์เซอร์เชื่อมต่อแล้ว (กัน toast หายแล้วถูกมาร์กว่าอ่าน)
    ui.timer(0.5, tick, once=True)
    state["timer"] = ui.timer(POLL_SECONDS, tick)


# ---------------------------------------------------------------- ลงทะเบียน/สตาร์ท

def register_pages() -> None:
    """ลงทะเบียนเส้นทางทั้งหมด (เรียกซ้ำได้ ไม่ลงซ้ำ)"""
    global _registered
    if _registered:
        return
    if config.LOGO_PATH.exists():
        app.add_static_file(local_file=config.LOGO_PATH, url_path=components.LOGO_URL)
    config.FONTS_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    config.MENU_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    if hasattr(app, "add_static_files"):
        app.add_static_files("/fonts", str(config.FONTS_DIR))
        app.add_static_files("/uploads", str(config.UPLOADS_DIR))
    ui.page("/")(_root_page)
    ui.page("/t/{table_no}")(enter.build)
    ui.page("/s")(_customer_page)
    _registered = True


def run(host: str | None = None, port: int | None = None) -> None:
    """เปิดเซิร์ฟเวอร์เว็บลูกค้า (บล็อกจนปิดโปรแกรม) ; ต้องมีฐานข้อมูลที่ seed แล้ว (python -m database.seed)"""
    register_pages()
    ui.run(host=host or config.WEB_HOST, port=port or config.WEB_PORT, title=config.APP_NAME,
           favicon=str(config.LOGO_PATH) if config.LOGO_PATH.exists() else None,
           storage_secret=get_storage_secret(), reload=False, show=False, language="th")


def start_in_thread(host: str | None = None, port: int | None = None) -> threading.Thread:
    """เปิดเซิร์ฟเวอร์ใน thread แยก (daemon — ปิดพร้อมแอปหลัก) -> thread"""
    t = threading.Thread(target=run, args=(host, port), name="web-server", daemon=True)
    t.start()
    return t
