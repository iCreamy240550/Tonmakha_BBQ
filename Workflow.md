# PROGRESS.md — แอปร้านต้นมะค่า แคมป์ปิ้งบาร์หมูกระทะ

> **ไฟล์นี้คือความจำของโปรเจกต์** ทุกแชทใหม่ให้ Claude อ่านไฟล์นี้ก่อนเริ่มงานเสมอ

## กติกาการทำงาน (ทุกแชทต้องทำตาม)
1. อ่าน PROGRESS.md ทั้งไฟล์ก่อนเริ่ม แล้วทำ **เฉพาะขั้นถัดไปที่ยังไม่เสร็จ** ทีละโฟลเดอร์ ห้ามข้ามขั้น
2. จบแต่ละขั้น ต้องอัปเดตไฟล์นี้: ติ๊ก `[x]`, เขียนรายการไฟล์ที่สร้าง, ฟังก์ชันสาธารณะ (ชื่อ + พารามิเตอร์ + ค่าที่คืน) และข้อควรรู้
3. ไม่แก้โฟลเดอร์ที่เสร็จแล้ว ยกเว้นแก้บั๊ก (และต้องจดไว้ในบันทึก)
4. **Python ล้วนเท่านั้น** ห้ามเขียน HTML/CSS เอง ห้ามใช้ Flet
5. ชื่อไฟล์/ฟังก์ชัน/ตัวแปรเป็นภาษาอังกฤษ ข้อความที่แสดงบนหน้าจอเป็นภาษาไทย
6. ทุกการเปลี่ยนแปลงสำคัญ (ยกเลิก, แก้ราคา, ยกเลิกรายการ ฯลฯ) ต้องเรียก `log_service`

## ภาพรวมโปรเจกต์
- ร้านหมูกระทะชั่งกิโล + เมนูอื่น ๆ
- **ฝั่ง PC (พนักงาน/เจ้าของ):** Python + CustomTkinter
- **ฝั่งมือถือลูกค้า:** Python + NiceGUI (สแกน QR เข้าเว็บ)
- **ฐานข้อมูล:** SQLite ไฟล์เดียว เปิดโหมด WAL ใช้ร่วมกัน 2 โปรเซส
- ไลบรารี: customtkinter, nicegui, qrcode, pillow, bcrypt
- ทั้งสองฝั่งใช้ `services/` ชุดเดียวกัน (UI ไม่แตะ SQL ตรง)
- การเข้าถึงมือถือจริง (Wi-Fi ร้าน / Tailscale Funnel) ยังไม่เลือก ช่วงพัฒนาทดสอบบนเครือข่ายเดียวกัน

## กติกาธุรกิจ
**สถานะโต๊ะ:** `ว่าง → รอยืนยัน(pending) → ใช้งาน(open) → รอชำระ → ปิด(closed)` และ `ยกเลิก(cancelled)` ได้จาก pending/open

**ลำดับสแกน:**
1. ร้านปิด → ขึ้น "ร้านปิดอยู่" สแกนเข้าไม่ได้
2. QR เป็นลิงก์ `/t/<เลขโต๊ะ>?k=<รหัสลับ>` รหัสผิด → "QR ไม่ถูกต้อง"
3. ผ่าน → สร้างรอบ (session) สถานะ pending จำเครื่องลูกค้าไว้
4. พนักงานกด **ยืนยัน** → open (สั่งได้) หรือ **ยกเลิก** → cancelled (สแกนมั่ว/ไม่มีลูกค้าจริง)
5. เช็คเอาท์แล้ว → closed ต้องสแกนใหม่ถึงเข้าได้
6. ลูกค้ากดยกเลิกคำขอเองได้ตอน pending

**แจ้งเตือนโต๊ะเงียบ (manual ไม่ตัดอัตโนมัติ):**
- กรณี A: pending นานเกิน N นาที (ค่าเริ่มต้น 5) ยังไม่มีใครยืนยัน
- กรณี B: open แต่ไม่มีรายการชั่งและไม่มีออเดอร์เกิน N นาที (ค่าเริ่มต้น 10)
- เช็คทุก 30 วินาที → แถบแดง + เสียงเตือนครั้งเดียวที่หน้าพนักงาน
- ปุ่ม: ยกเลิกโต๊ะ / ปล่อยไว้ (เตือนอีกใน 5 นาที) / ไปเช็คแล้ว — บันทึก log ทุกครั้ง
- เจ้าของปรับ N ที่หน้าตั้งค่า

**ราคา:** ชั่งหมู 1 กก. = 10 ขีด คิดราคา = น้ำหนัก × ราคา/กก. ที่เจ้าของตั้ง; ยอดสุทธิ = รวม − ส่วนลดโปร + ค่าบริการ + VAT (ตั้งค่าได้ เปิด/ปิดได้)

**เมนูหมด:** พนักงานกดเอง และสต๊อกเป็น 0 → หมดอัตโนมัติ; ลูกค้าได้ข้อความแจ้ง
**ยกเลิกรายการ:** ต้องใส่เหตุผล บันทึก log และแจ้งลูกค้า

**สิทธิ์:** ลูกค้า = เฉพาะโต๊ะที่สแกน (ไม่ต้องล็อกอิน) | พนักงาน = หน้าหน้าร้าน | เจ้าของ = ทุกอย่าง

## โครงสร้างไฟล์

```
tonmakha_bbq/
├── PROGRESS.md
├── main.py                    # เปิดแอป PC + สตาร์ทเว็บมือถือเป็น thread
├── run_web.py                 # เปิดเฉพาะเว็บลูกค้า
├── config.py
├── requirements.txt
├── database/   db.py, schema.py, seed.py
├── services/   auth, shop, table, qr, order, weigh, menu, stock, notice,
│               alert, pricing, promo, checkout, report, log, settings, backup  (*_service.py)
├── ui/
│   ├── app.py, theme.py, login_page.py, alert_center.py
│   ├── staff/  shop_control, tables_page, weigh_page, orders_page, kitchen_page, checkout_page
│   ├── owner/  dashboard_page, menu_page, stock_page, promo_page, tables_manage_page,
│   │           users_page, settings_page, report_page, log_page, backup_page
│   └── widgets/
├── web/
│   ├── server.py, session.py, components.py
│   └── pages/  enter, waiting, bill, order, notice, closed
├── assets/ (qr_codes/, fonts/, logo.png)
├── exports/
└── backups/
```

## ตารางฐานข้อมูล (17 ตาราง)
`users`, `settings`, `shop_status`, `tables` (มี secret_key), `table_sessions` (สถานะ, เวลาเริ่ม, last_activity, อุปกรณ์), `menu_categories`, `menu_items` (มีสถานะหมด, ประเภท: ชั่ง/ปกติ), `stock_items`, `stock_movements`, `orders`, `order_items` (เหตุผลยกเลิก), `weigh_entries`, `customer_notices`, `staff_alerts`, `promotions`, `bills`, `activity_log`

---

## ขั้นตอนการทำ (ทีละโฟลเดอร์)

- [x] **ขั้น 0 — โฟลเดอร์หลัก:** สร้างโครงโฟลเดอร์ว่างทั้งหมด, `config.py`, `requirements.txt`
- [x] **ขั้น 1 — `database/` ทั้งหมด:** `db.py` (WAL, helper), `schema.py` (17 ตาราง), `seed.py` (โต๊ะ, เมนู, เจ้าของ, พนักงานตัวอย่าง)
- [x] **ขั้น 2A — `services/` กลุ่มแกนหลัก:** log, settings, auth, shop, table, qr
- [x] **ขั้น 2B — `services/` กลุ่มรายการ:** menu, stock, weigh, order, notice
- [x] **ขั้น 2C — `services/` กลุ่มการเงิน/ระบบ:** pricing, promo, checkout, alert, report, backup
- [x] **ขั้น 3 — `ui/` ส่วนฐาน:** `theme.py`, `widgets/`, `login_page.py`, `app.py`, `alert_center.py`
- [x] **ขั้น 4 — `ui/staff/` ทั้งหมด:** shop_control, tables_page, weigh_page, orders_page, kitchen_page, checkout_page
- [x] **ขั้น 5 — `web/` ทั้งหมด:** server, session, components, pages/ทั้งหมด
- [x] **ขั้น 6 — `ui/owner/` ทั้งหมด:** dashboard, menu, stock, promo, tables_manage, users, settings, report, log, backup
- [x] **ขั้น 7 — ไฟล์หลัก:** `main.py`, `run_web.py` ต่อทุกส่วนเข้าด้วยกัน
- [x] **ขั้น 8 — ทดสอบและตกแต่ง:** ไล่ทดสอบตามลำดับสแกน, แจ้งเตือนโต๊ะเงียบ, เช็คเอาท์, รายงาน; แก้บั๊ก; เขียนวิธีรัน

---

## บันทึกความคืบหน้า (อัปเดตท้ายทุกขั้น)

### สถานะปัจจุบัน
เสร็จ **ทุกขั้น (0–8)** แล้ว — โค้ดครบ รอผู้ใช้ทดสอบบนเครื่องจริง (Windows + มือถือ) ตามรายการ "ต้องทดสอบกับของจริง" ด้านล่าง ; วิธีติดตั้ง/ใช้งานอยู่ที่ `README.md`

### ไฟล์ที่สร้างแล้ว
**ขั้น 0**
- โครงโฟลเดอร์ว่างทั้งหมดตามผังด้านบน (ไฟล์อื่นนอกจากที่ระบุด้านล่างยังเป็นไฟล์ว่าง 0 ไบต์)
- `config.py` — ค่าคงที่กลาง (เขียนเสร็จ)
- `requirements.txt` — customtkinter, nicegui, qrcode, pillow, bcrypt (มีอยู่แล้ว ไม่แก้)
- `assets/logo.png` — โลโก้ร้าน (1750x1750)
- `__init__.py` (ว่าง) ใน database, services, ui, ui/staff, ui/owner, ui/widgets, web, web/pages

**ขั้น 1**
- `database/db.py` — ตัวเชื่อม SQLite (WAL) + helper
- `database/schema.py` — สร้าง 17 ตาราง + index
- `database/seed.py` — ข้อมูลเริ่มต้น
- ทดสอบแล้ว (sandbox ใช้ bcrypt ปลอมเพราะลง bcrypt ไม่ได้): สร้าง 17 ตาราง, seed รันซ้ำไม่ซ้ำ, WAL เปิด, rollback ได้, FK/CHECK กันข้อมูลผิดได้

**ขั้น 2A** (`services/`)
- `log_service.py`, `settings_service.py`, `auth_service.py`, `shop_service.py`, `table_service.py`, `qr_service.py`
- ทดสอบแล้ว (ใช้ bcrypt/qrcode ปลอมใน sandbox): ตั้งค่า, ล็อกอิน/จัดการผู้ใช้, เปิด-ปิดร้าน, ลำดับสแกน 3 ขั้น, วงจรสถานะรอบทุกเส้นทาง, ยกเลิกโดยลูกค้า/พนักงาน, จัดการโต๊ะ, log

**ขั้น 2B** (`services/`)
- `notice_service.py`, `menu_service.py`, `stock_service.py`, `weigh_service.py`, `order_service.py`
- ทดสอบแล้ว: เมนู/แก้ราคา+log, ชั่ง (คำนวณราคา/ตัดสต๊อก/ยกเลิก), สั่งอาหาร (rollback เมื่อสต๊อกไม่พอ), ยกเลิกรายการ/ออเดอร์ (เหตุผล/คืนสต๊อก/แจ้งลูกค้า), สต๊อก 0 → เมนูหมดอัตโนมัติ + แจ้งทุกโต๊ะ, เติมสต๊อก → เมนูกลับมา, โต๊ะปิดแล้วทำรายการไม่ได้

**ขั้น 2C** (`services/`)
- `promo_service.py`, `pricing_service.py`, `checkout_service.py`, `alert_service.py`, `report_service.py`, `backup_service.py`
- ทดสอบแล้ว (152 เช็ค ใน sandbox ใช้ bcrypt ปลอม, DB ชั่วคราว): โปร (ตรวจค่า/ช่วงเวลา/ขั้นต่ำ), สูตรบิล (ส่วนลด+ค่าบริการ+VAT ปัดเศษ), เช็คเอาท์ครบวงจร (rollback เมื่อโปรใช้ไม่ได้, ออเดอร์ค้าง/force, ชำระซ้ำ, ปิดโต๊ะแล้วครัวไม่เห็นออเดอร์), แจ้งเตือนกรณี A/B (สร้าง/ไม่ซ้ำ/เสียงครั้งเดียว/ปล่อยไว้แล้วเตือนอีก/ไปเช็คแล้ว/ยกเลิกโต๊ะ/ปิดเอง), รายงาน (สรุป/รายวัน/รายชั่วโมง/ขายดี/ยกเลิก/แดชบอร์ด/CSV), สำรอง-กู้คืน (กัน path traversal, ไฟล์เสีย, ต้องปิดร้าน, ย้อนด้วย prerestore, auto รายวัน+prune)

**ขั้น 3** (`ui/`)
- `theme.py`, `login_page.py`, `alert_center.py`, `app.py`
- `widgets/`: `__init__.py`, `base_page.py`, `basic.py`, `dialogs.py`, `toast.py`, `data_table.py`
- ทดสอบแล้วใน sandbox (Python 3.12 + customtkinter 6.0 + xvfb, bcrypt/qrcode จริง, DB ชั่วคราว): ล็อกอินผิด/ถูก, เมนูตามสิทธิ์ (พนักงานไม่เห็นเมนูเจ้าของ และ navigate ไปหน้าเจ้าของไม่ได้), เปิดครบ 15 หน้า (หน้ายังว่าง = PlaceholderPage ไม่ล่ม), แถบแจ้งเตือน (โผล่/เสียงครั้งเดียว/ปล่อยไว้/ตื่นซ้ำ/ยกเลิกโต๊ะผ่านกล่องยืนยัน), dialogs (confirm/ask_reason), DataTable + auto refresh, ล็อกเอาท์ + ล็อกอินใหม่, ภาพหน้าจอตรวจแล้ว ฟอนต์ไทยแสดงถูก

**ขั้น 4** (`ui/staff/` + `ui/widgets/order_card.py`)
- `shop_control.py`, `tables_page.py`, `weigh_page.py`, `orders_page.py`, `kitchen_page.py`, `checkout_page.py`
- เพิ่ม `ui/widgets/order_card.py` (`OrderCard` ใช้ร่วมหน้าออเดอร์/ครัว) และ export ใน `ui/widgets/__init__.py`
- ทดสอบแล้วใน sandbox (xvfb, DB ชั่วคราว, ตรวจภาพหน้าจอ): สวิตช์ร้าน (เปิด/ปิด/ปิดตอนมีโต๊ะค้างต้องยืนยัน), ยืนยัน/ยกเลิกโต๊ะ, ชั่ง (5 ขีด=140 บาท, +ขีดลัด, ยกเลิกต้องมีเหตุผล, กรอกผิดไม่ล่ม), ครัว (เริ่มทำ), ออเดอร์ (ยกเลิกรายการ+เหตุผล, พนักงานสั่งให้ลูกค้าผ่านกล่อง), เช็คเอาท์ครบวงจร (เช็คบิล -> โปร 10% -> เงินสด/ทอน -> ชำระ -> ใบเสร็จ+.txt -> โต๊ะ closed)
- **แก้บั๊กขั้น 3:** `PageHeader` — `subtitle=''` เดิมไม่สร้างช่อง subtitle ทำให้ `set_subtitle()` ไม่ทำงาน (แก้เป็น `is not None`) และกรอบ `.right` ว่างสูง 200px (ตั้ง height=1)

**ขั้น 5** (`web/`)
- `session.py` (ตรรกะล้วน ไม่ import nicegui), `components.py`, `server.py`
- `pages/`: `enter.py`, `waiting.py`, `order.py`, `bill.py`, `notice.py`, `closed.py`
- ไม่แก้ไฟล์ขั้นก่อนหน้า ; สร้างไฟล์ `web_secret.key` ที่รากโปรเจกต์ตอนรันเว็บครั้งแรก (รหัสเซ็น storage ของ NiceGUI ห้ามแจก/ห้ามใส่ใน zip/git)
- ทดสอบแล้วใน sandbox (70 เช็ค ผ่านหมด): **ลง nicegui/bcrypt/qrcode ใน sandbox ไม่ได้ (ไม่มีเน็ต)** จึงใช้ตัวจำลอง `nicegui` + `bcrypt` ปลอมที่บันทึก element ที่วาด แล้วไล่ครบวงจร: ร้านปิด → QR ผิด/โต๊ะไม่มี → สแกนถูก (สร้าง pending, เก็บ device) → สแกนซ้ำเครื่องเดิมได้รอบเดิม → ลูกค้ายกเลิกคำขอเอง → สแกนใหม่ → พนักงานยืนยัน → เมนู/ตะกร้า/สั่ง (ตัดสต๊อก, เก็บตะกร้าข้ามรีโหลด) → เมนูหมดระหว่างสั่ง (toast + เอาออกจากตะกร้า + สั่งไม่ผ่าน rollback) → พนักงานชั่ง/ส่งข้อความ/ยกเลิกรายการ แสดงในหน้าลูกค้า → เครื่องอื่นเข้า/สั่ง/ยกเลิกรอบของเราไม่ได้ → เช็คบิล (สั่งเพิ่มไม่ได้) → ชำระ (ใบเสร็จ, หยุดโพล) → สแกนใหม่ได้รอบใหม่ → ยืนยันว่าการแค่เปิดดูไม่ขยับ `last_activity`
- **ยังไม่เคยรันกับ NiceGUI จริง** — หน้าตา/ฟอนต์/การเลื่อนบนมือถือจริง และ `ui.run` ใน thread ยังต้องให้ผู้ใช้ลองหลัง `pip install -r requirements.txt`

**ขั้น 6** (`ui/owner/`)
- `_common.py` (ตัวช่วยกลาง), `dashboard_page.py`, `menu_page.py`, `stock_page.py`, `promo_page.py`, `tables_manage_page.py`, `users_page.py`, `settings_page.py`, `report_page.py`, `log_page.py`, `backup_page.py`
- ไม่แก้ไฟล์ขั้นก่อนหน้า (เพิ่มเฉพาะ `ui/owner/_common.py` ซึ่งไม่อยู่ในผังเดิม)
- ทดสอบแล้ว 46 เช็ค ใน sandbox ด้วย **customtkinter/tkinter จำลอง** (sandbox ครั้งนี้ไม่มี tkinter และลงเพิ่มไม่ได้) + DB ชั่วคราว + bcrypt/qrcode ปลอม: ทุกหน้าสร้าง/โหลดได้, เพิ่ม-แก้-ซ่อนเมนู/หมวด/สต๊อก/โปร/โต๊ะ/ผู้ใช้, ตรวจช่องกรอกผิด, ตั้งค่าแบบ all-or-nothing, รายงาน (บิล/ยกเลิก/CSV), log แบ่งหน้า+กรอง, สำรอง/กู้คืนครบวงจร ; **ยังไม่เคยเห็นหน้าตาจริง (เลย์เอาต์/ฟอนต์/ขนาดตาราง) — ผู้ใช้ต้องเปิดดูบน Windows**

**ขั้น 7** (`main.py`, `run_web.py`, `README.md`)
- `main.py`: `prepare_environment() -> {'seeded','backup'}` (สร้างโฟลเดอร์+ตาราง, seed ถ้ายังไม่มีผู้ใช้, `auto_backup()` ไม่ล้มแอปถ้าพัง) · `start_web(mode='thread'|'process'|'off') -> WebHandle(.mode,.error,.running,.stop())` (ไม่ throw ; thread ตายเก็บข้อความใน `.error`) · `main(argv)` พร้อม `--web` ; หลังเปิดหน้าต่าง 4 วินาที ถ้าเว็บไม่ทำงานจะขึ้นกล่องแจ้งพนักงาน ; ปิดหน้าต่างแล้วหยุดโปรเซสเว็บ (โหมด process)
- `run_web.py [--host --port]`: เปิดเฉพาะเว็บ (ไม่มี nicegui = แจ้งให้ pip install แล้วออกด้วยรหัส 1)
- เพิ่ม `ui/owner/_common.detect_lan_ip()` + แถบแสดง IP/ปุ่ม "ใช้ค่านี้" ในหน้าตั้งค่า (ช่วยตั้ง public_base_url)

**ขั้น 8** (ตรวจสอบ ไม่พบบั๊กในขั้น 0–5 ; ไม่ได้แก้ไฟล์ขั้นก่อนหน้า)
- สถิติเช็ค (sandbox ไม่มี tkinter/nicegui/bcrypt/qrcode จริง จึงใช้ตัวจำลอง): import ครบ 60 โมดูล+หาชื่อที่ไม่ได้กำหนด = 0 ปัญหา ; App (ล็อกอินผิด/ถูก, เปิดครบ 15 หน้าไม่มี Placeholder, พนักงานเข้าหน้าเจ้าของไม่ได้) ; main/start_web/run_web ; หน้าเจ้าของ 46 เช็ค ; e2e 13 กลุ่ม: ลำดับสแกน, แจ้งเตือน A/B (เวลาจำลอง), สั่ง/สต๊อก/หมดอัตโนมัติ/ยกเลิกรายการ, เช็คเอาท์+สูตรบิลเทียบการคำนวณอิสระ, รายงานตรงกับบิล, ปิดร้านขณะมีโต๊ะค้าง, ลูกค้า 4 เครื่อง×15 ออเดอร์ + พนักงานโพล 2 เธรดพร้อมกัน ไม่มี database is locked

### ฟังก์ชันสาธารณะของแต่ละโมดูล
(เขียนเพิ่มหลังทำแต่ละขั้นเสร็จ: ชื่อฟังก์ชัน, พารามิเตอร์, ค่าที่คืน)

**config.py** (ค่าคงที่ ไม่มีฟังก์ชัน — import เป็น `import config`)
- พาธ: `BASE_DIR, DB_PATH (tonmakha.db), ASSETS_DIR, LOGO_PATH, FONTS_DIR, QR_DIR, EXPORTS_DIR, BACKUPS_DIR`
- เว็บ: `WEB_HOST, WEB_PORT (8080), PUBLIC_BASE_URL, QR_PATH_TEMPLATE ("/t/{table_no}?k={secret_key}"), SECRET_KEY_LENGTH (16)`
- DB: `DB_TIMEOUT_SECONDS`
- สถานะ (ค่าในฐานข้อมูลเป็นอังกฤษ): `TABLE_STATUS_FREE="free", SESSION_PENDING="pending", SESSION_OPEN="open", SESSION_AWAITING_PAYMENT="awaiting_payment", SESSION_CLOSED="closed", SESSION_CANCELLED="cancelled"` และ `SESSION_STATUS_TH` (dict แปลเป็นไทย)
- ประเภทเมนู: `MENU_TYPE_WEIGHED="weighed", MENU_TYPE_NORMAL="normal"`; บทบาท: `ROLE_STAFF="staff", ROLE_OWNER="owner"`
- ราคา: `GRAMS_PER_KG=1000, KHEED_PER_KG=10`
- แจ้งเตือน: `ALERT_CHECK_INTERVAL_SECONDS=30`
- `DEFAULT_SETTINGS` (dict ใช้ seed ตาราง settings): alert_pending_minutes=5, alert_idle_open_minutes=10, alert_snooze_minutes=5, service_charge_enabled=0, service_charge_percent=10, vat_enabled=0, vat_percent=7, public_base_url
- อื่น ๆ: `MIN_PASSWORD_LENGTH=4, DEFAULT_TABLE_COUNT=10`

**database/db.py** (`from database import db`) — เฉพาะ services เรียกใช้ UI ห้ามแตะ
- `now_str() -> str` เวลาเครื่อง 'YYYY-MM-DD HH:MM:SS'
- `parse_time(text: str) -> datetime`
- `get_connection() -> sqlite3.Connection` (WAL, foreign_keys, Row; ผู้เรียกต้อง close เอง)
- `transaction()` context manager → yield conn; สำเร็จ commit / error rollback / ปิดให้เอง (ใช้ BEGIN IMMEDIATE)
- `query_all(sql, params=(), conn=None) -> list[Row]`
- `query_one(sql, params=(), conn=None) -> Row | None`
- `execute(sql, params=(), conn=None) -> int` (lastrowid; ไม่ส่ง conn = commit ให้เอง)
- `execute_rowcount(sql, params=(), conn=None) -> int` (จำนวนแถวที่ถูกแก้)
- `executemany(sql, rows, conn=None) -> None`
- ทำหลายคำสั่งพร้อมกัน → `with db.transaction() as conn:` แล้วส่ง `conn=conn` ให้ทุก helper

**database/schema.py** (`python -m database.schema [--reset]`)
- `create_all() -> None` สร้างตาราง/index ที่ยังไม่มี + แถว shop_status (ปิดร้านเป็นค่าเริ่มต้น); รันซ้ำได้
- `drop_all() -> None` ลบทุกตาราง (ใช้ตอนพัฒนา)
- `list_tables() -> list[str]`
- ค่าคงที่: `TABLE_NAMES` (17 ชื่อ), `TABLES_SQL`, `INDEXES_SQL`, `SCHEMA_VERSION=1`

**database/seed.py** (`python -m database.seed`)
- `seed_all() -> dict[str,int]` สร้างตาราง + ใส่ข้อมูลเริ่มต้นใน transaction เดียว (รันซ้ำปลอดภัย: ข้ามส่วนที่มีข้อมูลแล้ว)
- `hash_password(password: str) -> str` (bcrypt) — auth_service ตรวจด้วย `bcrypt.checkpw`
- `make_secret_key() -> str` (ยาว SECRET_KEY_LENGTH)
- `seed_settings/seed_users/seed_tables/seed_stock/seed_menu(conn) -> int`
- บัญชีตัวอย่าง: `owner/owner1234` (owner), `staff1/staff1234` (staff) — ต้องเปลี่ยนก่อนใช้งานจริง

**กติการ่วมของ services/** : คืน dict/list[dict] (ไม่คืน Row) ; ผิดกติกา -> `raise ValueError("ข้อความไทย")` ให้ UI จับแล้วแสดงตรง ๆ ; ทุกฟังก์ชันที่เปลี่ยนข้อมูลสำคัญ log ให้เอง ; ฟังก์ชันที่รับ `conn=None` ใช้ใน transaction ของผู้เรียกได้

**services/log_service.py**
- `log_action(action, detail=None, user_id=None, actor=None, ref_type=None, ref_id=None, conn=None) -> int` (actor = ชื่อข้อความ เช่น 'ลูกค้า'/'ระบบ' เมื่อไม่ใช่ user)
- `get_logs(limit=200, offset=0, action=None, user_id=None, date_from=None, date_to=None) -> list[dict]` (ใหม่สุดก่อน มี user_name; วันที่ 'YYYY-MM-DD')
- `count_logs(action=None, user_id=None, date_from=None, date_to=None) -> int`

**services/settings_service.py**
- `get_setting(key, default=None) -> str|None` (ไม่มีใน DB ใช้ config.DEFAULT_SETTINGS)
- `get_int(key, default=0)`, `get_float(key, default=0.0)`, `get_bool(key, default=False)`
- `get_all() -> dict[str,str]`
- `set_setting(key, value, user_id=None, conn=None) -> None` (bool -> '1'/'0'; log เมื่อค่าเปลี่ยนจริง)
- `set_many(values: dict, user_id=None) -> None` (transaction เดียว)

**services/auth_service.py** (user dict: id, username, display_name, role, active, created_at)
- `login(username, password) -> dict|None` (log สำเร็จ/ล้มเหลว; บัญชีปิดใช้ = None)
- `hash_password(password) -> str`, `verify_password(password, password_hash) -> bool`
- `get_user(user_id) -> dict|None`, `list_users(include_inactive=True) -> list[dict]`
- `is_owner(user) -> bool`, `has_permission(user, required_role) -> bool` (owner ทำได้ทุกอย่าง)
- `create_user(username, password, display_name, role, by_user_id=None) -> dict`
- `update_user(user_id, display_name=None, role=None, active=None, by_user_id=None) -> dict` (ห้ามทำให้ไม่เหลือ owner ที่ใช้งานได้)
- `change_password(user_id, new_password, by_user_id=None) -> None`

**services/shop_service.py**
- `get_status() -> {'is_open','changed_at','changed_by'}`, `is_open() -> bool`, `active_session_count() -> int`
- `open_shop(user_id=None)`, `close_shop(user_id=None, force=False)` (ValueError ถ้ามีโต๊ะค้างและไม่ force)

**services/table_service.py** (ค่าคงที่ `ACTIVE_STATUSES` = pending/open/awaiting_payment)
- จัดการโต๊ะ: `get_table(table_id)`, `get_table_by_no(table_no)`, `list_tables(include_inactive=False)`, `add_table(table_no, name=None, user_id=None)`, `update_table(table_id, name=None, active=None, user_id=None)`, `regenerate_secret(table_id, user_id=None)` -> dict
- อ่านรอบ: `get_session(session_id)`, `get_active_session(table_id)` (None = โต๊ะว่าง), `is_session_active(session_id) -> bool`, `list_pending_sessions() -> list[dict]` (+table_no, table_name), `list_tables_with_status() -> list[dict]` (โต๊ะ ไม่มี secret_key + status('free'|สถานะรอบ), status_th, session_id, started_at, last_activity)
- เปลี่ยนสถานะ (คืน dict รอบใหม่): `start_session(table_id, device_id=None, device_info=None)`, `confirm_session(session_id, user_id)` pending→open, `cancel_session(session_id, cancelled_by='staff'|'customer', user_id=None, reason=None)`, `mark_awaiting_payment(session_id, user_id=None)` open→awaiting_payment, `close_session(session_id, user_id=None, conn=None)` awaiting_payment→closed
- `touch_session(session_id, conn=None) -> None` อัปเดต last_activity (order/weigh เรียกให้แล้ว)

**services/notice_service.py** (kind: 'sold_out','item_cancelled','staff_message','info')
- `add_notice(session_id, kind, message, conn=None) -> int`
- `broadcast_open_sessions(kind, message, conn=None) -> int` (ส่งถึงทุกรอบสถานะ open)
- `send_message(session_id, message, user_id=None) -> int` (พนักงานพิมพ์ส่ง, log)
- `list_notices(session_id, limit=50)`, `list_unread(session_id)` (เก่าสุดก่อน), `unread_count(session_id) -> int`
- `mark_read(notice_id)`, `mark_all_read(session_id) -> int`

**services/menu_service.py** (item dict: id, category_id, name, item_type, price, is_sold_out(bool), stock_item_id, sort_order, active(bool))
- หมวด: `list_categories(include_inactive=False)`, `add_category(name, sort_order=None, user_id=None)`, `update_category(category_id, name=None, sort_order=None, active=None, user_id=None)`
- เมนู: `get_item(item_id, conn=None)`, `list_items(category_id=None, include_inactive=False)` (+category_name), `add_item(category_id, name, item_type, price, stock_item_id=None, sort_order=None, user_id=None)`, `update_item(item_id, name=, price=, category_id=, stock_item_id=, active=, sort_order=, user_id=None)` (ส่งเฉพาะที่จะแก้; `stock_item_id=None` = เลิกผูก; แก้ราคา log 'menu_price_change')
- `get_menu_for_customer() -> [{'id','name','items':[{'id','name','item_type','price','is_sold_out'}]}]`
- `set_sold_out(item_id, sold_out, user_id=None, auto=False, conn=None) -> bool` (True = สถานะเปลี่ยนจริง; เปลี่ยนเป็นหมด → แจ้งทุกโต๊ะที่ open)

**services/stock_service.py** (หน่วยเนื้อสัตว์ = 'กก.' ทศนิยม; ปริมาณไม่ติดลบ)
- `get_item(id)`, `list_items(include_inactive=False)`, `list_low_stock()` (dict มี is_low = quantity <= min_quantity)
- `add_item(name, unit, quantity=0, min_quantity=0, user_id=None)`, `update_item(stock_item_id, name=None, unit=None, min_quantity=None, active=None, user_id=None)`
- `adjust(stock_item_id, change_qty, reason, user_id=None, ref_type=None, ref_id=None, conn=None) -> float` (ใหม่; ถึง 0 → เมนูที่ผูกหมดอัตโนมัติ ไม่เปิดคืน)
- `restock(stock_item_id, quantity, user_id=None, reason='เติมสต๊อก', ref_type=None, ref_id=None, conn=None) -> float` (จาก 0 → เมนูกลับมามีขาย)
- `deduct_for_menu_item(menu_item_id, quantity, reason, user_id=None, ref_type=None, ref_id=None, strict=True, conn=None)` (strict=True สต๊อกไม่พอ ValueError; ไม่ผูกสต๊อก = ข้าม), `return_to_stock(menu_item_id, quantity, reason, user_id=None, ref_type=None, ref_id=None, conn=None)`
- `get_movements(stock_item_id=None, limit=200) -> list[dict]` (+item_name, user_name)

**services/weigh_service.py** (entry dict: id, session_id, menu_item_id, name_snapshot, weight_grams, weight_kheed, price_per_kg, amount, status 'active'|'cancelled', cancel_reason, created_by, created_at)
- `kheed_to_grams(kheed) -> int`, `grams_to_kheed(grams) -> float`, `calc_amount(weight_grams, price_per_kg) -> float` (ปัด 2 ตำแหน่ง HALF_UP), ค่าคงที่ `MAX_WEIGHT_GRAMS=50000`
- `get_entry(entry_id)`, `list_entries(session_id, include_cancelled=False)`, `session_total(session_id) -> float`
- `add_entry(session_id, menu_item_id, weight_grams: int, user_id) -> dict` (เฉพาะรอบ open, เมนูชั่ง, ไม่หมด)
- `cancel_entry(entry_id, reason, user_id) -> dict` (เหตุผลบังคับ; open/awaiting_payment; คืนสต๊อก+แจ้งลูกค้า+log)

**services/order_service.py** (order dict: id, session_id, status 'new'|'preparing'|'served'|'cancelled', status_th, note, created_by(None=ลูกค้า), created_at, items:[{id, menu_item_id, name_snapshot, unit_price, quantity, line_total, status 'active'|'served'|'cancelled', cancel_reason,...}])
- `get_order(order_id, include_cancelled=False)`, `list_orders(session_id, include_cancelled=False)`, `list_active_orders()` (new/preparing ทุกโต๊ะ + table_no, table_name — หน้าครัว), `session_total(session_id) -> float`
- `create_order(session_id, items=[{'menu_item_id','quantity'}], note=None, user_id=None) -> dict` (user_id=None = ลูกค้า; เฉพาะรอบ open + เมนู normal; ล้มเหลว = rollback ทั้งออเดอร์)
- `set_order_status(order_id, new_status, user_id=None)` (new→preparing→served, new→served)
- `cancel_item(order_item_id, reason, user_id)`, `cancel_order(order_id, reason, user_id)` (เหตุผลบังคับ; คืนสต๊อก+แจ้งลูกค้า+log; ยกเลิกครบ → ออเดอร์ cancelled)

**services/qr_service.py**
- `build_url(table_no, secret_key) -> str`, `get_table_url(table_id) -> str`
- `verify_key(table_no, key) -> dict|None`
- `generate_qr_image(table_id, out_dir=None) -> Path` (assets/qr_codes/table_<เลข>.png; import qrcode ตอนเรียก), `generate_all_qr(out_dir=None) -> list[Path]`
- `resolve_scan(table_no, key, device_id, device_info=None) -> {'ok','code','message','table','session'}` code = 'shop_closed'|'invalid_qr'|'table_busy'|'ok' (table ไม่มี secret_key) — **หน้าเว็บ enter.py เรียกฟังก์ชันนี้ฟังก์ชันเดียว**

**services/promo_service.py** (promo dict: id, name, promo_type 'percent'|'fixed', promo_type_th, value, min_amount, start_at, end_at, active(bool), label เช่น '10%'/'50 บาท')
- `get_promo(promo_id, conn=None)`, `list_promos(include_inactive=True)` (ใหม่สุดก่อน)
- `is_in_period(promo, at=None) -> bool`, `calc_discount(promo, subtotal) -> float` (ปัด 2 ตำแหน่ง, ไม่เกินยอดรวม, ไม่เช็คเงื่อนไข)
- `list_available(subtotal=None, at=None) -> list[dict]` (โปรที่เลือกได้ตอนนี้; ถ้าส่ง subtotal กรองยอดขั้นต่ำและมี `discount`) — ใช้เติม dropdown หน้าเช็คเอาท์
- `check_applicable(promo_id, subtotal, at=None, conn=None) -> dict` (ValueError ไทย: ไม่พบ/ปิดใช้งาน/นอกช่วงเวลา/ยอดไม่ถึง)
- `add_promo(name, promo_type, value, min_amount=0, start_at=None, end_at=None, user_id=None) -> dict` (วันที่ 'YYYY-MM-DD' หรือมีเวลา; วันเริ่ม=00:00:00 วันสิ้นสุด=23:59:59)
- `update_promo(promo_id, name=, promo_type=, value=, min_amount=, start_at=, end_at=, active=, user_id=None) -> dict` (ส่งเฉพาะที่จะแก้; `start_at/end_at=''` = ล้าง, None = ไม่แก้) — ไม่มีลบโปร ใช้ `active=False`

**services/pricing_service.py** (ไม่เขียน DB ไม่ log)
- `compute_totals(subtotal, discount=0, service_percent=0, vat_percent=0) -> {'subtotal','discount','after_discount','service_charge','vat','total'}` (คำนวณล้วน)
- `get_rates() -> {'service_charge_enabled','service_charge_percent','vat_enabled','vat_percent'}` (percent=0 เมื่อปิด)
- `calc_bill(session_id, promo_id=None, conn=None) -> dict`: session_id, weigh_total, order_total, subtotal, promo_id, promo_name, discount, after_discount, service_charge_enabled/percent, service_charge, vat_enabled/percent, vat, total (ใช้ได้ทุกสถานะรอบ)

**services/checkout_service.py** (`PAYMENT_METHODS_TH = {'cash':'เงินสด','transfer':'โอน/พร้อมเพย์','card':'บัตร'}`)
- `start_checkout(session_id, user_id=None) -> dict` open→awaiting_payment แล้วคืน `preview` (ValueError ถ้าไม่ใช่ open / ไม่มีรายการ)
- `preview(session_id, promo_id=None) -> dict` = calc_bill + table_no, table_name, status, status_th, weigh_entries, orders, unserved_orders ; รอบ closed คืนบิลที่บันทึก (get_bill_detail) ; pending/cancelled → ValueError
- `pay(session_id, payment_method, user_id, promo_id=None, force=False) -> dict` บันทึกบิล + `table_service.close_session` ใน transaction เดียว ; ออเดอร์ new/preparing ค้างต้อง `force=True` (จะตั้งเป็น served) ; คืน get_bill_detail
- `get_bill(session_id) -> dict|None` (ฟิลด์ bills + payment_method_th, table_no, table_name, promo_name, cashier_name), `get_bill_by_id(bill_id)`, `get_bill_detail(session_id)` (+ weigh_entries, orders, after_discount)
- `list_bills(date_from=None, date_to=None, limit=100, offset=0) -> list[dict]` (ใหม่สุดก่อน ตามเวลาชำระ)

**services/alert_service.py** (alert dict: id, session_id, table_id, table_no, table_name, kind 'pending_timeout'|'idle_open', kind_th, message, status 'active'|'snoozed'|'resolved', sound_played(bool), snooze_until, resolution, created_at, resolved_at, session_status)
- `check_alerts(now=None) -> {'new':[...], 'woken':[...], 'cleared':[...]}` **UI เรียกทุก `config.ALERT_CHECK_INTERVAL_SECONDS`** (`now` ใช้ทดสอบ)
- `list_active_alerts() -> list[dict]` (status 'active' = แถบแดง), `list_recent_alerts(limit=50)`, `active_count() -> int`, `get_alert(alert_id)`
- `pop_sound_alerts() -> list[dict]` คืนแจ้งเตือน active ที่ยังไม่เคยเล่นเสียงและมาร์กว่าเล่นแล้ว (UI เล่นเสียงครั้งเดียวถ้าลิสต์ไม่ว่าง)
- ปุ่มพนักงาน (คืน dict แจ้งเตือนหลังเปลี่ยน; ValueError ถ้าไม่พบ/จัดการแล้ว): `cancel_table(alert_id, user_id)`, `snooze(alert_id, user_id)`, `mark_checked(alert_id, user_id)`

**services/report_service.py** (วันที่ 'YYYY-MM-DD' รวมทั้งสองวัน; ไม่ส่ง = วันนี้; ผิดรูปแบบ/กลับด้าน → ValueError)
- `sales_summary(date_from=None, date_to=None) -> {'date_from','date_to','bill_count','subtotal','discount','service_charge','vat','total','avg_per_bill','by_payment':{method:{'method_th','count','total'}}}`
- `daily_sales(...) -> [{'date','bill_count','total'}]` (ครบทุกวัน), `hourly_sales(...) -> 24 แถว [{'hour','bill_count','total'}]`
- `top_items(date_from=None, date_to=None, limit=10) -> [{'menu_item_id','name','item_type','quantity','unit','amount'}]` (ชั่ง=กก., ปกติ=ชิ้น; เรียงตามยอดเงิน)
- `cancellations(...) -> {'items':[{'kind':'order_item'|'weigh_entry','table_no','name','quantity','amount','reason','by','at'}], 'cancelled_sessions':[{'table_no','cancelled_by','reason','at'}], 'item_count','item_amount'}`
- `today_overview() -> dict` สำหรับแดชบอร์ด: sales (วันนี้), tables_total, tables_in_use, tables_pending, tables_awaiting_payment, low_stock, low_stock_count, active_alerts, cancelled_items_today, cancelled_sessions_today
- `export_sales_csv(date_from=None, date_to=None, out_dir=None) -> Path` (exports/sales_<จาก>_<ถึง>.csv, utf-8-sig)

**services/backup_service.py** (backup dict: filename, path(Path), kind 'manual'|'auto'|'prerestore', kind_th, size_bytes, created_at)
- `create_backup(user_id=None, kind='manual') -> dict`, `list_backups(kind=None) -> list[dict]` (ใหม่สุดก่อน), `delete_backup(filename, user_id=None)`
- `restore_backup(filename, user_id=None) -> dict` (ไฟล์ prerestore ที่สำรองก่อนกู้ + `active_sessions`) — ต้องปิดร้านและไม่มีโต๊ะค้าง ; หลังกู้คืนร้านเป็น 'ปิด' ; **ควรให้ผู้ใช้รีสตาร์ตแอป**
- `auto_backup(keep=14) -> dict|None` (สำรองอัตโนมัติวันละครั้ง คืน None ถ้าวันนี้มีแล้ว) , `prune_auto_backups(keep=14) -> int`
- รับ `filename` เป็นชื่อไฟล์เปล่า ๆ เท่านั้น (รูปแบบ `tonmakha_<ชนิด>_<YYYYmmdd>_<HHMMSS>.db`)

**ui/theme.py** (`from ui.theme import COLORS, font, money, ...`) — `font()` ต้องเรียกหลังสร้างหน้าต่างหลักแล้ว
- `COLORS` (dict สี: bg, card, card_border, sidebar, primary, success, danger, warning, info, neutral, text, text_muted, input_bg, input_border, row_alt, row_hover ...), `STATUS_COLORS` (สถานะรอบ/โต๊ะ -> สี), `ORDER_STATUS_COLORS` (new/preparing/served/cancelled)
- `init_theme()`, `font(size=14, bold=False) -> CTkFont`, `font_family() -> str` (Leelawadee UI > Tahoma > ... > ฟอนต์ระบบ)
- `money(v) -> '1,234.50'`, `baht(v) -> '1,234.50 บาท'`, `weight_text(grams) -> '1.5 กก. (15 ขีด)' / '3 ขีด'`
- `fmt_time(text) -> 'HH:MM'`, `fmt_datetime(text) -> 'dd/mm/YYYY HH:MM'`, `minutes_since(text)`, `duration_text(text) -> '5 นาที'/'1 ชม. 20 นาที'`, `status_color(status)`, `status_text(status)`

**ui/widgets/** (`from ui.widgets import ...`)
- `BasePage` — คลาสแม่ของทุกหน้า: override `build()` (สร้าง widget ครั้งเดียว), `on_show(**params)` (ค่าเริ่มต้นเรียก `refresh()`), `refresh()`, `on_hide()`; ตั้ง `title`, `auto_refresh_ms` (None = ไม่รีเฟรชเอง); ตัวช่วย `self.app`, `self.user`, `self.user_id`, `self.toast(text, kind)`, `self.call(fn, *args, success=None, **kw) -> (ok, result)` (จับ ValueError แสดง toast ไทยให้เอง), `self.reload()`
- `Card`, `ActionButton(master, text, command, variant='primary|success|danger|info|neutral|ghost', height=40, width=0, size=15)` (+`set_variant`), `StatusBadge(master, text, color)` (+`set(text,color)`), `PageHeader(master, title, subtitle)` (+`.right` ช่องวางปุ่ม, `set_subtitle`), `LabeledEntry(master, label, show=None, placeholder='', width=0)` (+`get/set/clear/.entry`), `StatTile(master, title, value, color)` (+`set(value, hint)`), `EmptyState`
- `DataTable(master, columns, on_select=None, row_height=40, empty_text, font_size)` — columns = list ของ dict `{key, title, weight, min_width, anchor, format(value,row), widget(parent,row), wrap}` ; `set_rows(list[dict])` (คงแถวที่เลือกถ้า `id` เดิมยังอยู่), `.selected`, `.clear_selection()` ; แสดงสูงสุด 300 แถว
- Dialog (modal): `confirm(parent, message, title, confirm_text, cancel_text, danger=False) -> bool`, `ask_text(parent, prompt, title, required=True, initial='', multiline=False, confirm_text, danger=False) -> str|None`, `ask_reason(parent, prompt='เหตุผล', ...) -> str|None` (บังคับกรอก — ใช้กับยกเลิกรายการ/โต๊ะ), `show_info`, `show_error`, `BaseDialog` (สืบทอดทำฟอร์มเอง: ใส่ widget ใน `self.body`, `add_buttons(confirm_text, cancel_text, variant, on_confirm)`, `close(result)`, `show() -> result`)
- `show_toast(widget, text, kind='info|success|error|warning')`

**ui/login_page.py** — `LoginPage(master, on_success)` เรียก `on_success(user_dict)`

**ui/alert_center.py** — `AlertCenter(master, user_provider, on_change=None, show_fn=None, hide_fn=None)`: `start()`, `stop()`, `refresh_view(notify=False)`, `.count` ; `play_alert_sound(widget)` ; **ที่เดียวที่เรียก `alert_service.check_alerts/pop_sound_alerts`** (App สร้างให้อัตโนมัติ หน้าอื่นห้ามสร้างเอง)

**ui/app.py** — `App()` (`.mainloop()`), `NAV_ITEMS` / `NavItem(key, label, role, module, group)` ลงทะเบียนหน้า (คีย์: tables, weigh, orders, kitchen, checkout | dashboard, menu, stock, promo, tables_manage, report, users, settings, log, backup)
- ทุกโมดูลหน้า **ต้องมีคลาส `Page(BasePage)`** — App โหลดแบบ lazy; ไม่มีคลาส/โหลดพัง = `PlaceholderPage` ไม่ล่ม
- `app.user`, `app.navigate(key, **params)` (เช็คสิทธิ์ให้; params ไป `Page.on_show(**params)` เช่น `app.navigate('weigh', session_id=12)`), `app.toast(text, kind)`, `app.alert_center.refresh_view()` (เรียกหลังพนักงานเปลี่ยนสถานะโต๊ะ), `app.refresh_shop_status()`, `app.logout()`
- แถบบนมีช่องสวิตช์ร้าน: ถ้า `ui/staff/shop_control.py` มี **`ShopControl(master, app)`** (CTkFrame ที่มี `refresh()`) จะนำมาใช้ (App เรียก `refresh()` ทุก 15 วินาทีและเมื่อสั่ง `refresh_shop_status()`) ; ไม่มี = ป้ายสถานะร้านอย่างเดียว

**ui/staff/** (ทุกหน้า = `Page(BasePage)`; คีย์นำทางตาม NAV_ITEMS)
- `shop_control.ShopControl(master, app)` — ป้าย+ปุ่มเปิด/ปิดร้านบนแถบบน; `refresh()`, `toggle()`
- `tables_page` (key `tables`, รีเฟรช 4 วิ): การ์ดโต๊ะ; ปุ่มตามสถานะ — pending: ยืนยัน/ยกเลิก ; open: ชั่ง/ออเดอร์/เช็คบิล/ส่งข้อความ/ยกเลิกโต๊ะ(ต้องใส่เหตุผล) ; awaiting_payment: ไปชำระเงิน ; เมธอด `confirm_session(session_id)`, `cancel_session(t)`, `send_message(t)`
- `weigh_page` (key `weigh`, `on_show(session_id=None)`): เลือกโต๊ะ (เฉพาะ open) + เมนู weighed + กรอกขีด/กรัม ; `save()`, `cancel_entry(entry)`
- `orders_page` (key `orders`, `on_show(session_id=None)`): กรองโต๊ะ/ยังไม่เสิร์ฟ-ทั้งหมด ; `set_status`, `cancel_item`, `cancel_order`, `open_create_dialog()` ; `CreateOrderDialog` (พนักงานสั่งเมนู normal ให้โต๊ะ -> `create_order(user_id=พนักงาน)`)
- `kitchen_page` (key `kitchen`, รีเฟรช 3 วิ): 2 คอลัมน์ ใหม่/กำลังทำ ตัวใหญ่ ; ออเดอร์ใหม่เข้า = เสียงเตือน (`play_alert_sound`)
- `checkout_page` (key `checkout`, `on_show(session_id=None)`): `start_checkout()` (ถามยืนยัน), `pay()` (ถามยืนยัน + ถ้ามีออเดอร์ค้างถาม force) ; `build_receipt_text(bill) -> str`, `ReceiptDialog(parent, bill)` (ปุ่มบันทึก .txt ที่ exports/)
- `ui/widgets/order_card.OrderCard(master, order, on_status=None, on_cancel_item=None, on_cancel_order=None, big=False)` ; `ORDER_STATUS_TH`

**web/session.py** (`from web import session` — ไม่พึ่ง nicegui ; `storage` = dict-like เช่น `app.storage.browser`)
- ค่าคงที่: `DEVICE_KEY, SESSION_KEY, CART_KEY`, `VIEW_WAITING/ORDER/BILL/CLOSED/CANCELLED` (`VIEW_BY_STATUS` สถานะรอบ → view), `TERMINAL_VIEWS`, `MAX_QTY=99`
- เครื่อง/รอบ: `get_device_id(storage) -> str`, `device_info(user_agent) -> str|None`, `remember_session(storage, session_id)` (รอบใหม่ล้างตะกร้า), `forget_session(storage)`, `load_context(storage) -> {'session_id','device_id','table'(ไม่มี secret_key),'status','view'}|None` (ไม่ใช่ของเครื่องนี้ = None + ลบที่จำ), `require_owner(session_id, device_id) -> dict` (ValueError ถ้าไม่ใช่เจ้าของ)
- การกระทำ (ตรวจเจ้าของให้ ValueError ไทย): `cancel_request(session_id, device_id)` (เฉพาะ pending), `place_order(session_id, device_id, cart, note=None) -> order dict` (user_id=None = ลูกค้า), `mark_notices_read(ids)`
- ตะกร้า `{menu_item_id: qty}`: `cart_load(storage, session_id)`, `cart_save(storage, session_id, cart)`, `cart_clean(cart, menu) -> list[str]` (เอาของหมด/เมนูชั่งออก คืนชื่อที่ถูกเอาออก), `cart_lines(cart, menu)`, `cart_count(cart)`, `cart_total(cart, menu)`
- `get_snapshot(session_id) -> dict|None` (อ่านอย่างเดียว: session, table, view, menu(เฉพาะตอน open), weigh_entries, orders, subtotal, notices, unread, bill) ; `signature(snap)` (hashable ใช้ตัดสินว่าต้องวาดใหม่ไหม)

**web/components.py** (`from web import components`) — `BRAND_COLORS`, `CUSTOMER_STATUS_TH/COLOR`, `ORDER_STATUS_CUSTOMER_TH/COLOR`, `NOTICE_ICONS`, `NOTICE_NOTIFY_TYPES`, `LOGO_URL='/logo.png'` ; format: `money, baht, weight_text, fmt_time, fmt_datetime` ; UI: `apply_theme()`, `page_column()`, `header(table_name, status=None)`, `message_card(icon, title, text=None, color, spinner=False) -> card`, `section_title`, `summary_row(label, value, bold, color)`, `lines_block(weigh_entries, orders)`, `bill_card(bill, paid=False)`

**web/pages/** (ทุกฟังก์ชันเป็นแค่ "วาดเนื้อหา" header วาดโดย server.py)
- `enter.build(client, table_no, k='')` (async, เส้นทาง `/t/{table_no}`; สแกนหลัง `await client.connected()`; สำเร็จ → `/s`) ; `enter._scan(storage, device_id, table_no, key, user_agent) -> {'kind':'ok'|'other_table'|'fail','code','message','table_name'}`
- `waiting.render(ctx, snap, on_change)` ; `bill.render(snap)` ; `order.render(snap, ctx, state, on_change)` (state = `{'cart','tab':'menu'|'mine'|'notice','cat'}`)
- `notice.show_unread(snap) -> int` (toast + mark_read), `notice.render(snap)` (ประวัติ)
- `closed.render_shop_closed/render_invalid_qr/render_table_busy(message=None)/render_other_table(table_name)/render_no_session/render_paid(snap)/render_cancelled(snap)`

**web/server.py** (`from web import server`) — `register_pages()` (ลงซ้ำได้) ; `run(host=None, port=None)` (บล็อก; ใช้ config.WEB_HOST/WEB_PORT) ; `start_in_thread(host=None, port=None) -> Thread` (daemon) ; `get_storage_secret() -> str` ; ค่าคงที่ `POLL_SECONDS=3.0`, `SECRET_FILE`
- เส้นทาง: `/` (บอกให้สแกน), `/t/{table_no}?k=` (เข้าจาก QR), `/s` (หน้าหลักลูกค้า สลับตามสถานะรอบ), `/logo.png` (ไฟล์เดียว)

**ui/owner/** (ทุกหน้า = `Page(OwnerPage)`; คีย์ตาม NAV_ITEMS)
- `_common.OwnerPage(BasePage)` — กันผู้ที่ไม่ใช่เจ้าของอีกชั้น (toast + กลับหน้าโต๊ะ, ไม่ตั้งรีเฟรชเอง) ; หน้าลูกเขียน `on_open(**params)` แทน `on_show` ; `refresh()` เหมือน BasePage
- `_common`: `parse_number(text,label,minimum,maximum,allow_empty,default)`, `parse_int`, `parse_percent`, `parse_date(text,label,allow_empty=True)->'YYYY-MM-DD'|''` (ผิด = ValueError ไทย), `fmt_qty`, `open_folder(path)->bool`, `human_size`, `LabeledMenu(master,label,values)` (`get/set/configure_values/.menu`), `bar(master,fraction,color,width)`
- `dashboard_page` (รีเฟรช 10 วิ) · `menu_page` (`ItemDialog`; หมวด+เมนู, ▲▼ เรียงลำดับ, ซ่อน/แสดง, ทำเป็นหมด) · `stock_page` (`StockDialog`, `QuantityDialog`; เติม/ปรับ/แก้ + ประวัติ) · `promo_page` (`PromoDialog`) · `tables_manage_page` (`AddTableDialog`; สร้าง QR PNG, ตัวอย่าง, คัดลอกลิงก์, สุ่มรหัสใหม่) · `users_page` (`UserDialog`, `PasswordDialog`) · `settings_page` (`normalize_base_url`) · `report_page` (แท็บรายวัน/ชั่วโมง/ขายดี/ยกเลิก/บิล + CSV) · `log_page` (`ACTION_TH` แปลรหัส action, หน้าละ 100) · `backup_page` (กู้คืนต้องยืนยัน 2 ชั้นพิมพ์คำว่า "กู้คืน")

### ข้อควรรู้ / บั๊กที่แก้ / การตัดสินใจเพิ่มเติม
- (ขั้น 0) ค่าสถานะในฐานข้อมูลใช้ภาษาอังกฤษ (free/pending/open/awaiting_payment/closed/cancelled) แสดงผลเป็นไทยผ่าน `config.SESSION_STATUS_TH`
- (ขั้น 0) ค่าที่เจ้าของปรับได้เก็บในตาราง `settings` ส่วน `DEFAULT_SETTINGS` ใน config ใช้เป็นค่าเริ่มต้นตอน seed เท่านั้น
- (ขั้น 0) ไฟล์ฐานข้อมูลคือ `tonmakha.db` ที่รากโปรเจกต์ (สร้างตอนรันขั้น 1)
- (ขั้น 0) ค่า `public_base_url` ยังเป็น localhost จนกว่าจะเลือกวิธีเข้าถึงมือถือจริง
- (ขั้น 1) เวลาเก็บเป็นข้อความเวลาเครื่อง; **น้ำหนักเก็บเป็นกรัม (int)** 1 ขีด = 100 กรัม; เงินเก็บเป็น REAL (บาท)
- (ขั้น 1) "โต๊ะว่าง" ไม่ใช่สถานะในฐานข้อมูล = โต๊ะที่ไม่มี session สถานะ pending/open/awaiting_payment (table_sessions.status มีแค่ pending/open/awaiting_payment/closed/cancelled)
- (ขั้น 1) ตารางที่เพิ่มคอลัมน์นอกเหนือจากแผนเดิม: `table_sessions.cancelled_by` (TEXT: 'staff'/'customer'), `activity_log.actor` (TEXT ชื่อผู้กระทำ รวมลูกค้า), `staff_alerts.sound_played` + `snooze_until` + `resolution`, `orders.status` (new/preparing/served/cancelled), `order_items`/`weigh_entries` เก็บ `name_snapshot` + ราคาตอนสั่งไว้กันราคาเปลี่ยนทีหลัง
- (ขั้น 1) `menu_items.price` = ราคา/กก. ถ้า item_type='weighed' ; ราคา/หน่วย ถ้า 'normal' ; `stock_items.unit` ของเนื้อสัตว์คือ 'กก.' (quantity เป็น REAL) — weigh_service ต้องแปลงกรัม→กก. ตอนตัดสต๊อก
- (ขั้น 1) แต่ละ connection เปิดใหม่ต่อ 1 การทำงาน (ปลอดภัยกับหลายเธรด); เรียกหลายคำสั่งพร้อมกันต้องใช้ `db.transaction()`
- (ขั้น 1) ลง bcrypt ใน sandbox ไม่ได้ จึงยังไม่ได้ทดสอบ hash จริง — เครื่องผู้ใช้ต้อง `pip install -r requirements.txt` ก่อนรัน `python -m database.seed`
- (ขั้น 2A) เครื่องเดิม (device_id ตรงกัน) สแกนซ้ำ = ได้รอบเดิมกลับ ; เครื่องอื่นสแกนโต๊ะที่มีรอบค้าง = 'table_busy'
- (ขั้น 2A) ปิดร้านไม่ได้ถ้ายังมีโต๊ะ pending/open/awaiting_payment (ต้อง force=True) ; ปิดใช้งานโต๊ะที่มีรอบค้างไม่ได้
- (ขั้น 2A) `cancel_session` จากสถานะ open ทำไม่ได้ถ้ามีรายการชั่ง/สั่งที่ยังไม่ยกเลิก (ต้องยกเลิกรายการ/เช็คเอาท์แทน) ; ลูกค้ายกเลิกได้เฉพาะ pending
- (ขั้น 2A) การเปลี่ยน awaiting_payment→closed ทำที่ `table_service.close_session` — checkout_service (2C) ต้องเรียกฟังก์ชันนี้ ไม่แก้ SQL เอง
- (ขั้น 2A) ยังไม่ได้ทดสอบรูป QR จริง (ไม่มี qrcode ใน sandbox) — ในเครื่องผู้ใช้ลอง `qr_service.generate_all_qr()` หลัง pip install
- (ขั้น 2B) **ตัดสินใจ:** ลูกค้าสั่งผ่านมือถือได้เฉพาะเมนู `normal` ; เมนูชั่งกิโล (`weighed`) พนักงานชั่งที่ weigh_service เท่านั้น (ถ้าอยากให้ลูกค้ากด "ขอหมู" ต้องเพิ่มกลไกคำขอภายหลัง)
- (ขั้น 2B) สต๊อก: สั่งโดยลูกค้า = เข้มงวด (ไม่พอ → ValueError) ; พนักงานชั่ง = ไม่เข้มงวด (ตัดจนเหลือ 0 แล้วเมนูหมดอัตโนมัติ) ; ปริมาณไม่ติดลบ (movement บันทึกส่วนที่เปลี่ยนจริง)
- (ขั้น 2B) เมนูหมดอัตโนมัติจากสต๊อก 0 จะ **ไม่กลับมามีขายเอง** เว้นแต่เติมผ่าน `restock()`/`return_to_stock()` (จาก 0 → มี) หรือพนักงานกด `set_sold_out(False)`
- (ขั้น 2B) ข้อความแจ้งลูกค้า: เมนูหมด → broadcast ทุกรอบ open ; ยกเลิกรายการ → ส่งเฉพาะโต๊ะนั้น ; หน้าเว็บดึงด้วย `notice_service.list_unread` แล้ว `mark_read`
- (ขั้น 2B) ยอดเงิน: `weigh_service.session_total` + `order_service.session_total` = ยอดก่อนส่วนลด ; pricing_service (2C) ควรรวม 2 ค่านี้ ไม่คำนวณซ้ำเอง
- (ขั้น 2B) ภายใน `db.transaction()` ต้องส่ง `conn=conn` ให้ทุกฟังก์ชัน service ที่รองรับ ห้ามเรียกฟังก์ชันที่เปิด connection เองซ้อนกัน (จะติด lock)
- (ขั้น 2C) **สูตรบิล:** ค่าบริการคิดจากยอดหลังหักส่วนลด ; **VAT คิดบน (หลังหักส่วนลด + ค่าบริการ)** ; ปัด 2 ตำแหน่งทุกขั้น (HALF_UP) — ถ้าร้านต้องการ VAT คิดเฉพาะยอดอาหาร ต้องแก้ `pricing_service.compute_totals`
- (ขั้น 2C) ตาราง bills เก็บเฉพาะ **จำนวนเงิน** (ไม่เก็บอัตรา %) ; บิลที่บันทึกแล้วแก้/ลบไม่ได้ (ยังไม่มีฟังก์ชันยกเลิกบิล/คืนเงิน) ; ส่วนลดโปรถูกเก็บเป็นจำนวนเงิน แก้โปรทีหลังไม่กระทบบิลเก่า
- (ขั้น 2C) `start_checkout` ย้อนกลับเป็น open **ไม่ได้** (ตามวงจรสถานะ) — กดเช็คบิลผิดแล้วโต๊ะสั่ง/ชั่งเพิ่มไม่ได้ ; หน้าเช็คเอาท์ควรมีกล่องยืนยันก่อนกด (ถ้าต้องการปุ่ม "ยกเลิกเช็คบิล" ต้องเพิ่ม transition ที่ table_service เป็นการแก้ขั้น 2A)
- (ขั้น 2C) ไม่มี `ValueError` ตรวจสิทธิ์ใน services — **UI เป็นผู้ตรวจ role** (หน้า owner/ ต้องกันพนักงาน: โปร, รายงาน, สำรอง/กู้คืน, ตั้งค่า) โดยใช้ `auth_service.has_permission`
- (ขั้น 2C) `pay` คิดยอดใหม่ใน transaction ตอนกดชำระ (ไม่ใช้ยอดที่หน้าจอเห็นก่อนหน้า) — ถ้ายอดเปลี่ยนระหว่างนั้น (เช่นยกเลิกรายการ) ยอดบิลจริงจะต่างจากที่แสดง ; UI ควรโหลด `preview` ใหม่ทุกครั้งที่เปิดหน้า/เปลี่ยนโปร และแสดงยอดจากผล `pay`
- (ขั้น 2C) แจ้งเตือนโต๊ะเงียบ: **1 รอบ + 1 ชนิด มีได้ 1 แจ้งเตือนตลอดรอบ** (กด "ไปเช็คแล้ว" แล้วไม่เตือนซ้ำ ; "ปล่อยไว้" = เตือนวนทุก `alert_snooze_minutes` ตราบที่เงื่อนไขยังจริง) ; แจ้งเตือนที่เงื่อนไขหาย (ยืนยัน/ยกเลิก/มีรายการ/ปิดโต๊ะ) ถูกปิดเองเป็น `auto_cleared`
- (ขั้น 2C) กรณี B นับเวลาจาก `table_sessions.last_activity` ซึ่งขยับเฉพาะเมื่อ ยืนยัน/ชั่ง/สั่ง/ยกเลิก/เปลี่ยนสถานะ — **ขั้น 5 (web) ห้ามเรียก `touch_session` ตอนลูกค้าแค่เปิดดูหน้า** ไม่งั้นกรณี B ไม่เตือน
- (ขั้น 2C) `check_alerts` และ `pop_sound_alerts` ให้เรียกจากฝั่ง PC (ขั้น 3 `alert_center.py`) ที่เดียว ไม่เรียกจากเว็บ ; เวลาที่เตือนอ่านจากค่า `alert_*_minutes` ในตั้งค่าทุกครั้งที่ตรวจ (ขั้นต่ำ 1 นาที ; ยังไม่มีสวิตช์ปิดการเตือน)
- (ขั้น 2C) `report_service.cancellations`: รายการชั่งไม่เก็บเวลา/ผู้ยกเลิก จึงกรองตามเวลาชั่งและช่อง `by` เป็นชื่อผู้ชั่ง (รายการสั่งมีเวลา/ผู้ยกเลิกจริง)
- (ขั้น 2C) กู้คืนข้อมูล: ถ้าไฟล์สำรองถูกสร้างตอนร้านเปิด จะได้โต๊ะค้าง (pending/open) กลับมาด้วย — ค่า `active_sessions` ที่คืนให้ UI ใช้เตือนให้พนักงานเคลียร์ ; `main.py` (ขั้น 7) ควรเรียก `backup_service.auto_backup()` ตอนเปิดแอป
- (ขั้น 2C) ทดสอบเท่านั้นใน sandbox: bcrypt/qrcode ยังไม่เคยรันจริง (ใช้ตัวปลอม) — ในเครื่องผู้ใช้ให้ลอง `python -m database.seed`, `qr_service.generate_all_qr()` และเปิดโปรเจกต์ครั้งแรกเพื่อยืนยัน
- (ขั้น 3) **หน้าใหม่ทุกหน้าสืบทอด `BasePage` และตั้งชื่อคลาสว่า `Page`** ; เรียก service ผ่าน `self.call(...)` เพื่อให้ ValueError ไทยขึ้น toast เอง ; `auto_refresh_ms` เหมาะ 3000–5000 สำหรับหน้าครัว/โต๊ะ (หน้าจะถูก `reload()` ด้วยเมื่อแจ้งเตือนเปลี่ยน)
- (ขั้น 3) ปุ่มแจ้งเตือนโต๊ะเงียบทำงานครบ 3 ปุ่มที่แถบแดง (ยกเลิกโต๊ะมีกล่องยืนยัน) ; แถบแสดงสูงสุด 4 แถว ที่เหลือแสดง "และอีก N รายการ"
- (ขั้น 3) ออกจากระบบ log action `logout` ; แจ้งเตือนยังตรวจต่อเนื่องตลอดที่ล็อกอิน (หยุดตอนล็อกเอาท์/ปิดแอป)
- (ขั้น 3) เสียงเตือน: Windows ใช้ `winsound.Beep` 3 ครั้งใน thread แยก, ระบบอื่นใช้ `bell()` ; เวลาแสดงเป็นปี ค.ศ. (dd/mm/YYYY)
- (ขั้น 3) ใน sandbox ต้องใช้ Python 3.12 ถึงมี tkinter (ทดสอบ GUI ด้วย `xvfb-run` + `ImageGrab`) ; เครื่องผู้ใช้ติดตั้ง Python ปกติจาก python.org มี tkinter อยู่แล้ว ; customtkinter ที่ใช้ทดสอบคือ 6.0.0
- (ขั้น 3) ยังไม่ได้ทดสอบบน Windows จริง (ฟอนต์ Leelawadee UI/เสียง winsound) — ให้ผู้ใช้ลองเปิดหน้าล็อกอินครั้งแรกหลัง `pip install -r requirements.txt` และ `python -m database.seed`
- (ขั้น 4) หน้าที่รีเฟรชเองสร้าง widget ใหม่เฉพาะเมื่อ "signature" ข้อมูลเปลี่ยน (กันกะพริบ/ค่าที่กรอกหาย) ; หลังทำรายการเองให้ตั้ง `_signature=None` แล้ว `refresh()`
- (ขั้น 4) ยกเลิกโต๊ะ pending = ถามยืนยันแล้วใช้เหตุผล "ไม่มีลูกค้าจริง/สแกนมั่ว" อัตโนมัติ ; ยกเลิกโต๊ะ open ต้องกรอกเหตุผล (service ปฏิเสธเองถ้ามีรายการชั่ง/สั่งค้าง ซึ่ง toast จะบอกเหตุผล)
- (ขั้น 4) พนักงานสั่งเมนูชั่งกิโลให้ลูกค้าไม่ได้ในหน้าออเดอร์ (ชั่งที่หน้าชั่งเท่านั้น ตามขั้น 2B) ; หน้าชั่งกรอกได้ทศนิยมขีด (2.5) หรือเป็นกรัม ; MAX 50 กก./ครั้ง
- (ขั้น 4) เช็คเอาท์: เงินสดมีช่องรับเงิน/ทอน (แสดงผลเท่านั้น ไม่บันทึกลง DB) ; ยอดบิลจริงมาจาก `pay()` ; ใบเสร็จเป็น .txt ธรรมดา (ยังไม่ต่อเครื่องพิมพ์) ; ไม่มีปุ่มยกเลิกเช็คบิล (ตามข้อจำกัด 2C)
- (ขั้น 4) ตัวอย่างเทสต์ GUI อัตโนมัติของ sandbox: สคริปต์กด dialog ด้วย `after()` เรียก `button_row.winfo_children()[0].invoke()` (index 0 = ปุ่มยืนยัน)
- (ขั้น 5) **ไม่มีสิทธิ์ล็อกอินฝั่งลูกค้า:** เครื่องลูกค้าถูกจำด้วย `device_id` ใน `app.storage.browser` (คุกกี้เซ็นด้วย `web_secret.key`) ; ทุกการกระทำตรวจว่า `table_sessions.device_id` ตรงเครื่องนี้ ; ถ้า `web_secret.key` เปลี่ยน/หาย ลูกค้าที่ใช้งานอยู่จะหลุดจากรอบ (พนักงานยืนยัน/ยกเลิกจากฝั่ง PC ได้ตามปกติ)
- (ขั้น 5) **สแกนจริงหลังเบราว์เซอร์เชื่อมต่อ** (`await client.connected()`) กันบอตพรีวิวลิงก์ (LINE/Facebook ฯลฯ) สร้างรอบ pending หลอก ; สแกนสำเร็จแล้ว redirect ไป `/s` เพื่อให้รีเฟรช/ย้อนกลับไม่สแกนซ้ำ
- (ขั้น 5) **ตัดสินใจ:** เครื่องที่ยังมีโต๊ะอื่นค้าง (pending/open/awaiting_payment) สแกนโต๊ะใหม่ → ไม่เปิดรอบซ้อน แสดง "คุณกำลังใช้งาน โต๊ะ X อยู่ แจ้งพนักงาน" (กันรอบเก่าหลุดจากเครื่อง) ; รอบที่จบแล้ว (closed/cancelled) สแกนโต๊ะไหนก็ได้
- (ขั้น 5) หน้าลูกค้าโพลทุก 3 วินาที และวาดใหม่เฉพาะเมื่อ `session.signature` เปลี่ยน (ตะกร้า/ช่องกรอกไม่หายตอนไม่มีอะไรเปลี่ยน) ; จบรอบ (closed/cancelled) หยุดโพล ; **ไม่เรียก `touch_session`/`check_alerts`/`pop_sound_alerts` จากเว็บ** (ตรวจแล้วว่าแค่เปิดดูไม่ขยับ `last_activity`)
- (ขั้น 5) ข้อความแจ้งลูกค้า: เด้ง toast แล้ว `mark_read` ทันที (ประวัติเต็มดูได้ที่แท็บ "ข้อความ") ; เมนูในตะกร้าที่หมดระหว่างนั้นถูกเอาออกอัตโนมัติพร้อมแจ้ง ; ส่งออเดอร์ล้มเหลว (หมด/สต๊อกไม่พอ) ทั้งออเดอร์ rollback และตะกร้ายังอยู่ให้แก้
- (ขั้น 5) **ลูกค้าสั่งได้เฉพาะเมนู `normal`** (ตาม 2B) เมนูชั่งกิโลแสดงราคา/กก. พร้อมข้อความ "สั่งกับพนักงาน" ; ลูกค้า**ไม่มีปุ่มเรียกเช็คบิล** (กติกาให้พนักงานกดเช็คบิลที่หน้า PC) หน้ารายการบอกให้เรียกพนักงาน ; หน้าบิลของลูกค้าใช้ `checkout_service.preview` (ไม่ใส่โปร) จึงมีข้อความเตือนว่ายอดอาจเปลี่ยนตามโปรที่พนักงานใช้
- (ขั้น 5) ไม่เปิดโฟลเดอร์ `assets/` เป็นไฟล์สาธารณะ (มี `qr_codes/` ซึ่งมีรหัสลับของโต๊ะ) เปิดเฉพาะ `logo.png` ไฟล์เดียว ; `web/` ไม่ import `ui/theme.py` (พึ่ง customtkinter) จึงมี format ของตัวเองใน `components.py`
- (ขั้น 5) ตามกติกาข้อ 4: ไม่เขียน HTML/CSS เอง ใช้ `ui.*` และ `.classes()` (Tailwind/Quasar ที่ NiceGUI มีให้) ; ไม่ใช้ `ui.footer` (ต้องอยู่ระดับบนสุดของหน้า) ใช้แถบตะกร้า `fixed bottom-0` แทน ; dialog ใช้แบบไม่ await (เปิดด้วย `.open()`) ทดสอบง่ายกว่า
- (ขั้น 5) **ต้องให้ผู้ใช้ทดสอบกับของจริง:** `pip install -r requirements.txt` → `python -m database.seed` → เปิดร้าน (`python -c "from services import shop_service; shop_service.open_shop()"`) → `python -c "from web import server; server.run()"` → เปิด `http://localhost:8080` แล้วสแกนลิงก์จาก `python -c "from services import qr_service; print(qr_service.get_table_url(1))"` ; ถ้าจะลองจากมือถือจริงต้องตั้ง `public_base_url` เป็น IP เครื่องร้าน (เช่น `http://192.168.1.50:8080`) ก่อนสร้าง QR ; `server.start_in_thread()` (ให้ `main.py` ขั้น 7 ใช้) ยังไม่ได้ลองกับ NiceGUI จริง — ถ้ามีปัญหาให้ใช้ `run_web.py` เปิดแยกโปรเซสแทน (DB เป็น WAL ใช้ร่วมกันได้อยู่แล้ว)
- (ขั้น 6) ไม่มีปุ่มลบเมนู/โปร/ผู้ใช้/สต๊อก/โต๊ะ (มีประวัติอ้างอิง) ใช้ "ซ่อน/ปิดใช้" ; ประเภทเมนู (ชั่ง/ปกติ) เปลี่ยนไม่ได้หลังสร้าง (service ไม่รองรับ)
- (ขั้น 6) สต๊อก: "ปรับ +/-" ไม่เปิดเมนูที่หมดกลับ (ตามกติกา service) — ให้ใช้ปุ่ม "เติม" ; ลดจนเป็น 0 เมนูที่ผูกหมดเอง
- (ขั้น 6) ปิดบัญชี/ลดสิทธิ์ผู้ใช้ที่ล็อกอินอยู่ไม่ได้ (กันล็อกตัวเอง) ; หน้าตั้งค่าตรวจทุกช่องก่อนบันทึก ผิดช่องเดียว = ไม่บันทึกอะไร ; เปลี่ยน public_base_url แล้วมีกล่องเตือนให้สร้าง QR ใหม่
- (ขั้น 6) หลังกู้คืนข้อมูลเรียก `app.show_login()` ให้ล็อกอินใหม่ (ผู้ใช้ในไฟล์สำรองอาจต่างจากปัจจุบัน) ; ขั้น 7 ควรให้ `main.py` เรียก `backup_service.auto_backup()` ตอนเปิดแอป
- (ขั้น 6) หน้ารายงาน/ประวัติ override `reload()` ไม่รีเฟรชตามแจ้งเตือนโต๊ะเงียบ (กันตารางเลื่อนหาย) ; รายการยกเลิกในรายงานรวมการยกเลิกทั้งโต๊ะ ; log ต้องเพิ่ม action ใหม่ใน `ACTION_TH` (ไม่อยู่ในรายการ = แสดงรหัสเดิม)
- (ขั้น 6) ไม่มีใบพิมพ์ QR รวมหลายโต๊ะ — พิมพ์จากไฟล์ `assets/qr_codes/table_<เลข>.png` แต่ละใบ (ปรับปรุงภายหลังได้)
- (ขั้น 7–8) **ต้องทดสอบกับของจริง (ยังไม่เคยรัน):** (1) GUI บน Windows จริง — เลย์เอาต์/ฟอนต์/ความกว้างตาราง/เสียงเตือน (2) NiceGUI จริง — หน้ามือถือ, `ui.run` ใน thread ของ `main.py` (ถ้าปัญหาใช้ `--web process`) (3) bcrypt/qrcode จริง และสแกน QR จากมือถือในเครือข่ายร้าน + Firewall พอร์ต 8080 (4) ปลายทางที่ยังไม่ได้ทำ: ใบพิมพ์ QR รวมหลายโต๊ะ, เครื่องพิมพ์ใบเสร็จ, ปุ่มยกเลิกเช็คบิล/ยกเลิกบิล, ให้ลูกค้ากด "ขอหมู"/เรียกเช็คบิล, วิธีเข้าถึงนอกร้าน (Tailscale Funnel)
- (ขั้น 7) `main.py` สร้างข้อมูลตัวอย่างเฉพาะเมื่อไม่มีผู้ใช้เลย ; บัญชี owner/staff1 รหัสเริ่มต้นต้องเปลี่ยนก่อนใช้งานจริง (README เตือนแล้ว ยังไม่มีการบังคับในแอป)
- (แก้บั๊กหลังทดสอบจริง) สแกน QR แล้วค้าง "กำลังตรวจสอบ QR..." + TypeError "the response to the browser has already been built": `app.storage.browser` เขียนไม่ได้หลังส่งหน้าไปแล้ว (หลัง `await client.connected()` และใน event handler ของตะกร้า) -> เปลี่ยนเป็น `app.storage.user` (เก็บฝั่งเซิร์ฟเวอร์ในโฟลเดอร์ `.nicegui/` ผูกกับเบราว์เซอร์ผ่านคุกกี้) ใน web/server.py, web/pages/enter.py, web/pages/order.py ; ห้ามใส่ `.nicegui/` ใน git


---

## ขั้นที่ 9 — การปรับปรุงเพิ่มเติมตามข้อกำหนด (2.1–2.8)

### สรุปสิ่งที่พัฒนาเพิ่มและไฟล์ที่แก้ไข
- [x] **2.1 หน้าลูกค้า NiceGUI แสดงสต๊อกและป้องกันการสั่งสินค้าหมด** (`services/menu_service.py`, `services/order_service.py`, `web/session.py`, `web/pages/order.py`)
  - เพิ่ม `stock_quantity`, `stock_unit`, `stock_text` ในข้อมูลเมนูจาก `menu_service.get_menu_for_customer()`
  - แสดงสต๊อกคงเหลือพร้อมหน่วยจริงจากฐานข้อมูล (เช่น `คงเหลือ 46 ขวด`, `สินค้าหมด · คงเหลือ 0 ขวด`)
  - ซ่อนปุ่มเพิ่มรายการเมื่อสินค้าหมดหรือสต๊อกเป็น 0 และจำกัดปุ่ม `+` ไม่ให้เพิ่มเกินสต๊อกคงเหลือ (`session.max_orderable_qty`, `session.cart_change_item`)
  - ตรวจสอบสต๊อกซ้ำใน `order_service.create_order` ภายใต้ `db.transaction()` (`BEGIN IMMEDIATE`) เพื่อป้องกัน race condition เมื่อหลายโต๊ะสั่งชิ้นสุดท้ายพร้อมกัน และตัดสต๊อกเพียงครั้งเดียวตอนยืนยันสั่ง
  - อัปเดต `session.signature(snap)` ให้รวม `stock_quantity`, `stock_unit`, `image_path` เพื่อให้หน้าลูกค้ารีเฟรชสต๊อกอัตโนมัติ
- [x] **2.2 แจ้งเตือนสต๊อกใกล้หมดและสินค้าหมดให้พนักงาน** (`database/schema.py`, `config.py`, `services/stock_service.py`, `services/alert_service.py`, `ui/alert_center.py`, `ui/owner/settings_page.py`)
  - เพิ่มค่าตั้งค่า `stock_low_threshold` (ค่าเริ่มต้น 5 หน่วย แก้ไขได้ที่หน้าตั้งค่า) และคอลัมน์ `stock_items.alert_level`
  - ขยายตาราง `staff_alerts` ให้รองรับ `stock_item_id` และชนิด `low_stock` (`สต๊อกใกล้หมด: [ชื่อ] เหลือ [จำนวน] [หน่วย]`) กับ `out_of_stock` (`สินค้าหมด: [ชื่อ] เหลือ 0 [หน่วย]`)
  - ป้องกันการสร้างแจ้งเตือนและ log ซ้ำในการ refresh แต่ละรอบ และรีเซ็ตสถานะกลับเป็น `normal` อัตโนมัติเมื่อเติมสต๊อกสูงกว่าเกณฑ์
- [x] **2.3 รูปภาพสินค้าในแต่ละเมนู (อัปโหลด แสดง 1:1 และลบ)** (`config.py`, `database/schema.py`, `services/menu_service.py`, `ui/owner/menu_page.py`, `web/server.py`, `web/pages/order.py`)
  - เพิ่มคอลัมน์ `menu_items.image_path` และฟังก์ชัน `menu_service.set_item_image`, `delete_item_image`, `get_item_image_file`
  - รองรับ JPG/JPEG, PNG, WebP ขนาดไม่เกิน 5 MB ตรวจชนิดไฟล์จริงด้วย Pillow และปรับสัดส่วน 1:1 (square, สูงสุด 400x400 px) ด้วย `ImageOps.fit` โดยไม่บิดสัดส่วนภาพ
  - เก็บไฟล์ด้วยชื่อสุ่มปลอดภัยใน `assets/uploads/menu/` และเปิดเส้นทาง `/uploads` ใน `web/server.py` (ไม่เปิด `assets/qr_codes/`)
  - ลบไฟล์อย่างปลอดภัยโดยตรวจว่าไม่มีเมนูอื่นอ้างอิงอยู่ และใช้ placeholder เมื่อไม่มีรูป
- [x] **2.4 & 2.5 หน้าชำระเงิน (ตรวจยอดรับเงินด้วย Decimal) และสร้าง PromptPay QR แบบระบุยอดเงิน** (`config.py`, `services/settings_service.py`, `services/qr_service.py`, `services/checkout_service.py`, `ui/staff/checkout_page.py`, `ui/owner/settings_page.py`)
  - เพิ่มคอลัมน์ `bills.amount_received`, `bills.change_amount` และฟังก์ชัน `checkout_service.validate_payment` (ใช้ `Decimal` ป้องกัน floating-point error)
  - ห้ามรับเงินสดติดลบ/ตัวอักษร/ค่าว่าง/ต่ำกว่ายอดสุทธิ และคำนวณเงินทอนสดก่อนยืนยัน
  - เพิ่ม `qr_service.build_promptpay_payload`, `validate_promptpay_id`, `generate_promptpay_qr` ตามมาตรฐาน EMVCo (Tag 29 PromptPay + Tag 54 Amount + Tag 63 CRC16) แยกจาก QR โต๊ะชัดเจน
  - ค่าเริ่มต้น PromptPay: `0123456789` (`นางสาวพะพินพอ เพิ่มพูนพูน`) แก้ไขได้ที่หน้าตั้งค่า แสดงสถานะ `รอตรวจสอบการโอน` โดยไม่ปิดบิลอัตโนมัติจนกว่าพนักงานจะกดยืนยัน
- [x] **2.6 ใบเสร็จ PDF และ TXT พร้อมรายละเอียดการเงินครบถ้วน** (`requirements.txt`, `services/checkout_service.py`, `ui/staff/checkout_page.py`, `assets/fonts/`)
  - เพิ่ม `checkout_service.export_receipt_pdf`, `export_receipt_txt`, `export_receipt` พร้อมฟอนต์ภาษาไทย+ตัวเลขอารบิก `NotoSansThai-Regular.ttf` และ `NotoSansThai-Bold.ttf` ใน `assets/fonts/`
  - แสดงรายการครบถ้วนพร้อมคำว่า `รวมเป็นเงินก่อนคิดภาษีและส่วนลด`, `ภาษีมูลค่าเพิ่ม` (ไม่ใช้คำว่า VAT แสดงต่อผู้ใช้), `ยอดชำระสุทธิ`, `รับเงินมา` และ `เงินทอน` (`0.00 บาท (ไม่เกี่ยวข้อง)` สำหรับโอน/PromptPay)
- [x] **2.7 หน้าชั่งน้ำหนัก: เอาส่วน "เมนูที่ชั่ง" ออก และแสดงอัตรา "กิโลกรัมละ 299 บาท"** (`config.py`, `database/schema.py`, `services/weigh_service.py`, `services/settings_service.py`, `ui/staff/weigh_page.py`)
  - ลบส่วนเลือกเมนูที่ชั่งออกจาก `ui/staff/weigh_page.py` เหลือเฉพาะเลือกโต๊ะและกรอกน้ำหนัก (ขีด/กรัม/กิโลกรัม)
  - แสดงอัตรา `กิโลกรัมละ 299 บาท` ซิงก์กับ `settings` (`weigh_price_per_kg`) และ `weigh_service.get_price_per_kg()`
- [x] **2.8 หน้าสต๊อกเจ้าของร้าน: เพิ่มปุ่มลบรายการสต๊อก** (`services/stock_service.py`, `ui/owner/stock_page.py`, `ui/owner/log_page.py`)
  - เพิ่ม `stock_service.get_delete_impact` และ `stock_service.delete_item` (จำกัดสิทธิ์เฉพาะเจ้าของร้าน)
  - หากไม่มีความสัมพันธ์กับเมนู/ประวัติการเคลื่อนไหว/ออเดอร์ จะลบจริงใน transaction ; หากมีประวัติอ้างอิง จะป้องกันการลบประวัติย้อนหลังและทำ Soft Delete (`active=0`) แทน พร้อมบันทึก `log_service`
