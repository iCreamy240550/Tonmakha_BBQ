# PROGRESS.md — งานย้าย UI ต้นมะค่า เป็น HTML/CSS/JS (หลังบ้าน Python + SQLite)

> **อ่านคู่กับ `PLAN.md`** (แผนและกติกาทั้งหมดอยู่ที่นั่น) — ไฟล์นี้คือ "ความจำ" ของงาน: ติ๊กทันทีที่เสร็จจริง (เขียนครบ + รันได้ + ทดสอบแล้ว)
> เปลี่ยน `PROGRESS.md` เดิมเป็น `LEGACY_PROGRESS.md` ก่อนเริ่ม (ใช้อ้างอิงฟังก์ชัน services ได้ เพราะ services ไม่เปลี่ยน)
> ถ้าเซสชันขาด เริ่มใหม่จาก "จุดที่ทำถึง" — ไม่ต้องทำซ้ำข้อที่ติ๊กแล้ว

## จุดที่ทำถึง
- เฟสปัจจุบัน: **ครบทุกเฟสสมบูรณ์ (เฟส 0 → เฟส 1 → เฟส 2 → เฟส 3 ส่งมอบ)**
- ข้อถัดไป: **เสร็จครบทุกข้อ (P0-1 ถึง P3-10)**
- ฟอนต์ที่ได้รับแล้ว: **ครบทุกน้ำหนัก (18 ไฟล์ TTF: Thin 100, ExtraLight 200, Light 300, Regular 400, Medium 500, SemiBold 600, Bold 700, ExtraBold 800, Black 900 ทั้ง Normal และ Italic + OFL.txt)**
- อัปเดตล่าสุด: 2026-10-25 05:03:00 (+07:00)

## ผลเทสต์ล่าสุด
| รายการ | ฐานก่อนเริ่ม (เฟส 0) | ล่าสุด (จบเฟส 3 ส่งมอบ) |
|---|---|---|
| เทสต์เดิม `tests/test_all_features.py` | **ผ่าน 10 / 10 ข้อ** | **ผ่าน 10 / 10 ข้อ** (ไม่แก้เทสต์เดิมแม้แต่บรรทัดเดียว) |
| เทสต์ API + ความปลอดภัยใหม่ (`test_api_features.py` + `test_api_security.py`) | - | **ผ่าน 10 / 10 ข้อ** |
| `tools/ui_audit.py` (ตาราง/การ์ด/ขอบซ้าย/ฟอนต์ Prompt/ระยะ `--space-*`) | - | **ผ่าน 35 / 35 มุมมอง (0 ข้อผิดพลาด, 0 Console Errors)** |
| E2E เบราว์เซอร์ (`tests/test_browser_e2e.py`) | - | **ผ่าน 1 / 1 ชุดเต็ม (รวมทั้งระบบ 21 / 21 ข้อ)** |
| `python main.py --check` | - | **ผ่านพร้อมใช้งานครบทุกรายการ** |

---

## เฟส 0 — เตรียมการ
- [x] P0-1 สำรองโปรเจกต์ทั้งก้อน (หรือ git init + commit ฐาน) + สร้าง `.gitignore` (`web_secret.key`, `*.db`, `backups/`, `assets/qr_codes/`, `exports/`, `__pycache__/`)
- [x] P0-2 เปลี่ยน PROGRESS.md เดิม → LEGACY_PROGRESS.md และวางไฟล์นี้แทน
- [x] P0-3 สร้าง venv + ติดตั้ง dependencies เดิม + รันเทสต์เดิม บันทึกตัวเลขฐาน (10/10 ข้อผ่าน)
- [x] P0-4 Inventory ฝั่งพนักงาน/เจ้าของ: อ่านทุกไฟล์ `ui/**` → กรอก "แมปหน้า → service/API" และ "คอลัมน์ตาราง" ด้านล่าง
- [x] P0-5 Inventory ฝั่งลูกค้า: อ่าน `web/server.py`, `web/components.py`, `web/pages/*`, `web/session.py` → กรอกตารางแมป
- [x] P0-6 ตรวจ `main.py` (prepare_environment / start_web / auto_backup) และสิ่งที่ต้องย้ายไป `server/jobs.py`
- [x] P0-7 ตรวจ `tests/test_all_features.py` ว่าพึ่ง `web.session` / `main.prepare_environment` / ฟังก์ชันไหนบ้าง (ห้ามทำให้เทสต์เดิมพัง)
- [x] P0-8 ตรวจ `services/checkout_service.py::_find_thai_fonts` และจุดอื่นที่อ้างอิงฟอนต์ Noto/Tahoma/Leelawadee
- [x] P0-9 ตรวจไฟล์ฟอนต์ใน `assets/fonts/` และไฟล์ที่ผู้ใช้แนบเพิ่ม → จดรายการน้ำหนักที่จะสร้าง `@font-face` (18 ไฟล์ครบ 100–900 normal + italic)
- [x] P0-10 (ถ้าทำได้) แคปภาพอ้างอิงแอปเดิมทุกหน้า → `docs/reference_screens/` _(สภาพแวดล้อม VM ไม่มี X11/xvfb สำหรับแสดงหน้าต่าง CustomTkinter จึงบันทึกในความต่างที่ยอมรับและสร้างจากโค้ดต้นฉบับ 100%)_
- [x] P0-11 ✅ เกณฑ์ผ่านเฟส 0 (ตัวเลขเทสต์ฐานมี, inventory ครบ, ตารางพาริตี้เติมจากโค้ดจริง)

## เฟส 1 — หลังบ้าน (Python API)
- [x] P1-1 `server/app.py` FastAPI + ตัวจัดการ exception (400/401/403/404/500) + หัวความปลอดภัย (CSP, Referrer-Policy) + static (`/fonts`, `/uploads/menu`, `/logo.png`) + **ไม่เสิร์ฟ `assets/qr_codes/`**
- [x] P1-2 `server/auth.py` คุกกี้เซ็น HMAC (พนักงาน/เจ้าของ + ลูกค้า) ใช้ความลับจาก `web_secret.key`; ตรวจ Origin (CSRF); rate limit ล็อกอิน/สแกน
- [x] P1-3 ตัวกันเครื่องสำหรับ `/staff` + `/api/staff|owner/*` (เฉพาะ localhost/`STAFF_ALLOWED_NETS`, ปฏิเสธเมื่อมี X-Forwarded-For/Forwarded)
- [x] P1-4 adapter dict-like ให้ `web/session.py` ใช้กับคุกกี้ลูกค้า (ไม่แก้ API ของ session.py)
- [x] P1-5 routes ลูกค้า: scan (POST) · state (snapshot+signature) · cart check · place_order · cancel_request · mark notices read
- [x] P1-6 routes auth: login/logout/me (log `login`, `login_fail`, `logout`)
- [x] P1-7 routes shop (เปิด/ปิดร้าน + force) + alerts (list/poll เสียง/ไปเช็คแล้ว/ปล่อยไว้/ยกเลิกโต๊ะ/รับทราบ/เตือนซ้ำ)
- [x] P1-8 routes tables (รายการ+สถานะ/ยืนยัน/ยกเลิก) + notices (ส่งข้อความหาลูกค้า)
- [x] P1-9 routes weigh (เพิ่ม/ยกเลิกรายการ/กฎครั้งแรก ≥ 1 กก.) + orders (รายการ/เปลี่ยนสถานะ/สั่งแทนลูกค้า/ยกเลิกรายการ+เหตุผล/ทำเมนูหมด)
- [x] P1-10 routes checkout (เริ่มเช็คบิล/preview/โปรที่ใช้ได้/ชำระ เงินสด-PromptPay/QR พร้อมเพย์/ใบเสร็จ PDF-TXT ดาวน์โหลด+บันทึก exports/)
- [x] P1-11 routes owner: dashboard + report (summary/daily/hourly/top/cancellations/bills) + export CSV + เปิดโฟลเดอร์ exports (เฉพาะเครื่องเดียวกับเซิร์ฟเวอร์)
- [x] P1-12 routes owner: menu (หมวด/รายการ/รูปอัปโหลด/ลบรูป/ทำหมด/ซ่อน/ลบ+impact) + stock (รายการ/เติม/ปรับ/แก้/ลบ+impact/ประวัติ)
- [x] P1-13 routes owner: promo + tables_manage (+QR ภาพ/ดาวน์โหลด/สุ่มรหัสลับใหม่) + users + settings (ตรวจทุกช่องก่อนบันทึก + แสดง IP เครื่อง) + log (กรอง+แบ่งหน้า 100)
- [x] P1-14 routes owner: backup (สร้าง/รายการ/ลบ/กู้คืน + ดาวน์โหลดตรวจชื่อไฟล์)
- [x] P1-15 `server/jobs.py` (ตรวจแจ้งเตือนทุก 30 วิ, สำรองอัตโนมัติตอนเริ่ม, เตรียม DB/seed) + lifespan
- [x] P1-16 `main.py` ใหม่ (`--host --port --no-browser --check`) + `run_web.py` ทางลัด + `config.py` + `requirements.txt` (ตัด customtkinter/nicegui เพิ่ม fastapi/uvicorn/python-multipart) + เตือนรหัสเริ่มต้น
- [x] P1-17 แก้ `_find_thai_fonts` ให้ใช้ Prompt (เอา Noto/Tahoma/Leelawadee ออก) + ทดสอบ PDF ใบเสร็จไทยจริง (เปิดดูภาพ)
- [x] P1-18 เทสต์ API: ทุก endpoint (สำเร็จ + สิทธิ์/ข้อมูลผิด) + flow เต็มลูกค้า↔พนักงาน + แจ้งเตือนกรณี A/B + สต๊อกหมด + ตะกร้าเกินสต๊อก
- [x] P1-19 เทสต์ความปลอดภัย (ข้ามรอบ/ข้ามเครื่อง, ข้ามบทบาท, proxy header, rate limit, Origin, ไม่มี password_hash/secret_key ใน response, ลูกค้าไปไม่ถึง touch_session/check_alerts)
- [x] P1-20 ✅ เกณฑ์ผ่านเฟส 1 (เทสต์เดิม ≥ ฐาน + เทสต์ใหม่ผ่านหมด 20/20 ข้อ) → เขียน "สรุปเฟส 1"

## เฟส 2 — หน้าเว็บ
### 2A ฐานร่วม (`frontend/shared/`)
- [x] P2-1 `fonts.css` (@font-face Prompt ครบน้ำหนักที่ได้รับ, `font-synthesis:none`, preload 400/700) + `tokens.css` (สี/สถานะ/`--space-*`/ขนาดฟอนต์/ปุ่ม sm-md-lg ตามเดิม)
- [x] P2-2 `base.css` (reset, tabular-nums, line-height ไทย ≥ 1.5, กฎฟอนต์ฟอร์ม) + `components.css`
- [x] P2-3 `api.js` (fetch wrapper, จัดการ 401/403, แสดง detail ภาษาไทย) + `format.js` (money/baht/weight_text/fmt_time/fmt_datetime + เทสต์เทียบ Python)
- [x] P2-4 modal/confirm/toast (Esc, โฟกัสวน) + status-badge
- [x] P2-5 **ตารางกลาง** `data-table.js` + `table.css` (table เดียว, colgroup, sticky thead, anchor/header_anchor, แถวสูงเท่ากัน, MAX_ROWS 300)
- [x] P2-6 ปฏิทินเลือกวัน พ.ศ. `date-picker.js` (ค่าที่ส่ง parse_date รับได้)
- [x] P2-7 `tools/ui_audit.py` (Playwright/Selenium Chromium) ตามหัวข้อ 4.5 — ทำให้รันได้ตั้งแต่ตอนนี้
### 2B ฝั่งลูกค้า (มือถือ 390×844) — ต้นฉบับ `web/pages/*`
- [x] P2-8 โครงหน้า `/` และ `/t/{no}` (GET ไม่มีผลข้างเคียง) + enter (POST scan หลังโหลด, ล้าง `?k=`, replace → `/s`)
- [x] P2-9 `/s` ตัวโพล 3 วินาที + signature + วาดใหม่เฉพาะเมื่อเปลี่ยน + header ชื่อโต๊ะ/ป้ายสถานะ
- [x] P2-10 waiting (+ยกเลิกคำขอ มีกล่องยืนยัน)
- [x] P2-11 order: เมนูแยกหมวด + รูป 1:1/placeholder + สต๊อกคงเหลือ + "สินค้าหมด" + เมนูชั่ง "สั่งกับพนักงาน"
- [x] P2-12 order: ตะกร้า (จำกัดตามสต๊อก/99, ข้อความ error ไทย, เอารายการสั่งไม่ได้ออกพร้อมแจ้ง, หมายเหตุ) + ส่งออเดอร์
- [x] P2-13 order: แท็บออเดอร์/รายการชั่ง/ยอดรวม + แท็บข้อความ (notice) + เด้งข้อความยังไม่อ่าน
- [x] P2-14 bill (ดูอย่างเดียว) + closed (ชำระแล้ว/ยกเลิก/ร้านปิด/QR ผิด/ไม่พบรอบ/โต๊ะไม่ว่าง)
### 2C เว็บแอปพนักงาน/เจ้าของ (`frontend/staff/`) — ต้นฉบับ `ui/**`
- [x] P2-15 app shell: sidebar 230px (กลุ่ม/สิทธิ์/ผู้ใช้/ออกจากระบบ+ยืนยัน), topbar 60px, router (`#/key?params`, guard บทบาท, report→dashboard, kitchen เมิน)
- [x] P2-16 shop-control (เปิด/ปิดร้าน + force confirm, รีเฟรช 15 วิ)
- [x] P2-17 alert-center (แถบแดง, สูงสุด 5 + "และอีก N", ปุ่มตามชนิด, เสียง WebAudio + ปลดล็อก/ปุ่มปิดเสียง, รีโหลดหน้าปัจจุบันเมื่อเปลี่ยน)
- [x] P2-18 login (70)
- [x] P2-19 tables (129) — การ์ดเท่ากัน, รีเฟรช 4 วิ
- [x] P2-20 weigh (255)
- [x] P2-21 orders (197) + order-card
- [x] P2-22 checkout (596) — เงินสด/PromptPay/โปร/ใบเสร็จ/พิมพ์/ดาวน์โหลด
- [x] P2-23 dashboard (455) — ภาพรวม + รายงาน 5 แท็บ + ปฏิทิน พ.ศ. + CSV
- [x] P2-24 menu (490) — หมวด + รายการ + อัปโหลดรูป 1:1
- [x] P2-25 stock (294)
- [x] P2-26 promo (174)
- [x] P2-27 tables_manage (266) — QR/ลิงก์/สุ่มรหัส
- [x] P2-28 users (173)
- [x] P2-29 settings (289)
- [x] P2-30 log (172)
- [x] P2-31 backup (134)
### 2D ตรวจรวม
- [x] P2-32 รัน `ui_audit` ทุกหน้า (1280×780, 1040×660, ลูกค้า 390×844) แก้จน 0 ข้อผิดพลาด (ตาราง/การ์ด/ขอบซ้าย/overflow/ฟอนต์ Prompt)
- [x] P2-33 ไม่มี error/warning ใน console ตอนเดินทุกหน้า
- [x] P2-34 ✅ เกณฑ์ผ่านเฟส 2 → เขียน "สรุปเฟส 2"

## เฟส 3 — พาริตี้ ความปลอดภัย ส่งมอบ
- [x] P3-1 E2E เบราว์เซอร์ 2 บทบาทพร้อมกัน (สแกน→ยืนยัน→ชั่ง→สั่ง→เสิร์ฟ→เช็คเอาท์→ชำระ→ใบเสร็จ) + ฝั่งเจ้าของ (ราคา/โปร/สต๊อก/สุ่มรหัส/CSV/สำรอง-กู้คืน) + แจ้งเตือนโต๊ะเงียบ; เก็บภาพ `docs/web_screens/`
- [x] P3-2 ไล่ "ตารางพาริตี้" ครบทุกแถว
- [x] P3-3 matrix สิทธิ์ (ลูกค้า/พนักงาน/เจ้าของ × หน้า × การกระทำ)
- [x] P3-4 ทดสอบเจาะ: เดา session_id, แก้คุกกี้, XSS ทุกจุดที่รับข้อความ, อัปโหลดไฟล์แปลก/`../`, ดาวน์โหลดโดยไม่ล็อกอิน, Origin อื่น, proxy header
- [x] P3-5 ทดสอบมือถือ (iOS Safari / Android Chrome หรือจำลอง) + ขนาดปุ่มสัมผัส ≥ 44px
- [x] P3-6 ตรวจฟอนต์ทั้งระบบ = Prompt (computed style ทุกหน้า + grep `font-family` ใน frontend + PDF ใบเสร็จ)
- [x] P3-7 ทำความสะอาด: `ui/` และ NiceGUI ใน `web/` → `legacy/`; ตรวจไม่มี import customtkinter/tkinter/nicegui ใน flow เว็บ
- [x] P3-8 อัปเดต `README.md` + (ถ้ามี) `.env.example`/ตัวแปร config (ติดตั้ง/รัน/ตั้งค่าครั้งแรก/บัญชีเริ่มต้น/ลิงก์ QR/ข้อจำกัดหน้าพนักงาน/ฟอนต์)
- [x] P3-9 รันเทสต์ทั้งหมดครั้งสุดท้าย + `python main.py --check` ผ่าน
- [x] P3-10 ✅ เกณฑ์ผ่านเฟส 3 = Definition of Done ครบ 7 ข้อใน PLAN.md หัวข้อ 1 → เขียน "สรุปส่งมอบ"

---

## ตารางพาริตี้ฟีเจอร์
> เริ่มจากสรุปใน PLAN.md หัวข้อ 7 แล้ว **เติมให้ละเอียดจากโค้ดจริงในเฟส 0** — ทุกปุ่ม/เงื่อนไข/ข้อความ/กล่องยืนยันที่พบเป็นหนึ่งแถว
> สถานะ: ⬜ ยังไม่ทำ · 🟨 ทำแล้วยังไม่ทดสอบ · ✅ ทดสอบผ่าน · ⚠️ ต่างจากเดิม (ใส่เหตุผล)

| # | ฟีเจอร์ / เงื่อนไข | ไฟล์เดิม | API | หน้าเว็บ | สถานะ | หมายเหตุ |
|---|---|---|---|---|---|---|
| 1 | สแกนผ่านบอตพรีวิว (`GET /t/{no}`) ไม่สร้างรอบ ต้องรอ JS ยิง `POST /api/customer/scan` แล้วล้าง `?k=` ออกจาก URL และ `replace('/s')` | `web/pages/enter.py` | `GET /t/{no}`, `POST /api/customer/scan` | `customer/js/enter.js` | ✅ | ทดสอบผ่านทั้ง API และ E2E เบราว์เซอร์ |
| 2 | สแกน QR ตรวจลำดับ: ร้านปิด (`ร้านปิดอยู่`) → รหัสผิด (`QR ไม่ถูกต้อง`) → โต๊ะไม่ว่าง (`โต๊ะนี้มีลูกค้าใช้งานอยู่แล้ว`) → เครื่องนี้มีโต๊ะอื่นค้างอยู่ (`คุณกำลังใช้งาน <ชื่อโต๊ะ> อยู่` + ปุ่ม `กลับไปที่โต๊ะของฉัน`) → สร้างรอบ `pending` ผูกกับ `device_id` | `web/pages/enter.py`, `web/pages/closed.py`, `services/qr_service.py` | `POST /api/customer/scan` | `customer/js/enter.js`, `customer/js/closed.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 3 | หน้ารอพนักงานยืนยัน (`pending`): แสดง `ส่งคำขอแล้ว กรุณารอพนักงานยืนยัน` + ปุ่ม `ยกเลิกคำขอ` พร้อมกล่องยืนยัน `ยกเลิกคำขอใช้โต๊ะ?` (`ไม่ยกเลิก` / `ยืนยันยกเลิก`) | `web/pages/waiting.py` | `POST /api/customer/cancel` | `customer/js/waiting.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 4 | หน้าสั่งอาหาร (`open`): 3 แท็บ `เมนู`, `รายการของฉัน`, `ข้อความ (N)` + เลือกหมวดเมนู + รูปเมนูสัดส่วน 1:1 (หรือ placeholder ไอคอนอาหารเมื่อไม่มีรูป) | `web/pages/order.py` | `GET /api/customer/state` | `customer/js/order.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 5 | แสดงสต๊อกคงเหลือจริงพร้อมหน่วย (`คงเหลือ 8 ขวด` สีเขียว, `สินค้าหมด · คงเหลือ 0 ขวด` สีแดง + ป้าย `สินค้าหมด` ซ่อนปุ่มเพิ่ม, `พร้อมจำหน่าย` เมื่อไม่ผูกสต๊อก) | `web/pages/order.py`, `services/menu_service.py` | `GET /api/customer/state` | `customer/js/order.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 6 | เมนูชั่งกิโล (`weighed`) ในหน้าลูกค้าแสดง `<ราคา> บาท/กก. · ชั่งกิโล สั่งกับพนักงาน` และป้าย `ชั่งกิโล` ไม่ให้กดใส่ตะกร้า | `web/pages/order.py` | `GET /api/customer/state` | `customer/js/order.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 7 | ลูกค้าเพิ่ม/ลดจำนวนในตะกร้า: จำกัดไม่เกินสต๊อกคงเหลือและสูงสุด 99 ชิ้น, แสดงข้อความเตือนไทย (`<ชื่อ> สั่งได้สูงสุด <N> <หน่วย> ตามสต๊อกคงเหลือ`), เอารายการที่หมด/ไม่มีขายออกอัตโนมัติพร้อมแจ้ง `เอาออกจากตะกร้าแล้ว (สินค้าหมด/ไม่มีขาย): ...` | `web/session.py`, `web/pages/order.py` | `POST /api/customer/cart/change`, `GET /api/customer/state` | `customer/js/order.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 8 | แถบล่างตะกร้า (`ตะกร้า N รายการ · X บาท` หรือ `ตะกร้ายังว่าง`) + ปุ่ม `ตรวจสอบ/สั่งอาหาร` → กล่องยืนยันการสั่งอาหาร + ช่อง `หมายเหตุถึงครัว (ถ้ามี)` + ปุ่ม `กลับไปแก้` / `ยืนยันสั่ง` (ตรวจสต๊อกซ้ำใน transaction; ถ้าไม่พอ rollback ทั้งออเดอร์และคงตะกร้าไว้) | `web/pages/order.py`, `web/session.py` | `POST /api/customer/order` | `customer/js/order.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 9 | แท็บ `รายการของฉัน`: แสดง `หมูกระทะชั่งกิโล` (ชื่อ + น้ำหนัก + เงิน), ออเดอร์แต่ละใบ (`ออเดอร์ #ID · HH:MM` + ป้ายสถานะ `รับออเดอร์แล้ว`/`กำลังทำ`/`เสิร์ฟแล้ว`), หมายเหตุ, และ `ยอดรวมปัจจุบัน` | `web/pages/order.py` | `GET /api/customer/state` | `customer/js/order.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 10 | แท็บ `ข้อความ` & แจ้งเตือนข้อความยังไม่อ่าน (`unread`): เด้ง toast ข้อความที่ยังไม่อ่านแล้วเรียก `mark_notices_read` ทันที, แสดงประวัติข้อความพร้อมเวลา | `web/pages/notice.py` | `POST /api/customer/notices/read` | `customer/js/notice.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 11 | หน้าบิล (`awaiting_payment`): แสดง `พนักงานกำลังเช็คบิลให้ที่โต๊ะ` + การ์ด `รายการที่ต้องชำระ` (รายการชั่ง/สั่ง, รวมก่อนภาษี/ส่วนลด, ส่วนลดโปร, ค่าบริการ, VAT, `ยอดชำระสุทธิ`) ดูอย่างเดียว | `web/pages/bill.py`, `web/components.py` | `GET /api/customer/state` | `customer/js/bill.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 12 | หน้าจบ (`closed` / `cancelled` / ไม่พบรอบ): `ชำระเงินเรียบร้อย` + การ์ด `ใบเสร็จรับเงิน` (แสดงชำระโดย, รับเงินมา, เงินทอนเฉพาะเงินสด, เวลาชำระ); ถ้ายกเลิกแสดง `ยกเลิกคำขอแล้ว` (ลูกค้ายกเลิก) หรือ `คำขอถูกยกเลิก` (พนักงานยกเลิก ไม่โชว์เหตุผลภายใน) | `web/pages/closed.py`, `web/components.py` | `GET /api/customer/state` | `customer/js/closed.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 13 | โพลลูกค้าทุก 3 วินาที (`POLL_SECONDS`): วาดใหม่เฉพาะเมื่อ `signature` เปลี่ยน (ไม่ทำค่าที่กรอก/แท็บหาย), หยุดโพลเมื่อ `view` เป็น `closed`/`cancelled`, และ **ห้ามเรียก `touch_session` หรือ `check_alerts`** | `web/server.py`, `web/session.py` | `GET /api/customer/state` | `customer/js/app.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 14 | ล็อกอินพนักงาน/เจ้าของ: ตรวจชื่อผู้ใช้+รหัสผ่าน (`กรุณากรอกชื่อผู้ใช้และรหัสผ่าน`, `ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง`), บันทึก log `login`/`login_fail`, ออกคุกกี้เซ็น HMAC, หน้าเริ่มต้นตามสิทธิ์ (`owner` → `dashboard`, `staff` → `tables`) | `ui/login_page.py`, `ui/app.py` | `POST /api/staff/login`, `POST /api/staff/logout`, `GET /api/staff/me` | `staff/js/pages/login.js`, `staff/js/app.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 15 | แถบเมนูซ้าย 230px สีถ่านไม้ (`#2b2118`): โลโก้ 64px + `ต้นมะค่า`, กลุ่ม `หน้าร้าน` (โต๊ะ, ชั่งน้ำหนัก, ออเดอร์, เช็คเอาท์) และ `เจ้าของร้าน` (แดชบอร์ด, เมนูและราคา, สต๊อก, โปรโมชั่น, จัดการโต๊ะ/QR, ผู้ใช้, ตั้งค่า, ประวัติการใช้งาน, สำรองข้อมูล — ซ่อนจากพนักงาน), ท้ายแถบแสดงชื่อ+บทบาท+ปุ่ม `ออกจากระบบ` (มีกล่องยืนยัน `ออกจากระบบใช่หรือไม่?`) | `ui/app.py` | `GET /api/staff/me`, `POST /api/staff/logout` | `staff/js/app.js`, `staff/js/router.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 16 | การนำทาง (`navigate`): ไม่มีเมนู `kitchen` (ถ้าเรียก `#/kitchen` ให้เมิน), ถ้าเรียก `#/report` ให้พาไป `#/dashboard` อัตโนมัติ, ถ้าพนักงานเข้าหน้าเจ้าของให้แจ้ง `คุณไม่มีสิทธิ์เข้าหน้านี้` / `หน้านี้สำหรับเจ้าของร้านเท่านั้น` แล้วพากลับ `#/tables` | `ui/app.py`, `ui/owner/_common.py` | `server/deps.py` (`require_owner`) | `staff/js/router.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 17 | ตัวควบคุมเปิด/ปิดร้าน (`ShopControl`) บนแถบบน: ป้าย `ร้านเปิด`/`ร้านปิด` + ปุ่ม `เปิดร้าน`/`ปิดร้าน`, รีเฟรชทุก 15 วิ; ปิดร้านถามยืนยัน `ปิดร้านใช่หรือไม่?`, ถ้ามีโต๊ะค้างถามยืนยันซ้ำ `ต้องการปิดร้านทั้งที่ยังมีโต๊ะค้างหรือไม่?` (`ปิดร้านเลย` → `force=True`) | `ui/staff/shop_control.py`, `ui/app.py` | `GET /api/staff/shop`, `POST /api/staff/shop/open`, `POST /api/staff/shop/close` | `staff/js/shop-control.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 18 | ศูนย์แจ้งเตือนด่วน (`AlertCenter`): แถบแดงใต้แถบบน แสดงสูงสุด 5 รายการ + `และอีก N รายการ`, แยกปุ่มโต๊ะเงียบ (`ไปเช็คแล้ว`, `ปล่อยไว้`, `ยกเลิกโต๊ะ` มีกล่องยืนยัน) กับสต๊อก (`รับทราบแล้ว`, `ปล่อยไว้`), เสียงบี๊บ WebAudio 3 ครั้ง (1200Hz 250ms) เมื่อมีแจ้งเตือนใหม่ + ปุ่มเปิด/ปิดเสียงที่แถบบน, เปลี่ยนแล้วรีโหลดหน้าปัจจุบัน | `ui/alert_center.py`, `services/alert_service.py` | `GET /api/staff/alerts`, `POST /api/staff/alerts/{id}/check`, `POST /api/staff/alerts/{id}/snooze`, `POST /api/staff/alerts/{id}/cancel_table` | `staff/js/alert-center.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 19 | หน้าโต๊ะ (`tables`): กริด 4 คอลัมน์ รีเฟรชทุก 4 วิ, แสดงป้ายสถานะ 4 สีมุมขวาบน, การ์ดโต๊ะแสดงเวลาที่นั่ง+ยอดรวมปัจจุบัน, ปุ่มตามสถานะ: `pending` (`ยืนยัน`, `ยกเลิก` ถามยืนยัน), `open` (`ชั่ง`, `ออเดอร์`, `เช็คบิล`, `ส่งข้อความ`, `ยกเลิกโต๊ะ` ถามเหตุผล), `awaiting_payment` (`ไปชำระเงิน`) | `ui/staff/tables_page.py` | `GET /api/staff/tables`, `POST /api/staff/tables/{sid}/confirm`, `POST /api/staff/tables/{sid}/cancel`, `POST /api/staff/tables/{sid}/notice` | `staff/js/pages/tables.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 20 | หน้าชั่งน้ำหนัก (`weigh`): เลือกโต๊ะ (เฉพาะ `open`), แสดงกรอบอัตราราคา `กิโลกรัมละ 299 บาท`, กรอกน้ำหนัก + เลือกหน่วย (`ขีด`, `กรัม`, `กิโลกรัม`) + ปุ่มลัด `+1 ขีด`, `+2 ขีด`, `+5 ขีด`, `+10 ขีด`, `ล้าง`, คำนวณราคาสด, กฎชั่งครั้งแรกของรอบต้อง ≥ 1,000 กรัม (`การชั่งครั้งแรกของโต๊ะต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม`), ตารางรายการที่ชั่งแล้ว + ปุ่ม `ยกเลิก` (ต้องระบุเหตุผล) | `ui/staff/weigh_page.py`, `services/weigh_service.py` | `GET /api/staff/weigh`, `POST /api/staff/weigh`, `POST /api/staff/weigh/{id}/cancel` | `staff/js/pages/weigh.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 21 | หน้าออเดอร์ (`orders`): กรองโต๊ะ (`ทุกโต๊ะ` / โต๊ะที่ใช้งาน) + กรองสถานะ (`ยังไม่เสิร์ฟ` / `ทั้งหมด`), การ์ดออเดอร์ (`OrderCard`) แสดงทีละปุ่มตามลำดับ: `new` → `เริ่มทำ`, `preparing` → `เสิร์ฟแล้ว`, `served` → ไม่มีปุ่ม (และไม่มีปุ่มยกเลิกบนหน้านี้ตามข้อกำหนด), ปุ่ม `+ สั่งให้ลูกค้า` เปิด modal เลือกโต๊ะ+จำนวนเมนู+หมายเหตุ | `ui/staff/orders_page.py`, `ui/widgets/order_card.py` | `GET /api/staff/orders`, `POST /api/staff/orders/{id}/status`, `POST /api/staff/orders` | `staff/js/pages/orders.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 22 | หน้าเช็คเอาท์ (`checkout`): ซ้ายรายการโต๊ะ `open`/`awaiting_payment`, ขวาแสดงรายการชั่ง+สั่ง+สรุปยอด, โต๊ะ `open` มีปุ่ม `เริ่มเช็คบิล` (ถามยืนยัน), โต๊ะ `awaiting_payment` เลือกโปรโมชั่นที่ใช้ได้ + เลือกวิธีชำระ 2 แบบ (`เงินสด` / `โอน/PromptPay` ไม่มีบัตร), เงินสดคำนวณเงินทอนสดด้วย Decimal และห้ามยืนยันถ้ารับน้อยกว่ายอดสุทธิ, PromptPay แสดง QR EMVCo ระบุยอดอัตโนมัติ + ชื่อ/เลขบัญชี + ป้าย `สถานะ: รอตรวจสอบการโอน` (ไม่มีเงินทอน), ถ้ายืนยันตอนมีออเดอร์ค้างถามยืนยัน `ปิดบิลต่อ` (`force=True`) | `ui/staff/checkout_page.py`, `services/checkout_service.py`, `services/qr_service.py` | `GET /api/staff/checkout`, `POST /api/staff/checkout/{sid}/start`, `POST /api/staff/checkout/{sid}/pay` | `staff/js/pages/checkout.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 23 | กล่องใบเสร็จรับเงิน (`ReceiptDialog`): แสดงกระดาษใบเสร็จจัดย่อหน้าตามแบบใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงินด้วยฟอนต์ Prompt (ชื่อร้าน, เลขผู้เสียภาษีถ้าเปิด, ที่อยู่, โทร, พนักงานขาย, วันที่, เวลา, ตาราง จำนวน/รายการ/จำนวนเงิน, จำนวนรวม, สรุปยอด, ช่องทางชำระ, รับเงินมา/เงินทอนเฉพาะเงินสด, ขอบคุณที่ใช้บริการ) + ปุ่ม `บันทึก PDF (.pdf)`, `บันทึก TXT (.txt)` (บันทึกลง `exports/` และดาวน์โหลดได้) + ปุ่ม `พิมพ์` (`window.print()`) | `ui/staff/checkout_page.py`, `services/checkout_service.py` | `POST /api/staff/checkout/{sid}/export/{fmt}`, `GET /api/staff/checkout/files/{filename}` | `staff/js/pages/checkout.js` | ✅ | ทดสอบผ่านทั้ง API, PDF Prompt และเบราว์เซอร์จริง |
| 24 | หน้าแดชบอร์ดและรายงาน (`dashboard`): ส่วนที่ 1 ภาพรวมวันนี้ (การ์ด 8 ใบ + สต๊อกใกล้หมด + ยอดขายแยกตามช่องทางชำระ + ยกเลิกวันนี้) + ส่วนที่ 2 รายงานตามช่วงวันที่ด้วยตัวเลือกปฏิทิน พ.ศ. (`DatePickerField` ไม่ต้องพิมพ์เอง) + ปุ่มลัด (`วันนี้`, `เมื่อวาน`, `7 วัน`, `เดือนนี้`, `เดือนที่แล้ว`) + การ์ดสรุป 8 ใบ + ตาราง 5 แท็บ (`รายวัน`, `รายชั่วโมง`, `เมนูขายดี`, `รายการยกเลิก`, `บิล`) พร้อมกราฟแท่งสัดส่วน + ปุ่ม `ส่งออก CSV` (บันทึก `exports/` + ดาวน์โหลด) + ปุ่ม `เปิดโฟลเดอร์ exports` | `ui/owner/dashboard_page.py`, `services/report_service.py` | `GET /api/owner/dashboard/overview`, `GET /api/owner/dashboard/report`, `POST /api/owner/report/export_csv`, `POST /api/owner/open_folder` | `staff/js/pages/dashboard.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 25 | หน้าเมนูและราคา (`menu`): ซ้ายหมวดเมนู (`+ หมวด`, `เปลี่ยนชื่อ`, `▲`, `▼`, `ซ่อนหมวดนี้`/`แสดงหมวดนี้อีกครั้ง`), ขวาตารางเมนู + ปุ่ม `▲`, `▼`, `+ เพิ่มเมนู`, แถวละ 4 ปุ่ม (`แก้ไข`, `ทำเป็นหมด`/`มีขาย`, `ซ่อน`/`แสดง`, `ลบ` แสดงผลกระทบ `get_delete_impact`), กล่องเพิ่ม/แก้เมนูรองรับอัปโหลดรูป JPG/PNG/WebP ≤ 5MB ปรับสัดส่วน 1:1 อัตโนมัติ + พรีวิว + ลบรูป | `ui/owner/menu_page.py`, `services/menu_service.py` | `GET /api/owner/menu`, `POST /api/owner/menu/categories`, `PATCH /api/owner/menu/categories/{id}`, `POST /api/owner/menu/items`, `PATCH /api/owner/menu/items/{id}`, `POST /api/owner/menu/items/{id}/image`, `DELETE /api/owner/menu/items/{id}/image`, `POST /api/owner/menu/items/{id}/sold_out`, `GET /api/owner/menu/items/{id}/delete_impact`, `DELETE /api/owner/menu/items/{id}` | `staff/js/pages/menu.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 26 | หน้าสต๊อก (`stock`): ซ้ายตารางสต๊อก + ตัวเลือก `แสดงรายการที่ปิดใช้` + ปุ่ม `ลบรายการสต๊อกที่เลือก` + `+ เพิ่มรายการ`, แถวละ 4 ปุ่ม (`เติม`, `ปรับ +/-` บังคับเหตุผล, `แก้ไข`, `ลบ` แสดงผลกระทบ `get_delete_impact`), ขวาตาราง `ประวัติการเคลื่อนไหว` ของรายการที่เลือก | `ui/owner/stock_page.py`, `services/stock_service.py` | `GET /api/owner/stock`, `POST /api/owner/stock`, `PATCH /api/owner/stock/{id}`, `POST /api/owner/stock/{id}/restock`, `POST /api/owner/stock/{id}/adjust`, `GET /api/owner/stock/{id}/movements`, `GET /api/owner/stock/{id}/delete_impact`, `DELETE /api/owner/stock/{id}` | `staff/js/pages/stock.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 27 | หน้าโปรโมชั่น (`promo`): ตารางโปรโมชั่น + ปุ่ม `+ เพิ่มโปรโมชั่น`, แถวละ 2 ปุ่ม (`แก้ไข`, `ปิดใช้`/`เปิดใช้`), กล่องเพิ่ม/แก้โปรเลือกชนิด `ลดเป็น %` (1-100) หรือ `ลดเป็นบาท`, ยอดขั้นต่ำ, วันเริ่ม-วันสิ้นสุด | `ui/owner/promo_page.py`, `services/promo_service.py` | `GET /api/owner/promos`, `POST /api/owner/promos`, `PATCH /api/owner/promos/{id}`, `POST /api/owner/promos/{id}/toggle` | `staff/js/pages/promo.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 28 | หน้าจัดการโต๊ะและ QR (`tables_manage`): ซ้ายตารางโต๊ะ + ปุ่ม `เปิดโฟลเดอร์ QR`, `สร้าง QR ทุกโต๊ะ`, `+ เพิ่มโต๊ะ`, แถวละ 3 ปุ่ม (`ชื่อ`, `สุ่มรหัสใหม่` มีคำเตือน QR เดิมใช้ไม่ได้, `ปิดใช้`/`เปิดใช้`), ขวาแสดงตัวอย่างรูป QR + ลิงก์เต็ม + คำเตือนถ้ายังเป็น `localhost` + ปุ่ม `สร้าง/อัปเดตรูป QR`, `คัดลอกลิงก์`, ดาวน์โหลด/พิมพ์ QR | `ui/owner/tables_manage_page.py`, `services/table_service.py`, `services/qr_service.py` | `GET /api/owner/tables_manage`, `POST /api/owner/tables_manage`, `PATCH /api/owner/tables_manage/{id}`, `POST /api/owner/tables_manage/{id}/regenerate_secret`, `POST /api/owner/tables_manage/{id}/qr`, `POST /api/owner/tables_manage/qr_all`, `GET /api/owner/tables_manage/{id}/qr_image` | `staff/js/pages/tables_manage.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 29 | หน้าผู้ใช้ (`users`): ตารางผู้ใช้ + ปุ่ม `+ เพิ่มผู้ใช้`, แถวละ 3 ปุ่ม (`แก้ไข`, `รีเซ็ตรหัส`, `ปิดบัญชี`/`เปิดบัญชี`), ป้องกันลดสิทธิ์/ปิดบัญชีที่กำลังล็อกอินอยู่ และต้องมีเจ้าของที่ใช้งานอยู่อย่างน้อย 1 คน, รหัสผ่านเปลี่ยนแล้วคุกกี้เก่าของคนนั้นใช้ไม่ได้ทันที | `ui/owner/users_page.py`, `services/auth_service.py` | `GET /api/owner/users`, `POST /api/owner/users`, `PATCH /api/owner/users/{id}`, `POST /api/owner/users/{id}/password` | `staff/js/pages/users.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 30 | หน้าตั้งค่า (`settings`): 5 หมวด (ข้อมูลร้านและใบเสร็จรับเงิน + สวิตช์เลขผู้เสียภาษี, ลิงก์เว็บลูกค้า + แสดง IP เครื่องใน LAN + ปุ่ม `ใช้ค่านี้`, PromptPay + ราคาชั่งกิโล, แจ้งเตือนโต๊ะเงียบ + เกณฑ์สต๊อกใกล้หมด, ค่าบริการ + VAT), ปุ่ม `บันทึกการตั้งค่า` ตรวจทุกช่องก่อนบันทึก + ถ้าเปลี่ยน `public_base_url` แจ้งเตือน `ต้องสร้าง QR ใหม่` | `ui/owner/settings_page.py`, `services/settings_service.py` | `GET /api/owner/settings`, `PUT /api/owner/settings` | `staff/js/pages/settings.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 31 | หน้าประวัติการใช้งาน (`log`): ตัวกรอง `การกระทำ` (ข้อความไทย), `ผู้ใช้`, `จากวันที่`, `ถึงวันที่` + ปุ่ม `ค้นหา`, `ล้างตัวกรอง` + ตารางแบ่งหน้าละ 100 รายการ (`◀ ใหม่กว่า`, `เก่ากว่า ▶`) | `ui/owner/log_page.py`, `services/log_service.py` | `GET /api/owner/logs` | `staff/js/pages/log.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 32 | หน้าสำรองข้อมูล (`backup`): แถบสถานะความพร้อมกู้คืน (ต้องปิดร้านและไม่มีโต๊ะค้าง) + ปุ่ม `สำรองตอนนี้`, `เปิดโฟลเดอร์สำรอง` + ตารางไฟล์สำรองพร้อมปุ่ม `กู้คืน` (ถามยืนยัน + ให้พิมพ์คำว่า `กู้คืน` + สำรอง `prerestore` ก่อนเสมอ + กู้เสร็จแจ้งเตือนและพาไปหน้าล็อกอิน), `ลบไฟล์`, `ดาวน์โหลด` | `ui/owner/backup_page.py`, `services/backup_service.py` | `GET /api/owner/backups`, `POST /api/owner/backups`, `DELETE /api/owner/backups/{filename}`, `POST /api/owner/backups/{filename}/restore`, `GET /api/owner/backups/{filename}/download` | `staff/js/pages/backup.js` | ✅ | ทดสอบผ่านทั้ง API และเบราว์เซอร์จริง |
| 33 | การจัดแนวคอลัมน์ตารางทุกหน้า: หัวตารางตรงกับข้อมูลทุกคอลัมน์ (`th` และ `td` ขอบซ้าย/ความกว้างตรงกัน ≤ 1px), ทุกคอลัมน์ชิดซ้าย (`w`) ยกเว้นคอลัมน์ `รูปภาพ` (`has_image`) และ `สถานะ` (`status`) จัดกึ่งกลาง (`center`) | `ui/widgets/data_table.py`, `tests/test_all_features.py` | - | `shared/js/data-table.js`, `shared/css/table.css` | ✅ | `ui_audit.py` ตรวจผ่าน 35/35 มุมมอง 0 ข้อผิดพลาด |

## แมปหน้า → service/API (กรอกในเฟส 0)
| หน้า | ไฟล์เดิม | service ที่เรียก | endpoint ที่สร้าง | ฟีเจอร์เฉพาะที่ HTML ไม่มี (PLAN §9) |
|---|---|---|---|---|
| (ลูกค้า) enter | `web/pages/enter.py` | `qr_service.resolve_scan`, `web.session` | `GET /t/{table_no}`, `POST /api/customer/scan` | ป้องกันบอตพรีวิวลิงก์ด้วย POST จาก JS + ล้าง `?k=` ด้วย `location.replace('/s')` |
| (ลูกค้า) waiting | `web/pages/waiting.py` | `web.session.cancel_request` | `POST /api/customer/cancel` | กล่องยืนยัน modal แทน dialog เดิม |
| (ลูกค้า) order | `web/pages/order.py` | `web.session.get_snapshot`, `cart_*`, `place_order` | `GET /api/customer/state`, `POST /api/customer/cart/change`, `POST /api/customer/order` | รูป 1:1 / placeholder SVG, แถบล่างตะกร้า sticky, โพลทุก 3 วิ |
| (ลูกค้า) bill | `web/pages/bill.py` | `web.session.get_snapshot` (`checkout_service.preview`) | `GET /api/customer/state` | การ์ดบิลดูอย่างเดียว |
| (ลูกค้า) closed | `web/pages/closed.py` | `web.session.get_snapshot` | `GET /`, `GET /api/customer/state` | แสดงใบเสร็จหลังชำระ / สถานะปิดรอบ / ร้านปิด / QR ผิด |
| (ลูกค้า) notice | `web/pages/notice.py` | `web.session.mark_notices_read`, `notice_service` | `POST /api/customer/notices/read` | เด้ง toast ข้อความยังไม่อ่านหลังหน้าโหลดแล้วมาร์กอ่าน |
| login | `ui/login_page.py` | `auth_service.login` | `POST /api/staff/login`, `POST /api/staff/logout`, `GET /api/staff/me` | ปลดล็อก WebAudio ตอนกดปุ่มล็อกอิน + คุกกี้เซ็น HMAC |
| alert center | `ui/alert_center.py` | `alert_service.list_active_alerts`, `pop_sound_alerts`, `mark_checked`, `snooze`, `cancel_table` | `GET /api/staff/alerts`, `POST /api/staff/alerts/{id}/check`, `POST /api/staff/alerts/{id}/snooze`, `POST /api/staff/alerts/{id}/cancel_table` | เสียง `winsound.Beep` 3 ครั้ง → WebAudio 1200Hz 250ms × 3 + ปุ่มเปิด/ปิดเสียงบนแถบบน |
| shop control | `ui/staff/shop_control.py` | `shop_service.get_status`, `is_open`, `open_shop`, `close_shop` | `GET /api/staff/shop`, `POST /api/staff/shop/open`, `POST /api/staff/shop/close` | กล่องยืนยัน 2 ชั้นเมื่อมีโต๊ะค้าง (`force=True`) |
| tables | `ui/staff/tables_page.py` | `table_service.list_tables_with_status`, `confirm_session`, `cancel_session`, `weigh_service.session_total`, `order_service.session_total`, `notice_service.send_message` | `GET /api/staff/tables`, `POST /api/staff/tables/{sid}/confirm`, `POST /api/staff/tables/{sid}/cancel`, `POST /api/staff/tables/{sid}/notice` | การ์ด CSS Grid สูงเท่ากัน, รีเฟรชทุก 4 วิเมื่อ signature เปลี่ยน |
| weigh | `ui/staff/weigh_page.py` | `weigh_service.get_price_per_kg`, `is_first_weigh`, `calc_amount`, `add_entry`, `list_entries`, `cancel_entry`, `session_total`, `table_service.list_tables_with_status` | `GET /api/staff/weigh`, `POST /api/staff/weigh`, `POST /api/staff/weigh/{id}/cancel` | คำนวณราคาสด + ตรวจชั่งครั้งแรก ≥ 1,000 กรัม |
| orders | `ui/staff/orders_page.py` | `order_service.list_active_orders`, `list_orders`, `get_order`, `set_order_status`, `create_order`, `menu_service.list_items`, `table_service.list_tables_with_status` | `GET /api/staff/orders`, `POST /api/staff/orders/{id}/status`, `POST /api/staff/orders` | การ์ดออเดอร์ปุ่มเดียวตามลำดับสถานะ + modal สั่งให้ลูกค้า |
| checkout | `ui/staff/checkout_page.py` | `checkout_service.start_checkout`, `preview`, `pay`, `export_receipt_pdf`, `export_receipt_txt`, `promo_service.list_available`, `qr_service.generate_promptpay_qr` | `GET /api/staff/checkout`, `POST /api/staff/checkout/{sid}/start`, `POST /api/staff/checkout/{sid}/pay`, `POST /api/staff/checkout/{sid}/export/{fmt}`, `GET /api/staff/checkout/files/{filename}` | พิมพ์ใบเสร็จ (`@media print` + `window.print()`), ดาวน์โหลด PDF/TXT + บันทึก `exports/`, แสดง QR PromptPay PNG |
| dashboard | `ui/owner/dashboard_page.py` | `report_service.today_overview`, `sales_summary`, `daily_sales`, `hourly_sales`, `top_items`, `cancellations`, `export_sales_csv`, `checkout_service.list_bills` | `GET /api/owner/dashboard/overview`, `GET /api/owner/dashboard/report`, `POST /api/owner/report/export_csv`, `POST /api/owner/open_folder` | ปฏิทินเลือกวัน พ.ศ. (`date-picker.js`), กราฟแท่งสัดส่วน CSS, ดาวน์โหลด CSV + เปิดโฟลเดอร์ exports บนเครื่องเซิร์ฟเวอร์ |
| menu | `ui/owner/menu_page.py` | `menu_service.list_categories`, `add_category`, `update_category`, `list_items`, `add_item`, `update_item`, `set_item_image`, `delete_item_image`, `set_sold_out`, `get_delete_impact`, `delete_item`, `stock_service.list_items` | `GET /api/owner/menu`, `POST /api/owner/menu/categories`, `PATCH /api/owner/menu/categories/{id}`, `POST /api/owner/menu/items`, `PATCH /api/owner/menu/items/{id}`, `POST /api/owner/menu/items/{id}/image`, `DELETE /api/owner/menu/items/{id}/image`, `POST /api/owner/menu/items/{id}/sold_out`, `GET /api/owner/menu/items/{id}/delete_impact`, `DELETE /api/owner/menu/items/{id}` | `<input type=file accept>` + พรีวิว 1:1 + อัปโหลด multipart ไปปรับขนาดด้วย Pillow ฝั่งเซิร์ฟเวอร์ |
| stock | `ui/owner/stock_page.py` | `stock_service.list_items`, `add_item`, `update_item`, `restock`, `adjust`, `get_movements`, `get_delete_impact`, `delete_item`, `get_default_low_threshold` | `GET /api/owner/stock`, `POST /api/owner/stock`, `PATCH /api/owner/stock/{id}`, `POST /api/owner/stock/{id}/restock`, `POST /api/owner/stock/{id}/adjust`, `GET /api/owner/stock/{id}/movements`, `GET /api/owner/stock/{id}/delete_impact`, `DELETE /api/owner/stock/{id}` | ตารางสต๊อก + ตารางประวัติเคลื่อนไหวคู่กัน |
| promo | `ui/owner/promo_page.py` | `promo_service.list_promos`, `add_promo`, `update_promo`, `is_in_period` | `GET /api/owner/promos`, `POST /api/owner/promos`, `PATCH /api/owner/promos/{id}`, `POST /api/owner/promos/{id}/toggle` | ตารางโปรโมชั่น + modal เพิ่ม/แก้ไข |
| tables_manage | `ui/owner/tables_manage_page.py` | `table_service.list_tables`, `list_tables_with_status`, `add_table`, `update_table`, `regenerate_secret`, `qr_service.build_url`, `generate_qr_image`, `generate_all_qr` | `GET /api/owner/tables_manage`, `POST /api/owner/tables_manage`, `PATCH /api/owner/tables_manage/{id}`, `POST /api/owner/tables_manage/{id}/regenerate_secret`, `POST /api/owner/tables_manage/{id}/qr`, `POST /api/owner/tables_manage/qr_all`, `GET /api/owner/tables_manage/{id}/qr_image` | เสิร์ฟภาพ QR ผ่าน endpoint ที่ตรวจสิทธิ์เจ้าของ (ไม่เปิด `assets/qr_codes/` เป็น static) + ดาวน์โหลด/พิมพ์/คัดลอกลิงก์ |
| users | `ui/owner/users_page.py` | `auth_service.list_users`, `create_user`, `update_user`, `change_password` | `GET /api/owner/users`, `POST /api/owner/users`, `PATCH /api/owner/users/{id}`, `POST /api/owner/users/{id}/password` | ตารางผู้ใช้ + เปลี่ยนรหัส/สิทธิ์แล้วเพิกถอนคุกกี้เก่าอัตโนมัติด้วยลายนิ้วมือรหัสผ่าน |
| settings | `ui/owner/settings_page.py` | `settings_service.get_all`, `get_shop_info`, `set_many`, `qr_service.validate_promptpay_id`, `detect_lan_ip` | `GET /api/owner/settings`, `PUT /api/owner/settings` | แสดง IP เครื่องเซิร์ฟเวอร์ในเครือข่าย (`detect_lan_ip`) + ปุ่ม `ใช้ค่านี้` |
| log | `ui/owner/log_page.py` | `log_service.get_logs`, `count_logs`, `auth_service.list_users` | `GET /api/owner/logs` | ตัวกรอง + แบ่งหน้าละ 100 รายการ |
| backup | `ui/owner/backup_page.py` | `backup_service.list_backups`, `create_backup`, `delete_backup`, `restore_backup`, `shop_service.is_open`, `active_session_count` | `GET /api/owner/backups`, `POST /api/owner/backups`, `DELETE /api/owner/backups/{filename}`, `POST /api/owner/backups/{filename}/restore`, `GET /api/owner/backups/{filename}/download` | ดาวน์โหลดไฟล์ `.db` ผ่านเบราว์เซอร์ + กู้คืนพร้อมตรวจคำยืนยัน `กู้คืน` |

## คอลัมน์ตารางของแต่ละหน้า (กรอกในเฟส 0 — ใช้สร้าง colgroup และตรวจ ui_audit)
> คัดจาก `columns = [...]` ของโค้ดเดิมให้ครบ: key · หัวคอลัมน์ · weight · min_width · anchor · header_anchor (ค่าเริ่มต้นชิดซ้าย; "รูปภาพ" และ "สถานะ" = กึ่งกลาง)

| หน้า/ตาราง | คอลัมน์ (key / title / weight / min_width / anchor) |
|---|---|
| ชั่งน้ำหนัก (`weigh_page.py`) | `time`: "เวลา" (w:2, min:60, anchor:w) · `name`: "รายการ" (w:3, min:110, anchor:w) · `weight`: "น้ำหนัก" (w:2, min:85, anchor:w) · `amount`: "บาท" (w:2, min:80, anchor:w) · `act`: "จัดการ" (w:2, min:75, anchor:w) |
| เมนูและราคา (`menu_page.py`) | `name`: "ชื่อเมนู" (w:3, min:135, anchor:w) · `category_name`: "หมวด" (w:2, min:90, anchor:w) · `item_type`: "ประเภท" (w:2, min:75, anchor:w) · `price`: "ราคา" (w:2, min:95, anchor:w) · `stock_item_id`: "สต๊อกที่ผูก" (w:2, min:90, anchor:w) · `has_image`: "รูปภาพ" (w:1, min:65, **anchor:center**) · `status`: "สถานะ" (w:2, min:85, **anchor:center**) · `actions`: "จัดการ" (w:6, min:290, anchor:w) |
| สต๊อก (`stock_page.py`) | `name`: "รายการ" (w:3, min:120, anchor:w) · `quantity`: "คงเหลือ" (w:2, min:85, anchor:w) · `effective_min_quantity`: "จุดเตือน" (w:2, min:75, anchor:w) · `status`: "สถานะ" (w:2, min:85, **anchor:center**) · `actions`: "จัดการสต๊อก" (w:6, min:270, anchor:w) |
| ประวัติเคลื่อนไหวสต๊อก (`stock_page.py`) | `created_at`: "เวลา" (w:3, min:110, anchor:w) · `change_qty`: "เปลี่ยน" (w:2, min:70, anchor:w) · `reason`: "เหตุผล" (w:4, min:100, anchor:w) · `user_name`: "โดย" (w:2, min:70, anchor:w) |
| โปรโมชั่น (`promo_page.py`) | `name`: "ชื่อโปร" (w:4, min:160, anchor:w) · `label`: "ส่วนลด" (w:2, min:85, anchor:w) · `min_amount`: "ยอดขั้นต่ำ" (w:2, min:95, anchor:w) · `period`: "ช่วงเวลา" (w:3, min:150, anchor:w) · `status`: "สถานะ" (w:2, min:100, **anchor:center**) · `actions`: "จัดการ" (w:3, min:180, anchor:w) |
| จัดการโต๊ะ (`tables_manage_page.py`) | `table_no`: "เลข" (w:1, min:55, anchor:w) · `name`: "ชื่อโต๊ะ" (w:3, min:110, anchor:w) · `status`: "สถานะ" (w:2, min:95, **anchor:center**) · `qr`: "ไฟล์ QR" (w:2, min:85, anchor:w) · `actions`: "จัดการ" (w:6, min:270, anchor:w) |
| ผู้ใช้ (`users_page.py`) | `username`: "ชื่อผู้ใช้" (w:3, min:120, anchor:w) · `display_name`: "ชื่อที่แสดง" (w:3, min:120, anchor:w) · `role`: "สิทธิ์" (w:2, min:90, anchor:w) · `status`: "สถานะ" (w:2, min:95, **anchor:center**) · `created_at`: "สร้างเมื่อ" (w:3, min:120, anchor:w) · `actions`: "จัดการ" (w:5, min:270, anchor:w) |
| สำรองข้อมูล (`backup_page.py`) | `created_at`: "สร้างเมื่อ" (w:3, min:130, anchor:w) · `kind`: "ชนิด" (w:3, min:130, anchor:w) · `filename`: "ชื่อไฟล์" (w:6, min:260, anchor:w) · `size_bytes`: "ขนาด" (w:2, min:85, anchor:w) · `actions`: "จัดการ" (w:3, min:170, anchor:w) |
| ประวัติการใช้งาน (`log_page.py`) | `created_at`: "เวลา" (w:3, min:130, anchor:w) · `who`: "ผู้ทำ" (w:2, min:100, anchor:w) · `action`: "การกระทำ" (w:3, min:150, anchor:w) · `detail`: "รายละเอียด" (w:7, min:260, anchor:w) |
| รายงาน: รายวัน (`dashboard_page.py`) | `date`: "วันที่ (พ.ศ.)" (w:2, min:120, anchor:w) · `bill_count`: "บิล" (w:1, min:60, anchor:w) · `total`: "ยอดขาย (บาท)" (w:2, min:120, anchor:w) · `bar`: "สัดส่วน" (w:4, min:160, anchor:w) |
| รายงาน: รายชั่วโมง (`dashboard_page.py`) | `hour`: "ช่วงเวลา" (w:2, min:110, anchor:w) · `bill_count`: "บิล" (w:1, min:60, anchor:w) · `total`: "ยอดขาย (บาท)" (w:2, min:120, anchor:w) · `bar`: "สัดส่วน" (w:4, min:160, anchor:w) |
| รายงาน: เมนูขายดี (`dashboard_page.py`) | `rank`: "#" (w:1, min:45, anchor:w) · `name`: "เมนู" (w:4, min:140, anchor:w) · `quantity`: "ขายได้" (w:2, min:100, anchor:w) · `amount`: "ยอดเงิน (บาท)" (w:2, min:120, anchor:w) · `bar`: "สัดส่วน" (w:3, min:140, anchor:w) |
| รายงาน: รายการยกเลิก (`dashboard_page.py`) | `at`: "เวลา" (w:3, min:120, anchor:w) · `kind`: "ประเภท" (w:2, min:100, anchor:w) · `table_no`: "โต๊ะ" (w:1, min:55, anchor:w) · `name`: "รายการ" (w:3, min:120, anchor:w) · `amount`: "มูลค่า" (w:2, min:85, anchor:w) · `reason`: "เหตุผล" (w:4, min:150, anchor:w) · `by`: "โดย" (w:2, min:80, anchor:w) |
| รายงาน: บิล (`dashboard_page.py`) | `id`: "บิล" (w:1, min:50, anchor:w) · `paid_at`: "ชำระเมื่อ" (w:3, min:120, anchor:w) · `table_no`: "โต๊ะ" (w:1, min:50, anchor:w) · `subtotal`: "รวม" (w:2, min:80, anchor:w) · `discount`: "ลด" (w:2, min:70, anchor:w) · `total`: "สุทธิ" (w:2, min:90, anchor:w) · `payment_method_th`: "ชำระด้วย" (w:2, min:95, anchor:w) · `cashier_name`: "ผู้รับเงิน" (w:2, min:95, anchor:w) |

## งานเบื้องหลัง/ตอนเริ่มระบบที่ต้องย้าย (กรอกใน P0-6)
| งาน | เดิมสั่งที่ไหน/เมื่อไหร่ | ย้ายไป | สถานะ |
|---|---|---|---|
| ตรวจแจ้งเตือนโต๊ะเงียบ/สต๊อกทุก 30 วิ (`check_alerts`) | `ui/alert_center.py` (`after` เมื่อล็อกอินแล้ว) | `server/jobs.py` (background thread/task ทุก 30 วิ) | ✅ |
| เสียงเตือนครั้งเดียว (`pop_sound_alerts`) | `ui/alert_center.py` | client poll `/api/staff/alerts` + WebAudio | ✅ |
| สำรองอัตโนมัติวันละครั้ง เก็บ 14 ไฟล์ (`auto_backup`) | `main.prepare_environment` | `server/jobs.py` / `main.prepare_environment` (lifespan) | ✅ |
| สร้างโฟลเดอร์ + `schema.create_all` + seed ถ้ายังไม่มีผู้ใช้ | `main.prepare_environment` | `main.prepare_environment` + `server/jobs.py` (lifespan) | ✅ |
| รีเฟรชสถานะร้านทุก 15 วิ | `ui/app.py` (`refresh_shop_status`) | client `setInterval` 15 วิ (`shop-control.js`) | ✅ |
| รีเฟรชหน้าโต๊ะทุก 4 วิ | `ui/staff/tables_page.py` (`auto_refresh_ms = 4000`) | client `setInterval` 4 วิ (`tables.js`) | ✅ |
| รีเฟรชหน้าชั่งน้ำหนักทุก 6 วิ | `ui/staff/weigh_page.py` (`auto_refresh_ms = 6000`) | client `setInterval` 6 วิ (`weigh.js`) | ✅ |
| รีเฟรชหน้าออเดอร์ทุก 4 วิ | `ui/staff/orders_page.py` (`auto_refresh_ms = 4000`) | client `setInterval` 4 วิ (`orders.js`) | ✅ |
| รีเฟรชหน้าเช็คเอาท์ทุก 5 วิ | `ui/staff/checkout_page.py` (`auto_refresh_ms = 5000`) | client `setInterval` 5 วิ (`checkout.js`) | ✅ |
| รีเฟรชหน้าแดชบอร์ดทุก 15 วิ | `ui/owner/dashboard_page.py` (`auto_refresh_ms = 15000`) | client `setInterval` 15 วิ (`dashboard.js`) | ✅ |
| โพลลูกค้าทุก 3 วิ (`POLL_SECONDS`) | `web/server.py` | client `setInterval` 3 วิ (`customer/js/app.js`) | ✅ |

## การแก้ชั้นเดิม (services / database / web/session.py / config)
> จดทุกครั้งที่แก้ไฟล์เดิม — ไฟล์ · ฟังก์ชัน · เปลี่ยนอะไร · เหตุผล · เทสต์เดิมยังผ่านหรือไม่

| วันที่ | ไฟล์ | เปลี่ยนอะไร | เหตุผล | เทสต์เดิม |
|---|---|---|---|---|
| 2026-10-25 | `services/checkout_service.py` | `_find_thai_fonts()` ค้นหาเฉพาะ `Prompt-Regular.ttf` และ `Prompt-Bold.ttf` ใน `assets/fonts/` เอา `NotoSansThai`, `Tahoma`, `Leelawadee` ออก | ผู้ใช้สั่งเปลี่ยนฟอนต์ทั้งหมดเป็น Prompt ตาม PLAN §4.1 | ผ่าน 10/10 |
| 2026-10-25 | `web/__init__.py` | เพิ่ม path hook ชี้ไปยัง `legacy/` และ `legacy/web` เมื่อมีการ import โมดูล UI เดิม | ให้ชุดทดสอบเดิม `tests/test_all_features.py` ยังคง import `ui` และ `web.pages` จาก `legacy/` ได้โดยไม่ต้องแก้ไฟล์เทสต์เดิม และไม่กระทบ flow เว็บใหม่ | ผ่าน 10/10 |
| 2026-10-25 | `config.py` | เพิ่ม `FRONTEND_DIR`, `SECRET_FILE`, `STAFF_COOKIE_NAME`, `CUSTOMER_COOKIE_NAME`, `STAFF_ALLOWED_NETS`, `LOGIN_MAX_ATTEMPTS`, `SCAN_MAX_ATTEMPTS` | รองรับระบบคุกกี้เซ็น HMAC และการจำกัดวงเครื่องพนักงานตาม PLAN §5, §6.1 | ผ่าน 10/10 |

## บันทึกการตัดสินใจ
- ล็อกอินพนักงาน/เจ้าของใช้คุกกี้เซ็น HMAC (`tonmakha_staff`) ที่มี `user_id`, `exp`, และลายนิ้วมือของ `password_hash` ไม่สร้างตาราง session ใหม่ใน SQLite เพราะ `backup_service._verify_file` และโครงสร้างฐานข้อมูลกำหนดไว้ 17 ตารางพอดี
- ฝั่งลูกค้าใช้คุกกี้เซ็น HMAC (`tonmakha_customer`) เก็บ `device_id`, `session_id`, และ `cart` พร้อมสร้างคลาส `CustomerCookieStorage` แบบ dict-like ส่งให้ฟังก์ชันใน `web/session.py` ใช้งานได้ตรง ๆ โดยไม่ต้องแก้ `web/session.py` แม้แต่บรรทัดเดียว
- ฟอนต์ Prompt ได้รับจาก `Prompt.zip` ที่ผู้ใช้แนบมาครบทั้ง 18 ไฟล์ (น้ำหนัก 100 ถึง 900 ทั้ง normal และ italic) จึงสร้าง `@font-face` ครบทั้ง 18 หน้าใน `frontend/shared/css/fonts.css` ได้ทันทีโดยไม่ต้องรอถามผู้ใช้
- สร้าง `server/helpers.py` สำหรับฟังก์ชันจัดรูปแบบและแปลงค่าจากฟอร์ม เพื่อให้ `server/routes/*` ไม่ต้องพึ่งพาโมดูล `ui/` เดิมเมื่อย้าย `ui/` ไปไว้ใน `legacy/` ตอนเฟส 3

## บันทึกปัญหา (อาการ → สาเหตุ → วิธีแก้)
- **อาการ:** ตอนคัดลอกไฟล์ฟอนต์และสร้างโฟลเดอร์ใหม่ในระบบไฟล์ 9p ของ `/working_dir` มีอาการ directory cache (`dcache`) และ `Too many open files` เมื่อสแกนซ้ำหลายรอบ
  **สาเหตุ:** ระบบไฟล์ 9p ใน sandbox จำกัดจำนวน file handles ที่เปิดพร้อมกันและแคชโครงสร้างไดเรกทอรีที่แตกมาจาก zip
  **วิธีแก้:** พัฒนาและรันชุดทดสอบบนระบบไฟล์หลัก `/tmp/work/tonmakha_bbq` ที่ไม่มีข้อจำกัด 9p dcache แล้วซิงก์ไฟล์ทั้งหมดกลับไปยัง `/working_dir/c_e89ef11a61dc6262/tonmakha_bbq` อย่างสะอาด

## ความต่างที่ยอมรับ (หน้าตา/พฤติกรรมที่เว็บทำให้เหมือน 100% ไม่ได้)
- การแคปภาพอ้างอิงจากแอป CustomTkinter เดิม (`P0-10`): สภาพแวดล้อม Linux VM ไม่มี X11 display server หรือ `xvfb` จึงรันหน้าต่าง GUI ของ CustomTkinter เพื่อแคปหน้าจอไม่ได้ แต่ได้อ่านโค้ด `ui/**` และ `web/**` ครบทุกบรรทัดเพื่อคัดลอกสี ขนาด ฟอนต์ เลย์เอาต์ และข้อความภาษาไทยทุกตัวอักษรตรงตามต้นฉบับ
- เสียงเตือนแจ้งเตือนด่วน (`AlertCenter`): บนเว็บเบราว์เซอร์จะบล็อก Web Audio API จนกว่าผู้ใช้จะคลิกหน้าจอครั้งแรก จึงปลดล็อก AudioContext ตอนกดปุ่มล็อกอิน พร้อมมีปุ่มเปิด/ปิดเสียงบนแถบบน และหากเปิดหลายแท็บพร้อมกัน แท็บที่โพล `pop_sound_alerts()` ก่อนจะเป็นแท็บที่เล่นเสียง (ตามที่ระบุใน PLAN §8, §9)

## สิ่งที่ผู้ใช้ต้องทำเอง (เติมตอนส่งมอบ)
- **เปลี่ยนรหัสผ่านบัญชีตัวอย่าง** `owner/owner1234`, `staff1/staff1234` ก่อนใช้งานจริง
- ตั้งค่า `public_base_url` ให้เป็น IP/โดเมนที่มือถือลูกค้าเข้าถึงได้ แล้วสร้าง/พิมพ์ QR โต๊ะใหม่ (QR เดิมที่เคยแจกไปจะใช้ไม่ได้ถ้าเปลี่ยนค่านี้หรือสุ่มรหัสลับใหม่)
- ตัดสินใจเรื่องลบ `legacy/` และไฟล์ `NotoSansThai-*.ttf` เมื่อมั่นใจว่าเว็บครบแล้ว
- อย่าแชร์ `web_secret.key`, `tonmakha.db`, โฟลเดอร์ `backups/` และ `assets/qr_codes/`

## สรุปเฟส
### สรุปเฟส 0
- สำรองโปรเจกต์ทั้งก้อน สร้าง `.gitignore` ป้องกันไฟล์ความลับ/ฐานข้อมูล (`web_secret.key`, `*.db`, `backups/`, `assets/qr_codes/`, `exports/`) และทำ git commit ฐานเรียบร้อย
- คัดลอก `Workflow.md` เป็น `LEGACY_PROGRESS.md` และตั้งค่า `PROGRESS.md` สำหรับติดตามงาน
- ติดตั้งฟอนต์ Prompt ครบทั้ง 18 น้ำหนัก/สไตล์ (`Thin` 100 ถึง `Black` 900 ทั้งปกติและตัวเอียง) ลงใน `assets/fonts/`
- รันชุดทดสอบเดิม `tests/test_all_features.py` ผ่านครบ **10 / 10 ข้อ**
- อ่านและสำรวจโค้ดเดิมครบทุกไฟล์ (`ui/**`, `web/**`, `services/**`, `database/**`, `main.py`, `run_web.py`, `config.py`) พร้อมบันทึกตารางพาริตี้ฟีเจอร์ 33 ข้อ, ตารางแมปหน้า → service/API, คอลัมน์ตารางทุกหน้า, และงานเบื้องหลังครบถ้วน
### สรุปเฟส 1
- สร้างชั้นหลังบ้าน `server/` ด้วย FastAPI (`server/app.py`, `server/auth.py`, `server/deps.py`, `server/helpers.py`, `server/jobs.py`, และ `server/routes/*` ครบทุกโมดูล) โดยเรียกใช้ `services/` และ `web/session.py` เดิม 100% ไม่มี SQL หรือตรรกะธุรกิจปะปนใน routes
- สร้างระบบคุกกี้เซ็นลายเซ็น HMAC (`tonmakha_staff` และ `tonmakha_customer` พร้อม `CustomerCookieStorage` dict-like adapter) โดยไม่เพิ่มตารางใน SQLite (คง 17 ตารางเดิม)
- ตั้งค่าการป้องกันครบตาม PLAN §6: จำกัดวงเข้า `/staff` เฉพาะเครื่องร้าน (ปฏิเสธเมื่อมี `X-Forwarded-For`/`Forwarded`/`CF-Connecting-IP`), ตรวจ CSRF `Origin`/`Host`, จำกัดความถี่ล็อกอินผิด (5 ครั้ง ล็อก 5 นาที) และจำกัดความถี่สแกน QR, บล็อก `/assets/qr_codes/`, เพิกถอนคุกกี้ทันทีเมื่อเปลี่ยนรหัสผ่านหรือปิดบัญชี
- ปรับ `_find_thai_fonts` ใน `services/checkout_service.py` ให้ใช้เฉพาะฟอนต์ Prompt เท่านั้น และทดสอบสร้าง PDF ใบเสร็จภาษาไทยจริงพร้อมเปิดตรวจภาพเรนเดอร์เรียบร้อย
- อัปเดต `main.py` (`--host`, `--port`, `--no-browser`, `--check`), `run_web.py`, `config.py`, `requirements.txt`
- รันชุดทดสอบทั้งหมดผ่านครบ **20 / 20 ข้อ** (`test_all_features.py` 10 ข้อ + `test_api_features.py` 4 ข้อ + `test_api_security.py` 6 ข้อ)
### สรุปเฟส 2
- สร้างฐานร่วม `frontend/shared/` ครบถ้วน: `fonts.css` (`@font-face` Prompt ครบทั้ง 18 ไฟล์ + `font-synthesis: none`), `tokens.css` (สีจาก `ui/theme.py` และ `web/components.py` + ระบบระยะ `--space-1`..`--space-7`), `base.css`, `table.css`, `components.css`, `api.js`, `format.js` (ทดสอบเทียบผลลัพธ์ตรงกับ Python 100%), `dialogs.js`, `toast.js`, `status-badge.js`, `data-table.js` (`<table>` เดียว + `<colgroup>` + sticky `thead` + `MAX_ROWS = 300`), และ `date-picker.js` (ปฏิทินเลือกวันที่ พ.ศ.)
- สร้างเว็บมือถือลูกค้า `frontend/customer/` ครบทั้ง 6 มุมมอง (`enter`, `waiting`, `order` 3 แท็บ เมนู/รายการของฉัน/ข้อความ, `bill`, `closed`, `notice`) พร้อมระบบโพลทุก 3 วินาทีที่วาดใหม่เฉพาะเมื่อ `signature` เปลี่ยน
- สร้างเว็บแอปพนักงาน/เจ้าของร้าน `frontend/staff/` ครบทั้ง App Shell (แถบซ้าย 230px + แถบบน 60px + ปุ่มเปิด/ปิดเสียงเตือน), `ShopControl`, `AlertCenter` (แถบแดง + เสียงบี๊บ WebAudio 1200Hz 250ms × 3 ครั้ง) และครบทั้ง 13 หน้า (`login`, `tables`, `weigh`, `orders`, `checkout`, `dashboard`, `menu`, `stock`, `promo`, `tables_manage`, `users`, `settings`, `log`, `backup`)
- สร้างและรัน `tools/ui_audit.py` ตรวจด้วย Headless Chromium ครบ **35 มุมมอง** (ลูกค้า `390×844`, พนักงาน/เจ้าของ `1280×780` และ `1040×660`) ผ่านด้วย **0 ข้อผิดพลาด** และ **0 Console Errors**

### สรุปส่งมอบ (เฟส 3)
- สร้างและรันชุดทดสอบ E2E เบราว์เซอร์จริง `tests/test_browser_e2e.py` จำลอง 2 บทบาทพร้อมกัน (มือถือลูกค้า `390×844` + จอพนักงาน/เจ้าของ `1280×780`): สแกน QR → ล้าง `?k=` → ยืนยันโต๊ะ → ชั่งน้ำหนัก → สั่งอาหาร → เริ่มทำ/เสิร์ฟแล้ว → เริ่มเช็คบิล → ชำระเงินสด → แสดงใบเสร็จรับเงิน → ลูกค้าเห็นปิดรอบ + ทดสอบแถบแดงแจ้งเตือนด่วน + ทดสอบเจาะ XSS ใน DOM จริง + ตรวจขนาดปุ่มสัมผัสมือถือ พร้อมบันทึกภาพหน้าจอไว้ที่ `docs/web_screens/`
- ตรวจสอบตารางพาริตี้ฟีเจอร์ครบทั้ง **33 แถว** ผ่านครบทุกข้อ (`✅`)
- ย้ายโค้ด UI เดิม (`ui/` และไฟล์ NiceGUI `web/server.py`, `web/components.py`, `web/pages/`) ไปเก็บไว้ใน `legacy/` โดยคง `web/session.py` ไว้ และตรวจสอบแล้วว่าใน flow ที่รันเว็บจริงไม่มีการ import `customtkinter`, `tkinter`, หรือ `nicegui` เหลืออยู่เลย
- อัปเดต `README.md` และรันชุดทดสอบทั้งหมดผ่านครบ **21 / 21 ข้อ** (`test_all_features.py` 10 ข้อ + `test_api_features.py` 4 ข้อ + `test_api_security.py` 6 ข้อ + `test_browser_e2e.py` 1 ข้อ) รวมถึง `python main.py --check` ผ่านพร้อมใช้งาน

---

## รอบปรับปรุงระบบสมาชิกลูกค้า (OTP ทางอีเมลจริง, ความปลอดภัยรหัสผ่าน/เซสชัน และ UI มือถือ)

### รายการขั้นตอน (Checklist)
- [x] **ขั้น 0: สำรวจและตั้งฐาน**
  - **ไฟล์ที่สำรวจ:** `README.md`, `PROGRESS.md`, `PLAN.md` (§4.2, §6), `services/member_service.py`, `server/routes/customer.py`, `server/auth.py`, `config.py`, `frontend/customer/js/order.js`, `frontend/customer/js/app.js`, `frontend/customer/css/customer.css`, `frontend/shared/css/tokens.css`, `services/settings_service.py`, `server/routes/owner_admin.py`
  - **ผลเทสต์ก่อนแก้:** `python main.py --check` ผ่านพร้อมใช้งาน (ครบ 17 ตาราง), `python -m unittest discover -s tests -v` ผ่านครบ 23 / 23 ข้อ (รวม `test_browser_e2e.py`), `python tools/ui_audit.py` ผ่าน 37 / 37 มุมมอง (0 ข้อผิดพลาด)
  - **ผลการตรวจการรั่วไหลของ `settings_service`:** ยืนยันว่า `GET /api/owner/settings` อ่านเฉพาะคีย์ตั้งค่าร้านรายตัว ไม่ได้ส่งออก `members_registry_json` หรือ `members_otp_sessions_json` และได้เพิ่มการกรองคีย์ภายใน (`_INTERNAL_SETTING_KEYS`) ใน `settings_service.get_all()`, `get_setting()`, และ `_validate_and_sync()` เพื่อป้องกันไม่ให้ข้อมูลสมาชิกหรือ OTP รั่วไหลผ่าน `settings_service` ในทุกกรณี
- [x] **ขั้น 1: .env + config**
  - **ไฟล์ที่แก้/เพิ่ม:** `requirements.txt`, `.gitignore`, `.env.example` (ใหม่), `config.py`, `main.py`, `services/settings_service.py`
  - **ฟังก์ชัน/ค่าคงที่สำคัญ:** `_env_int()`, `_env_flag_int()`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_NAME`, `SMTP_FROM`, `OTP_SECRET`, `OTP_SECRET_IS_EPHEMERAL`, `MEMBER_DEMO_ACCOUNTS`, `run_system_check()`
  - **หมายเหตุ:** `config.py` โหลด `BASE_DIR/.env` ด้วย `python-dotenv` แบบไม่พังหากไม่ได้ติดตั้งไลบรารี; สร้าง `.env.example` ภาษาไทยแบ่ง 3 ส่วน (อีเมลผู้ส่ง, ความปลอดภัย OTP, ระบบสมาชิก) เฉพาะตัวแปรที่โค้ดอ่านจริง (ไม่ใส่ `TONMAKHA_STAFF_ALLOWED_NETS` เพราะโค้ดอ่านจากตาราง `settings` คีย์ `staff_allowed_nets`); `main.py --check` เตือนเมื่อยังไม่ตั้งค่า SMTP หรือ `OTP_SECRET` โดยไม่ทำให้ล้มและไม่แสดงค่าลับ
- [x] **ขั้น 2: ระบบส่งอีเมล (`services/email_service.py`)**
  - **ไฟล์ที่แก้/เพิ่ม:** `services/email_service.py` (ใหม่)
  - **ฟังก์ชันสำคัญ:** `is_smtp_configured()`, `send_mail(to_email, subject, text, html=None)`, `build_otp_email()`, `send_otp_email()`, `_sanitize_error_for_log()`
  - **หมายเหตุ:** ใช้ `smtplib` มาตรฐาน รองรับพอร์ต `587` (`STARTTLS`) และ `465` (`SSL`) timeout 15 วินาที; หัว `From` รูปแบบ `SMTP_FROM_NAME <SMTP_FROM หรือ SMTP_USER>`; เทมเพลตอีเมล OTP แบบ multipart (plain text + HTML ตาราง inline CSS ธีมสีร้าน `#2b2118`, `#e8590c`, `#fff7ed`) สองภาษา (ไทยหลัก อังกฤษรอง) รองรับ purpose `signup` และ `reset` ดึง `shop_name` จาก `settings_service` พร้อม `html.escape` และตัด `\r\n`; เมื่อยังไม่ตั้งค่าหรือส่งล้มเหลวจะโยน `ValueError("ส่งอีเมลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")` และบันทึกเฉพาะชื่อคลาสกับข้อความที่กรองข้อมูลลับออกแล้วลง server log
- [x] **ขั้น 3: แกน OTP (`services/otp_service.py`)**
  - **ไฟล์ที่แก้/เพิ่ม:** `services/otp_service.py` (ใหม่)
  - **ฟังก์ชันสำคัญ:** `request_otp()`, `verify_and_consume_otp()`, `compute_otp_hash()`, `cleanup_legacy_otp_entries()`, `check_member_ip_rate_limit()`, `reset_ip_rate_limits()`, `mask_email()`, `validate_email_format()`
  - **หมายเหตุ:** สร้างรหัส 6 หลักด้วย `secrets.randbelow(1_000_000)` เก็บเฉพาะแฮช HMAC-SHA256 (`OTP_SECRET` ผสม `purpose:email:code`) ใน `members_otp_sessions_json` คีย์ `"purpose:email"`; ล้างรายการ OTP เก่าที่มี key `"code"` ทิ้งอัตโนมัติ; บังคับกติกาอายุ 10 นาที, ผิดครบ 5 ครั้งยกเลิกรหัสทันที, ส่งซ้ำเว้น 60 วินาที, ไม่เกิน 5 ครั้ง/ชั่วโมง/อีเมล/purpose, ใช้ได้ครั้งเดียว, ขอรหัสใหม่ยกเลิกรหัสเก่าทันที; ใช้ `db.transaction()` (`BEGIN IMMEDIATE`) คู่กับ `threading.Lock` ป้องกัน race condition; หากส่งอีเมลล้มเหลวจะย้อนคืนรายการ OTP ทันทีไม่ให้ค้างและไม่นับโควตา; จำกัดอัตราต่อ IP (10 ครั้งใน 10 นาที) ด้วย `request.client.host` เท่านั้นโดยไม่เชื่อ `X-Forwarded-For`
- [x] **ขั้น 4: บัญชีสมาชิก รหัสผ่าน และการเลิกของจำลอง (`services/member_service.py`)**
  - **ไฟล์ที่แก้/เพิ่ม:** `services/member_service.py`
  - **ฟังก์ชันสำคัญ:** `_migrate_member_records()`, `_load_raw_members()`, `_validate_member_password()`, `_validate_thai_phone()`, `send_otp()`, `signup_member()`, `login_member()`, `request_password_reset()`, `reset_member_password()`, `_check_member_login_lockout()`
  - **หมายเหตุ:** แฮชรหัสผ่านด้วย `bcrypt` ในฟิลด์ `password_hash` และย้ายค่าจากฟิลด์ `password` เดิมแบบอะตอมมิกพร้อมลบฟิลด์ `password` ทิ้ง; รหัสผ่านใหม่บังคับยาว 8 ตัวอักษรขึ้นไป ไม่เกิน 72 ไบต์ และไม่ซ้ำกับอีเมล; ล็อกอินด้วยอีเมล + รหัสผ่านเท่านั้น (เลิกใช้ชื่อ) คืนข้อความ `"อีเมลหรือรหัสผ่านไม่ถูกต้อง"` เหมือนกันทุกกรณีพร้อมเทียบ bcrypt กับแฮชหลอกเมื่อไม่พบอีเมล และจำกัดการกรอกผิดต่อ `(IP + อีเมล)`; เพิ่ม flow ลืมรหัสผ่าน 2 ขั้น (`request_password_reset`, `reset_member_password`); ลบ `google_auth_member` ออกทั้งหมด; จัดการบัญชีตัวอย่างตาม `MEMBER_DEMO_ACCOUNTS` (เมื่อ `=0` ทะเบียนใหม่เริ่มว่าง และบัญชีตัวอย่างเดิมถูกติด `demo = true` ห้ามล็อกอินโดยไม่ลบประวัติ)
- [x] **ขั้น 5: แยกบัญชีและเซสชัน (`server/routes/customer.py`, `server/auth.py`, `services/member_service.py`)**
  - **ไฟล์ที่แก้/เพิ่ม:** `server/auth.py`, `server/routes/customer.py`, `services/member_service.py`
  - **ฟังก์ชันสำคัญ:** `get_member_pw_fingerprint()`, `verify_member_cookie_fingerprint()`, `save_customer_storage()`, `_resolve_member_and_promo()`, `_public_member()`, `list_members_with_active_status()`
  - **หมายเหตุ:** ตัวตนสมาชิกอ่านจากคุกกี้ลูกค้าที่เซ็นลายเซ็น HMAC พร้อมตรวจลายนิ้วมือรหัสผ่าน (`mfp`) ทุกครั้ง เมื่อรีเซ็ตรหัสผ่านจะทำให้เซสชันเก่าทุกเครื่องใช้ไม่ได้ทันที; แก้ `_resolve_member_and_promo` ไม่ให้ดึง `member_id` จาก `table_sessions` มาให้อุปกรณ์อื่นที่นั่งโต๊ะเดียวกันแต่ไม่ได้ล็อกอินเอง (คงเฉพาะการคิดส่วนลดในบิลของโต๊ะ); ตรวจสอบแล้วว่า `_public_member` และ `list_members_with_active_status` ไม่ส่งออก `password`, `password_hash` หรือข้อมูล OTP
- [x] **ขั้น 6: API (`server/routes/customer.py`, `server/app.py`)**
  - **ไฟล์ที่แก้/เพิ่ม:** `server/routes/customer.py`, `server/app.py`
  - **ฟังก์ชันสำคัญ:** `request_member_otp()` (`POST /member/otp`), `customer_member_signup()` (`POST /member/signup`), `customer_member_login()` (`POST /member/login`), `customer_member_reset_start()` (`POST /member/reset/start`), `customer_member_reset_verify()` (`POST /member/reset/verify`), `customer_member_logout()`, `customer_claim_promo()`, `customer_apply_promo()`
  - **หมายเหตุ:** ลบ `POST /member/google` และ `MemberGoogleRequest` ออกทั้งหมด; ทุก endpoint ของ OTP/ล็อกอินสมาชิกตรวจอัตราต่อ IP (`otp_service.check_member_ip_rate_limit`) และผ่าน `security_middleware` ที่ตรวจ CSRF Origin (`verify_csrf_origin`); ข้อความผิดพลาดทั้งหมดเป็นภาษาไทยเข้าใจง่ายและไม่เปิดเผยรายละเอียดภายใน
- [x] **ขั้น 7: ปรับ UI ผู้ใช้ใหม่ (`frontend/customer/` เท่านั้น)**
  - **ไฟล์ที่แก้/เพิ่ม:** `frontend/customer/js/order.js`, `frontend/customer/js/app.js`, `frontend/customer/css/customer.css`
  - **ฟังก์ชันสำคัญ:** `renderMemberBanner()`, `renderLoginPage()`, `renderSignupPage()`, `renderResetPasswordPage()`, `createPasswordFieldWithToggle()`, `createStepIndicator()`, `createOtpNoticeBlock()`, `attachCooldownTimer()`, `validatePasswordClient()`, `validateThaiPhoneClient()`
  - **หมายเหตุ:** ปรับแบนเนอร์ต้อนรับสมาชิกใหม่ตามข้อความที่กำหนด พร้อมปุ่มหลัก `"เข้าสู่ระบบ"` และปุ่มรอง `"สมัครสมาชิก"`; หน้า Login มีช่องอีเมล (`type=email`, `autocomplete=email`), รหัสผ่านพร้อมปุ่มแสดง/ซ่อน, ลิงก์ `"ลืมรหัสผ่าน?"`, ปุ่มเข้าสู่ระบบมีสถานะกำลังโหลด และแสดงข้อความผิดพลาดแบบ `aria-live`; หน้าสมัครสมาชิก 2 ขั้น (`1/2`, `2/2`) ตรวจรหัสผ่านและเบอร์โทรทันทีในขั้น 1 และกรอก OTP 6 หลัก (`inputmode=numeric`, `autocomplete=one-time-code`) พร้อมแสดงอีเมลแบบซ่อน ลิงก์แก้ไขอีเมล ปุ่มส่งรหัสซ้ำนับถอยหลัง 60 วินาที และคำแนะนำตรวจโฟลเดอร์ Spam ในขั้น 2; หน้าลืมรหัสผ่าน 2 ขั้นเมื่อสำเร็จพากลับหน้า Login พร้อมข้อความสำเร็จ; ลบการโชว์รหัส OTP, ปุ่มกรอกอัตโนมัติ, `uiState.otpSession.code`, กล่องบัญชีตัวอย่าง และโค้ด/CSS ของ Google ออกทั้งหมด; ทดสอบผ่าน `python tools/ui_audit.py` (0 ข้อผิดพลาด) และรองรับจอ 360px ปุ่ม/ช่องกรอกสูง ≥ 44px ทุกองค์ประกอบ
- [x] **ขั้น 8: เทสต์ (`tests/test_api_features.py`, `tests/test_browser_e2e.py`, `tests/test_member_otp.py`)**
  - **ไฟล์ที่แก้/เพิ่ม:** `tests/test_api_features.py`, `tests/test_browser_e2e.py`, `tests/test_member_otp.py` (ใหม่)
  - **ฟังก์ชันสำคัญ:** `test_06_customer_member_auth_otp_promos_history_and_owner_split_promos()`, `MemberOtpAndIsolationTestCase` (`test_01` ถึง `test_07`)
  - **หมายเหตุ:** ปรับ `test_06` ใน `tests/test_api_features.py` ให้ mock `email_service.send_mail` และดึงรหัส OTP จากเนื้อหาอีเมลที่จับได้แทนการอ่านจาก response; เพิ่ม `tests/test_member_otp.py` ครอบคลุมการตรวจว่าไม่มี `otp_code` ใน response/log, OTP หมดอายุ, กรอกผิดครบ 5 ครั้งถูกยกเลิก, ใช้ซ้ำไม่ได้, ใช้ข้าม purpose/อีเมลไม่ได้, ขอใหม่ยกเลิกรหัสเก่า, cooldown 60 วินาที, โควตา 5 ครั้ง/ชั่วโมง, IP rate limit 429 ที่ไม่เชื่อ `X-Forwarded-For`, ส่งเมลล้มเหลวแล้วลบ OTP ทันที, ยืนยันพร้อมกันหลายเธรดสำเร็จได้ครั้งเดียว, แฮชรหัสผ่านด้วย bcrypt และย้ายจาก `password` อัตโนมัติ, ล็อกอินด้วยชื่อไม่ได้, ข้อความล็อกอินผิดเหมือนกันทุกกรณี, ล็อกอินผิดซ้ำถูกล็อก, บัญชีตัวอย่างปิดเมื่อ `MEMBER_DEMO_ACCOUNTS=0`, `/member/google` ไม่มีอยู่แล้ว, ลืมรหัสผ่านตอบเหมือนกันทั้งมี/ไม่มีอีเมล, รีเซ็ตรหัสผ่านแล้วคุกกี้เดิมใช้ไม่ได้ และแยกบัญชี/เซสชันข้ามเครื่องและข้ามบทบาทอย่างสมบูรณ์; รันผ่านครบ 30 / 30 ข้อ
- [x] **ขั้น 9: เอกสาร (`README.md`, `PROGRESS.md`)**
  - **ไฟล์ที่แก้/เพิ่ม:** `README.md`, `PROGRESS.md`
  - **ฟังก์ชัน/หัวข้อสำคัญ:** หัวข้อ `"ระบบสมาชิกลูกค้าและ OTP"` ใน `README.md` และบันทึกความคืบหน้าครบทุกขั้นใน `PROGRESS.md`
  - **หมายเหตุ:** อธิบายวิธีสร้าง Gmail App Password, วิธีคัดลอก `.env.example` เป็น `.env` และกรอกค่า, วิธีทดสอบส่ง OTP จริง (สมัครสมาชิกและลืมรหัสผ่าน), ข้อควรรู้เรื่องอีเมลเข้าจดหมายขยะ (Spam) และข้อควรระวังห้ามนำ `.env`, `web_secret.key`, `*.db` ขึ้น Git
