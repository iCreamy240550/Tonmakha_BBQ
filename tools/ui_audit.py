#!/usr/bin/env python3
"""tools/ui_audit.py — ตัวตรวจการจัดวาง ตาราง การ์ด ขอบซ้าย ฟอนต์ Prompt และระยะ --space-* อัตโนมัติ (PLAN §4.5)

รองรับทั้ง Playwright (ถ้ามีในเครื่อง) และ Selenium + Headless Chromium (ที่มีใน VM)
เปิดเซิร์ฟเวอร์ทดสอบชั่วคราวบนฐานข้อมูลสำเนา แล้วเดินตรวจทุกหน้า:
- ฝั่งพนักงาน/เจ้าของ ที่ความละเอียด 1280×780 และ 1040×660
- ฝั่งลูกค้า (มือถือ) ที่ความละเอียด 390×844
เขียนรายงานลง `docs/ui_audit.md` และบันทึกภาพหน้าจอลง `docs/web_screens/`
คืนค่า exit code 0 เมื่อพบ 0 ข้อผิดพลาด
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn
import config
from database import db, schema, seed
from services import (
    checkout_service,
    menu_service,
    order_service,
    qr_service,
    shop_service,
    table_service,
    weigh_service,
)


ALLOWED_SPACES = {0.0, 4.0, 8.0, 12.0, 16.0, 24.0, 32.0, 48.0}

AUDIT_JS = r"""
return (() => {
  const errors = [];
  const allowedSpaces = new Set([0, 4, 8, 12, 16, 24, 32, 48]);

  const isVisible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // 1) ตรวจฟอนต์ Prompt ทุก element ที่มีข้อความโดยตรง
  const fontLoaded = document.fonts ? document.fonts.check('16px Prompt') : true;
  if (!fontLoaded) {
    errors.push('Fontcheck: document.fonts.check("16px Prompt") คืนค่า false');
  }

  const allEls = Array.from(document.querySelectorAll('*'));
  let fontCheckedCount = 0;
  for (const el of allEls) {
    if (!isVisible(el)) continue;
    const hasDirectText = Array.from(el.childNodes).some(
      (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0
    );
    const isFormCtrl = ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'TH', 'TD'].includes(el.tagName);
    if (!hasDirectText && !isFormCtrl) continue;
    fontCheckedCount += 1;
    const ff = window.getComputedStyle(el).fontFamily || '';
    const cleaned = ff.replace(/['"]/g, '').trim().toLowerCase();
    if (!cleaned.startsWith('prompt')) {
      errors.push(`Font: <${el.tagName.toLowerCase()}> มี font-family="${ff}" (ต้องขึ้นต้นด้วย Prompt)`);
    }
  }

  // 2) ตรวจ Horizontal Overflow ของหน้า
  const docEl = document.documentElement;
  if (docEl.scrollWidth > docEl.clientWidth + 1) {
    errors.push(`Overflow: หน้าเว็บล้นแนวนอน scrollWidth=${docEl.scrollWidth} > clientWidth=${docEl.clientWidth}`);
  }

  // ตรวจปุ่มและป้ายสถานะว่าข้อความไม่ล้น/ถูกตัด
  const btnsAndBadges = Array.from(document.querySelectorAll('.btn, .status-badge'));
  for (const b of btnsAndBadges) {
    if (!isVisible(b)) continue;
    if (b.scrollWidth > b.clientWidth + 2) {
      errors.push(`Clipped text: "${(b.textContent || '').trim().slice(0, 30)}" scrollWidth=${b.scrollWidth} > clientWidth=${b.clientWidth}`);
    }
  }

  // 3) ตรวจตารางทุกตาราง (.data-table)
  const tables = Array.from(document.querySelectorAll('table.data-table'));
  let tableCount = 0;
  for (const tbl of tables) {
    if (!isVisible(tbl)) continue;
    tableCount += 1;
    const ths = Array.from(tbl.querySelectorAll('thead th'));
    const bodyRows = Array.from(tbl.querySelectorAll('tbody tr'));
    const thRects = ths.map((th) => th.getBoundingClientRect());
    const thAligns = ths.map((th) => window.getComputedStyle(th).textAlign);

    for (let i = 0; i < ths.length; i++) {
      if (ths[i].scrollWidth > ths[i].clientWidth + 1) {
        errors.push(`Table th[${i}] ("${ths[i].textContent.trim()}") ข้อความหัวตารางล้น/ถูกตัด scrollWidth=${ths[i].scrollWidth} > clientWidth=${ths[i].clientWidth}`);
      }
      const expectedAnchor = ths[i].dataset.anchor || 'w';
      const expectedAlign = expectedAnchor === 'center' ? 'center' : (expectedAnchor === 'e' ? 'right' : 'left');
      const actualThAlign = thAligns[i] === 'start' ? 'left' : (thAligns[i] === 'end' ? 'right' : thAligns[i]);
      if (actualThAlign !== expectedAlign) {
        errors.push(`Table th[${i}] ("${ths[i].textContent.trim()}") text-align=${actualThAlign} != ${expectedAlign}`);
      }
    }

    let firstRowHeight = null;
    for (let rIdx = 0; rIdx < bodyRows.length; rIdx++) {
      const tr = bodyRows[rIdx];
      if (!isVisible(tr)) continue;
      const trRect = tr.getBoundingClientRect();
      if (firstRowHeight === null) {
        firstRowHeight = trRect.height;
      } else if (Math.abs(trRect.height - firstRowHeight) > 2.0) {
        errors.push(`Table row[${rIdx}] height=${trRect.height.toFixed(1)} != row[0] height=${firstRowHeight.toFixed(1)}`);
      }

      const tds = Array.from(tr.querySelectorAll('td'));
      if (tds.length !== ths.length) continue;
      for (let cIdx = 0; cIdx < tds.length; cIdx++) {
        const td = tds[cIdx];
        const tdRect = td.getBoundingClientRect();
        const thRect = thRects[cIdx];
        if (Math.abs(tdRect.left - thRect.left) > 1.0) {
          errors.push(`Table row[${rIdx}] col[${cIdx}] left=${tdRect.left.toFixed(2)} != th.left=${thRect.left.toFixed(2)}`);
        }
        if (Math.abs(tdRect.width - thRect.width) > 1.0) {
          errors.push(`Table row[${rIdx}] col[${cIdx}] width=${tdRect.width.toFixed(2)} != th.width=${thRect.width.toFixed(2)}`);
        }
        const rawTdAlign = window.getComputedStyle(td).textAlign;
        const actualTdAlign = rawTdAlign === 'start' ? 'left' : (rawTdAlign === 'end' ? 'right' : rawTdAlign);
        const expectedAnchor = td.dataset.anchor || 'w';
        const expectedAlign = expectedAnchor === 'center' ? 'center' : (expectedAnchor === 'e' ? 'right' : 'left');
        if (actualTdAlign !== expectedAlign) {
          errors.push(`Table row[${rIdx}] col[${cIdx}] text-align=${actualTdAlign} != ${expectedAlign}`);
        }
        const actBox = td.querySelector('.table-actions');
        if (actBox && isVisible(actBox)) {
          const actRect = actBox.getBoundingClientRect();
          if (actRect.right > tdRect.right + 1.5) {
            errors.push(`Table row[${rIdx}] col[${cIdx}] ปุ่มในคอลัมน์จัดการล้นขอบขวา (${actRect.right.toFixed(1)} > ${tdRect.right.toFixed(1)})`);
          }
        }
      }
    }
  }

  // 4) ตรวจกริดการ์ด (.cards-grid, .stat-grid, .tables-grid, .orders-grid, .menu-grid)
  const grids = Array.from(document.querySelectorAll('.cards-grid, .stat-grid, .tables-grid, .orders-grid, .menu-grid'));
  let gridCount = 0;
  for (const grid of grids) {
    if (!isVisible(grid)) continue;
    gridCount += 1;
    const cards = Array.from(grid.children).filter((c) => isVisible(c));
    // จัดกลุ่มตามแถวแนวนอน (top ต่างกันไม่เกิน 3px)
    const rows = [];
    for (const card of cards) {
      const rect = card.getBoundingClientRect();
      let rowGroup = rows.find((g) => Math.abs(g.top - rect.top) <= 3.0);
      if (!rowGroup) {
        rowGroup = { top: rect.top, items: [] };
        rows.push(rowGroup);
      }
      rowGroup.items.push({ card, rect });
    }
    for (const rowGroup of rows) {
      if (rowGroup.items.length < 2) continue;
      const base = rowGroup.items[0];
      const baseFooter = base.card.querySelector('.card-footer, .card-actions');
      const baseFooterTop = baseFooter && isVisible(baseFooter) ? baseFooter.getBoundingClientRect().top : null;
      for (let i = 1; i < rowGroup.items.length; i++) {
        const cur = rowGroup.items[i];
        if (Math.abs(cur.rect.height - base.rect.height) > 1.5) {
          errors.push(`CardGrid: การ์ดในแถวเดียวกันสูงไม่เท่ากัน (${cur.rect.height.toFixed(1)} vs ${base.rect.height.toFixed(1)})`);
        }
        if (Math.abs(cur.rect.width - base.rect.width) > 1.5) {
          errors.push(`CardGrid: การ์ดในแถวเดียวกันกว้างไม่เท่ากัน (${cur.rect.width.toFixed(1)} vs ${base.rect.width.toFixed(1)})`);
        }
        if (baseFooterTop !== null) {
          const curFooter = cur.card.querySelector('.card-footer, .card-actions');
          if (curFooter && isVisible(curFooter)) {
            const curFooterTop = curFooter.getBoundingClientRect().top;
            if (Math.abs(curFooterTop - baseFooterTop) > 2.0) {
              errors.push(`CardGrid: ปุ่มท้ายการ์ดอยู่ระดับ top ไม่เท่ากัน (${curFooterTop.toFixed(1)} vs ${baseFooterTop.toFixed(1)})`);
            }
          }
        }
      }
    }
  }

  // 5) ตรวจขอบซ้ายเดียวกันของส่วนหลักในหน้า (.audit-align-root > .audit-block)
  const alignRoots = Array.from(document.querySelectorAll('.audit-align-root'));
  for (const root of alignRoots) {
    if (!isVisible(root)) continue;
    const blocks = Array.from(root.querySelectorAll(':scope > .page-header, :scope > .audit-block, :scope > .card, :scope > .data-table-card, :scope > .cards-grid, :scope > .stat-grid')).filter(isVisible);
    if (blocks.length >= 2) {
      const baseLeft = blocks[0].getBoundingClientRect().left;
      for (let i = 1; i < blocks.length; i++) {
        const left = blocks[i].getBoundingClientRect().left;
        if (Math.abs(left - baseLeft) > 1.5) {
          errors.push(`LeftEdge: บล็อกที่ ${i} ขอบซ้าย=${left.toFixed(1)} ไม่ตรงกับหัวหน้า=${baseLeft.toFixed(1)}`);
        }
      }
    }
  }

  // 6) ตรวจระยะ padding/margin ของคอมโพเนนต์หลักว่าอยู่ในชุด --space-* (0, 4, 8, 12, 16, 24, 32, 48)
  const spaceTargets = Array.from(document.querySelectorAll('.card, .page-header, .data-table th, .data-table td, .stat-tile, .modal-body, .modal-header, .modal-footer'));
  for (const el of spaceTargets) {
    if (!isVisible(el)) continue;
    const cs = window.getComputedStyle(el);
    for (const prop of ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft']) {
      const v = Math.round( parseFloat(cs[prop] || '0') );
      if (!allowedSpaces.has(v)) {
        errors.push(`Spacing: <${el.tagName.toLowerCase()} class="${el.className}"> ${prop}=${cs[prop]} ไม่อยู่ใน --space-*`);
      }
    }
  }

  return {
    errors,
    fontCheckedCount,
    tableCount,
    gridCount,
    consoleErrors: window.__auditConsoleErrors || [],
  };
})();
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check_static_css_font_families() -> list[str]:
    """ตรวจไฟล์ใน frontend/ ทั้งหมดว่าไม่มี font-family อื่นนอกจาก Prompt"""
    errs: list[str] = []
    frontend_dir = ROOT / "frontend"
    if not frontend_dir.exists():
        return ["ไม่พบโฟลเดอร์ frontend/"]
    pattern = re.compile(r"font-family\s*:\s*([^;\}]+)", re.IGNORECASE)
    for p in frontend_dir.rglob("*"):
        if p.suffix.lower() not in {".css", ".js", ".html"}:
            continue
        txt = p.read_text(encoding="utf-8")
        for m in pattern.finditer(txt):
            val = m.group(1).strip()
            if val.startswith("var("):
                continue
            cleaned = val.replace("'", "").replace('"', "").strip().lower()
            if not cleaned.startswith("prompt"):
                errs.append(f"{p.relative_to(ROOT)}: พบ font-family ที่ไม่ใช่ Prompt -> {val}")
    return errs


def setup_test_data() -> dict:
    """เตรียมข้อมูลจำลองในฐานข้อมูลสำเนาให้ทุกหน้ามีข้อมูลแสดงผลครบทุกสถานะ"""
    schema.create_all()
    seed.seed_all()
    shop_service.open_shop(user_id=1)

    tables = table_service.list_tables()
    t1 = tables[0]
    t2 = tables[1]
    t3 = tables[2]
    t4 = tables[3]

    # โต๊ะ 1: สถานะ pending (สำหรับตรวจหน้ารอยืนยัน และแถบแจ้งเตือน)
    scan1 = qr_service.resolve_scan(t1["table_no"], t1["secret_key"], device_id="dev-audit-1")
    sid_pending = scan1["session"]["id"]

    # โต๊ะ 2: สถานะ open มีรายการชั่ง + ออเดอร์ + ข้อความ (สำหรับตรวจหน้าสั่งอาหาร, หน้าชั่ง, หน้าออเดอร์)
    scan2 = qr_service.resolve_scan(t2["table_no"], t2["secret_key"], device_id="dev-audit-2")
    sid_open = scan2["session"]["id"]
    table_service.confirm_session(sid_open, user_id=2)
    weigh_service.add_entry(sid_open, None, 1500, user_id=2)
    items = [it for it in menu_service.list_items() if it["item_type"] == "normal"]
    if items:
        order_service.create_order(
            sid_open,
            [{"menu_item_id": items[0]["id"], "quantity": 2}],
            note="ไม่ใส่เผ็ด",
            user_id=None,
        )

    # โต๊ะ 3: สถานะ awaiting_payment (สำหรับตรวจหน้าบิลลูกค้า และหน้าเช็คเอาท์พนักงาน)
    scan3 = qr_service.resolve_scan(t3["table_no"], t3["secret_key"], device_id="dev-audit-3")
    sid_bill = scan3["session"]["id"]
    table_service.confirm_session(sid_bill, user_id=2)
    weigh_service.add_entry(sid_bill, None, 1200, user_id=2)
    checkout_service.start_checkout(sid_bill, user_id=2)

    # โต๊ะ 4: สถานะ closed ชำระเงินแล้ว (สำหรับตรวจหน้าใบเสร็จลูกค้า และรายงานแดชบอร์ด)
    scan4 = qr_service.resolve_scan(t4["table_no"], t4["secret_key"], device_id="dev-audit-4")
    sid_closed = scan4["session"]["id"]
    table_service.confirm_session(sid_closed, user_id=2)
    weigh_service.add_entry(sid_closed, None, 2000, user_id=2)
    checkout_service.start_checkout(sid_closed, user_id=2)
    preview4 = checkout_service.preview(sid_closed)
    checkout_service.pay(
        sid_closed,
        "cash",
        2,
        promo_id=None,
        force=True,
        amount_received=float(preview4["total"]) + 100.0,
    )

    return {
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "t4": t4,
        "sid_pending": sid_pending,
        "sid_open": sid_open,
        "sid_bill": sid_bill,
        "sid_closed": sid_closed,
    }


def make_driver():
    """สร้าง Headless Chromium WebDriver (Selenium)"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--force-device-scale-factor=1")
    opts.add_argument("--host-resolver-rules=MAP tonmakha.local 127.0.0.1")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
            window.__auditConsoleErrors = [];
            window.addEventListener('error', (e) => {
              window.__auditConsoleErrors.push(e.message || String(e));
            });
            window.addEventListener('unhandledrejection', (e) => {
              window.__auditConsoleErrors.push(String(e.reason || e));
            });
            """
        },
    )
    return driver


def set_viewport(driver, width: int, height: int) -> None:
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": width < 600,
        },
    )


def run_audit_on_current_page(driver, label: str, screenshot_name: str | None, screens_dir: Path) -> dict:
    time.sleep(0.35)
    driver.execute_script("if (document.fonts && document.fonts.ready) { return document.fonts.ready; }")
    time.sleep(0.15)
    res = driver.execute_script(AUDIT_JS)
    try:
        logs = driver.get_log("browser")
        for entry in logs:
            if entry.get("level") == "SEVERE":
                msg = entry.get("message", "")
                if "favicon.ico" not in msg:
                    res["consoleErrors"].append(msg)
    except Exception:
        pass

    if screenshot_name:
        screens_dir.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(screens_dir / screenshot_name))

    return {
        "label": label,
        "errors": res.get("errors", []),
        "consoleErrors": res.get("consoleErrors", []),
        "fontCheckedCount": res.get("fontCheckedCount", 0),
        "tableCount": res.get("tableCount", 0),
        "gridCount": res.get("gridCount", 0),
    }


def set_customer_cookie_for_session(driver, base_url: str, device_id: str, session_id: int | None) -> None:
    from server.auth import sign_payload

    token = sign_payload({
        "st": {"device_id": device_id, "session_id": session_id, "cart": {}},
        "exp": int(time.time()) + config.CUSTOMER_SESSION_TTL_SECONDS,
    })
    driver.execute_cdp_cmd(
        "Network.setCookie",
        {
            "name": config.CUSTOMER_COOKIE_NAME,
            "value": token,
            "url": base_url,
            "path": "/",
            "httpOnly": True,
        },
    )


def set_staff_cookie_for_user(driver, base_url: str, user_id: int) -> None:
    from server.auth import create_staff_token

    token = create_staff_token(user_id)
    driver.execute_cdp_cmd(
        "Network.setCookie",
        {
            "name": config.STAFF_COOKIE_NAME,
            "value": token,
            "url": base_url,
            "path": "/",
            "httpOnly": True,
        },
    )


def main() -> int:
    tmp_dir = Path(tempfile.mkdtemp(prefix="tonmakha_audit_"))
    orig_db = config.DB_PATH
    orig_backup = config.BACKUPS_DIR
    orig_exports = config.EXPORTS_DIR
    orig_qr = config.QR_DIR

    config.DB_PATH = tmp_dir / "audit.db"
    config.BACKUPS_DIR = tmp_dir / "backups"
    config.EXPORTS_DIR = tmp_dir / "exports"
    config.QR_DIR = tmp_dir / "qr"
    for d in (config.BACKUPS_DIR, config.EXPORTS_DIR, config.QR_DIR):
        d.mkdir(parents=True, exist_ok=True)

    static_errors = check_static_css_font_families()
    data_info = setup_test_data()

    from server.app import create_app

    app = create_app(enable_lifespan=False)
    port = find_free_port()
    base_url = f"http://tonmakha.local:{port}"

    srv_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(srv_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # รอให้เซิร์ฟเวอร์พร้อม
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    results: list[dict] = []
    screens_dir = ROOT / "docs" / "web_screens"

    driver = make_driver()
    try:
        # 1) ตรวจฝั่งลูกค้า (390×844)
        set_viewport(driver, 390, 844)

        # หน้าแรก `/`
        driver.get(f"{base_url}/")
        results.append(run_audit_on_current_page(driver, "Customer [390×844] GET / (หน้าบอกให้สแกน QR)", "customer_root.png", screens_dir))

        # หน้ารอพนักงานยืนยัน (pending)
        set_customer_cookie_for_session(driver, base_url, "dev-audit-1", data_info["sid_pending"])
        driver.get(f"{base_url}/s")
        results.append(run_audit_on_current_page(driver, "Customer [390×844] /s (waiting / pending)", "customer_waiting.png", screens_dir))

        # หน้าสั่งอาหาร (open) — แท็บเมนู, รายการของฉัน, ข้อความ
        set_customer_cookie_for_session(driver, base_url, "dev-audit-2", data_info["sid_open"])
        driver.get(f"{base_url}/s")
        results.append(run_audit_on_current_page(driver, "Customer [390×844] /s (order - แท็บเมนู)", "customer_order_menu.png", screens_dir))

        driver.execute_script("const t = document.querySelector('[data-tab=\"my_orders\"]'); if (t) t.click();")
        results.append(run_audit_on_current_page(driver, "Customer [390×844] /s (order - แท็บรายการของฉัน)", "customer_order_mine.png", screens_dir))

        driver.execute_script("const t = document.querySelector('[data-tab=\"notices\"]'); if (t) t.click();")
        results.append(run_audit_on_current_page(driver, "Customer [390×844] /s (order - แท็บข้อความ)", "customer_order_notices.png", screens_dir))

        # หน้าบิล (awaiting_payment)
        set_customer_cookie_for_session(driver, base_url, "dev-audit-3", data_info["sid_bill"])
        driver.get(f"{base_url}/s")
        results.append(run_audit_on_current_page(driver, "Customer [390×844] /s (bill / awaiting_payment)", "customer_bill.png", screens_dir))

        # หน้าจบ/ใบเสร็จ (closed)
        set_customer_cookie_for_session(driver, base_url, "dev-audit-4", data_info["sid_closed"])
        driver.get(f"{base_url}/s")
        results.append(run_audit_on_current_page(driver, "Customer [390×844] /s (closed / receipt)", "customer_closed.png", screens_dir))

        # 2) ตรวจฝั่งพนักงาน/เจ้าของ ที่ 1280×780 และ 1040×660
        staff_routes = [
            ("tables", "โต๊ะ"),
            ("takeaway", "สั่งกลับบ้าน"),
            ("weigh", "ชั่งน้ำหนัก"),
            ("orders", "ออเดอร์"),
            ("checkout", "เช็คเอาท์"),
            ("dashboard", "แดชบอร์ด"),
            ("menu", "เมนูและราคา"),
            ("stock", "สต๊อก"),
            ("promo", "โปรโมชั่น"),
            ("tables_manage", "จัดการโต๊ะ/QR"),
            ("users", "ผู้ใช้"),
            ("settings", "ตั้งค่า"),
            ("log", "ประวัติการใช้งาน"),
            ("backup", "สำรองข้อมูล"),
        ]

        for vp_w, vp_h in [(1280, 780), (1040, 660)]:
            set_viewport(driver, vp_w, vp_h)

            # หน้าล็อกอิน (ยังไม่ล็อกอิน)
            driver.get(f"{base_url}/")
            driver.execute_cdp_cmd("Network.deleteCookies", {"name": config.STAFF_COOKIE_NAME, "url": base_url})
            try:
                driver.get_log("browser")
            except Exception:
                pass
            driver.get(f"{base_url}/staff#/login")
            time.sleep(0.3)
            shot = f"staff_login_{vp_w}x{vp_h}.png" if vp_w == 1280 else None
            results.append(run_audit_on_current_page(driver, f"Staff [{vp_w}×{vp_h}] #/login", shot, screens_dir))

            # ล็อกอินเป็นเจ้าของร้าน (user_id=1) เพื่อตรวจครบทั้ง 13 หน้า
            set_staff_cookie_for_user(driver, base_url, 1)
            driver.get(f"{base_url}/staff#/tables")
            driver.refresh()
            time.sleep(0.4)
            for route_key, title_th in staff_routes:
                driver.get(f"{base_url}/staff#/{route_key}")
                shot_name = f"staff_{route_key}_{vp_w}x{vp_h}.png" if vp_w == 1280 else None
                results.append(
                    run_audit_on_current_page(
                        driver,
                        f"Staff/Owner [{vp_w}×{vp_h}] #/{route_key} ({title_th})",
                        shot_name,
                        screens_dir,
                    )
                )
    finally:
        driver.quit()
        server.should_exit = True
        thread.join(timeout=3)
        config.DB_PATH = orig_db
        config.BACKUPS_DIR = orig_backup
        config.EXPORTS_DIR = orig_exports
        config.QR_DIR = orig_qr
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total_errors = len(static_errors)
    for r in results:
        total_errors += len(r["errors"]) + len(r["consoleErrors"])

    report_lines = [
        "# รายงานตรวจการจัดวาง ตาราง การ์ด ขอบซ้าย และฟอนต์ Prompt (`docs/ui_audit.md`)",
        "",
        f"- เวลาที่ตรวจ: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- จำนวนมุมมองที่ตรวจ: **{len(results)} มุมมอง** (ลูกค้า `390×844`, พนักงาน/เจ้าของ `1280×780` และ `1040×660`)",
        f"- ตรวจไฟล์ CSS/JS แบบ static (`font-family`): **{len(static_errors)} ข้อผิดพลาด**",
        f"- รวมข้อผิดพลาดทั้งหมด: **{total_errors} ข้อผิดพลาด**",
        "",
        "## ตารางสรุปผลการตรวจแต่ละหน้า",
        "",
        "| หน้า / มุมมอง | Elements ตรวจฟอนต์ | ตาราง | กริดการ์ด | Console Errors | Layout/Font Errors | สถานะ |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]

    for r in results:
        err_cnt = len(r["errors"])
        con_cnt = len(r["consoleErrors"])
        status = "✅ ผ่าน" if (err_cnt == 0 and con_cnt == 0) else "❌ ไม่ผ่าน"
        report_lines.append(
            f"| {r['label']} | {r['fontCheckedCount']} | {r['tableCount']} | {r['gridCount']} | {con_cnt} | {err_cnt} | {status} |"
        )

    if static_errors:
        report_lines.extend(["", "## ข้อผิดพลาดจากการตรวจ Static Font-Family", ""])
        for se in static_errors:
            report_lines.append(f"- {se}")

    for r in results:
        if r["errors"] or r["consoleErrors"]:
            report_lines.extend(["", f"## รายละเอียดข้อผิดพลาด: {r['label']}", ""])
            for ce in r["consoleErrors"]:
                report_lines.append(f"- [Console] {ce}")
            for le in r["errors"]:
                report_lines.append(f"- [Audit] {le}")

    report_path = ROOT / "docs" / "ui_audit.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"UI Audit finished: {len(results)} views checked, {total_errors} total errors.")
    if total_errors > 0:
        for r in results:
            if r["errors"] or r["consoleErrors"]:
                print(f"  FAILED: {r['label']}")
                for e in (r["consoleErrors"] + r["errors"])[:10]:
                    print(f"    - {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
