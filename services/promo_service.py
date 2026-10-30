"""services/promo_service.py — โปรโมชั่น/ส่วนลด (ตาราง promotions)

ชนิด: 'percent' (ลด % ของยอดรวม, ค่า 0-100) | 'fixed' (ลดเป็นจำนวนบาท)
กลุ่มเป้าหมาย (target): 'general' (โปรโมชั่นสำหรับคนทั่วไป) | 'member' (โปรโมชั่นสำหรับสมาชิก)
โปรใช้ได้เมื่อ: active=1, อยู่ในช่วง start_at..end_at (ว่าง = ไม่จำกัด) และยอดรวม >= min_amount
ส่วนลดไม่เกินยอดรวมเสมอ ; ไม่มีการลบโปร (มีบิลอ้างอิง) — ใช้ปิดใช้งานแทน
pricing_service เป็นผู้เรียก calc_discount / check_applicable ตอนคิดบิล
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
import re

from database import db
from services import log_service

PROMO_TYPES = ("percent", "fixed")
PROMO_TYPE_TH = {"percent": "ลดเป็น %", "fixed": "ลดเป็นบาท"}

PROMO_TARGETS = ("general", "member")
PROMO_TARGET_TH = {"general": "คนทั่วไป", "member": "สมาชิก"}

DEFAULT_MEMBER_PROMOS = [
    {
        "name": "ส่วนลดต้อนรับสมาชิก 50 บาท",
        "promo_type": "fixed",
        "value": 50.0,
        "min_amount": 0.0,
        "target": "member",
        "code": "TONMAKHA50",
        "description": "ลดทันที 50 บาท สำหรับสมาชิกเมื่อสั่งอาหารภายในร้าน (ไม่มีขั้นต่ำ)",
    },
    {
        "name": "ลด 10% ทั้งบิล สำหรับสมาชิก",
        "promo_type": "percent",
        "value": 10.0,
        "min_amount": 300.0,
        "target": "member",
        "code": "MEMBER10",
        "description": "รับส่วนลด 10% จากยอดรวมค่าอาหาร เมื่อทานครบ 300 บาทขึ้นไป",
    },
    {
        "name": "ปาร์ตี้หมูกระทะ ลด 100 บาท",
        "promo_type": "fixed",
        "value": 100.0,
        "min_amount": 500.0,
        "target": "member",
        "code": "PARTY100",
        "description": "รับส่วนลดพิเศษ 100 บาท เมื่อมียอดสั่งอาหารตั้งแต่ 500 บาทขึ้นไป",
    },
]


# ---------------------------------------------------------------- ตัวช่วยภายใน

def _money(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _label(promo_type: str, value: float) -> str:
    return f"{value:g}%" if promo_type == "percent" else f"{value:g} บาท"


def _norm_time(text, end_of_day: bool) -> str | None:
    """รับ 'YYYY-MM-DD' หรือ 'YYYY-MM-DD HH:MM[:SS]' -> 'YYYY-MM-DD HH:MM:SS' ; ว่าง/None -> None
    วันที่ล้วน: ต้นช่วง = 00:00:00, ท้ายช่วง = 23:59:59"""
    if text is None or str(text).strip() == "":
        return None
    t = str(text).strip()
    for fmt, has_time in (("%Y-%m-%d %H:%M:%S", True), ("%Y-%m-%d %H:%M", True), ("%Y-%m-%d", False)):
        try:
            d = datetime.strptime(t, fmt)
        except ValueError:
            continue
        if not has_time and end_of_day:
            d = d.replace(hour=23, minute=59, second=59)
        return d.strftime(db.TIME_FORMAT)
    raise ValueError("รูปแบบวันที่ไม่ถูกต้อง (ใช้ ปี-เดือน-วัน เช่น 2026-10-31)")


def _validate(promo_type, value, min_amount, target: str = "general") -> None:
    if promo_type not in PROMO_TYPES:
        raise ValueError("ชนิดโปรโมชั่นไม่ถูกต้อง")
    if target not in PROMO_TARGETS:
        raise ValueError("กลุ่มเป้าหมายโปรโมชั่นไม่ถูกต้อง")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("ค่าส่วนลดต้องมากกว่า 0")
    if promo_type == "percent" and value > 100:
        raise ValueError("ส่วนลดเปอร์เซ็นต์ต้องไม่เกิน 100")
    if isinstance(min_amount, bool) or not isinstance(min_amount, (int, float)) or min_amount < 0:
        raise ValueError("ยอดขั้นต่ำต้องไม่ติดลบ")


def _clean_code(code: str | None, fallback_id: int | None = None, target: str = "general") -> str:
    raw = re.sub(r"[^A-Za-z0-9_-]", "", (code or "").strip()).upper()
    if raw:
        return raw[:24]
    if target == "member":
        return f"MEM{fallback_id or 1:02d}"
    return f"PRO{fallback_id or 1:02d}"


def _default_desc(promo_type: str, value: float, min_amount: float) -> str:
    disc_txt = f"{value:g}%" if promo_type == "percent" else f"{value:g} บาท"
    min_txt = f"เมื่อทานครบ {min_amount:,.0f} บาทขึ้นไป" if min_amount > 0 else "(ไม่มีขั้นต่ำ)"
    return f"รับส่วนลด {disc_txt} สำหรับสมาชิก {min_txt}"


def _promo(row) -> dict:
    d = dict(row)
    d["active"] = bool(d["active"])
    target = d.get("target") or "general"
    if target not in PROMO_TARGETS:
        target = "general"
    d["target"] = target
    d["target_th"] = PROMO_TARGET_TH.get(target, target)
    d["promo_type_th"] = PROMO_TYPE_TH.get(d["promo_type"], d["promo_type"])
    d["label"] = _label(d["promo_type"], d["value"])
    d["code"] = _clean_code(d.get("code"), fallback_id=d.get("id"), target=target)
    d["description"] = (d.get("description") or "").strip() or _default_desc(
        d["promo_type"], float(d["value"]), float(d["min_amount"] or 0)
    )
    return d


def ensure_default_member_promos(conn=None) -> None:
    """สร้างโปรโมชันสำหรับสมาชิกเริ่มต้น 3 รายการหากยังไม่มีโปรโมชันสำหรับสมาชิกในฐานข้อมูลเลย"""
    def _do(c) -> None:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(promotions)").fetchall()}
        if "target" not in cols:
            c.execute("ALTER TABLE promotions ADD COLUMN target TEXT NOT NULL DEFAULT 'general'")
        if "code" not in cols:
            c.execute("ALTER TABLE promotions ADD COLUMN code TEXT")
        if "description" not in cols:
            c.execute("ALTER TABLE promotions ADD COLUMN description TEXT")

        has_member_promo = c.execute(
            "SELECT 1 FROM promotions WHERE target = 'member' LIMIT 1"
        ).fetchone()
        if has_member_promo is not None:
            return
        for p in DEFAULT_MEMBER_PROMOS:
            c.execute(
                "INSERT INTO promotions (name, promo_type, value, min_amount, start_at, end_at, active, target, code, description) "
                "VALUES (?, ?, ?, ?, NULL, NULL, 1, ?, ?, ?)",
                (
                    p["name"],
                    p["promo_type"],
                    p["value"],
                    p["min_amount"],
                    p["target"],
                    p["code"],
                    p["description"],
                ),
            )

    if conn is not None:
        _do(conn)
    else:
        with db.transaction() as c:
            _do(c)


# ---------------------------------------------------------------- อ่าน

def get_promo(promo_id: int, conn=None) -> dict | None:
    """โปรตาม id -> dict (active เป็น bool, + promo_type_th, label เช่น '10%' / '50 บาท') หรือ None"""
    r = db.query_one("SELECT * FROM promotions WHERE id = ?", (promo_id,), conn=conn)
    return _promo(r) if r else None


def get_promo_by_code(code: str, conn=None) -> dict | None:
    """ค้นหาโปรโมชั่นจากรหัสโค้ด (case-insensitive)"""
    clean = (code or "").strip().upper()
    if not clean:
        return None
    ensure_default_member_promos(conn=conn)
    rows = db.query_all("SELECT * FROM promotions WHERE active = 1 ORDER BY id DESC", conn=conn)
    for r in rows:
        p = _promo(r)
        if p["code"].upper() == clean:
            return p
    return None


def list_promos(include_inactive: bool = True, target: str | None = None) -> list[dict]:
    """โปรทั้งหมด ใหม่สุดก่อน (หน้าเจ้าของ) ; ถ้าระบุ target ('general'|'member') จะกรองเฉพาะกลุ่มนั้น"""
    ensure_default_member_promos()
    clauses, params = [], []
    if not include_inactive:
        clauses.append("active = 1")
    if target in PROMO_TARGETS:
        clauses.append("COALESCE(target, 'general') = ?")
        params.append(target)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = "SELECT * FROM promotions" + where + " ORDER BY id DESC"
    return [_promo(r) for r in db.query_all(sql, tuple(params))]


def is_in_period(promo: dict, at: str | None = None) -> bool:
    """เวลา `at` ('YYYY-MM-DD HH:MM:SS', ไม่ส่ง = ตอนนี้) อยู่ในช่วงเวลาของโปรหรือไม่"""
    at = at or db.now_str()
    if promo.get("start_at") and at < promo["start_at"]:
        return False
    if promo.get("end_at") and at > promo["end_at"]:
        return False
    return True


def calc_discount(promo: dict, subtotal: float) -> float:
    """ส่วนลด (บาท ปัด 2 ตำแหน่ง) จากยอดรวม ; ไม่เกินยอดรวม ; ไม่เช็คเงื่อนไข (ใช้ check_applicable)"""
    if subtotal <= 0:
        return 0.0
    if promo["promo_type"] == "percent":
        d = _money(Decimal(str(subtotal)) * Decimal(str(promo["value"])) / Decimal(100))
    else:
        d = _money(promo["value"])
    return min(d, _money(subtotal))


def list_available(
    subtotal: float | None = None,
    at: str | None = None,
    target: str | None = None,
    include_member_promo_id: int | None = None,
) -> list[dict]:
    """โปรที่เลือกใช้ได้ตอนนี้ (เปิดใช้ + อยู่ในช่วงเวลา + ถ้าส่ง subtotal ต้องถึงยอดขั้นต่ำ)
    ถ้าส่ง subtotal แต่ละ dict จะมี 'discount' (ส่วนลดที่จะได้) — สำหรับ dropdown หน้าเช็คเอาท์"""
    out = []
    for p in list_promos(include_inactive=False):
        if target in PROMO_TARGETS and p["target"] != target:
            if include_member_promo_id is None or p["id"] != include_member_promo_id:
                continue
        if not is_in_period(p, at):
            continue
        if subtotal is not None:
            if subtotal < p["min_amount"]:
                continue
            p["discount"] = calc_discount(p, subtotal)
        out.append(p)
    return out


def check_applicable(promo_id: int, subtotal: float, at: str | None = None, conn=None) -> dict:
    """ตรวจว่าใช้โปรนี้กับยอดรวมนี้ได้ -> dict โปร ; ValueError (ข้อความไทย) ถ้าไม่พบ/ปิดใช้/นอกช่วงเวลา/ยอดไม่ถึง"""
    p = get_promo(promo_id, conn=conn)
    if p is None:
        raise ValueError("ไม่พบโปรโมชั่นที่เลือก")
    if not p["active"]:
        raise ValueError(f"โปร \"{p['name']}\" ปิดใช้งานแล้ว")
    if not is_in_period(p, at):
        raise ValueError(f"โปร \"{p['name']}\" ไม่อยู่ในช่วงเวลาที่ใช้ได้")
    if subtotal < p["min_amount"]:
        raise ValueError(f"โปร \"{p['name']}\" ต้องมียอดอย่างน้อย {p['min_amount']:,.2f} บาท")
    return p


# ---------------------------------------------------------------- จัดการ (เจ้าของ)

def add_promo(
    name: str,
    promo_type: str,
    value: float,
    min_amount: float = 0,
    start_at: str | None = None,
    end_at: str | None = None,
    user_id: int | None = None,
    target: str = "general",
    code: str | None = None,
    description: str | None = None,
) -> dict:
    """เพิ่มโปร -> dict ; start_at/end_at = 'YYYY-MM-DD' (หรือมีเวลา) หรือ None/'' = ไม่จำกัด
    target: 'general' (คนทั่วไป) หรือ 'member' (สมาชิก)
    ValueError ถ้าชื่อว่าง/ชนิดผิด/ค่า<=0/เปอร์เซ็นต์>100/ยอดขั้นต่ำติดลบ/วันที่ผิด/เริ่มหลังสิ้นสุด"""
    name = (name or "").strip()
    if not name:
        raise ValueError("กรุณาใส่ชื่อโปรโมชั่น")
    target = (target or "general").strip() or "general"
    _validate(promo_type, value, min_amount, target=target)
    s, e = _norm_time(start_at, False), _norm_time(end_at, True)
    if s and e and s > e:
        raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")
    clean_desc = (description or "").strip() or None
    with db.transaction() as conn:
        pid = db.execute(
            "INSERT INTO promotions (name, promo_type, value, min_amount, start_at, end_at, active, target, code, description) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (name, promo_type, value, min_amount, s, e, target, None, clean_desc),
            conn=conn,
        )
        final_code = _clean_code(code, fallback_id=pid, target=target)
        db.execute("UPDATE promotions SET code = ? WHERE id = ?", (final_code, pid), conn=conn)
        target_lbl = PROMO_TARGET_TH.get(target, target)
        log_service.log_action(
            "promo_add",
            f"เพิ่มโปร ({target_lbl}) {name} (ลด {_label(promo_type, value)}, ขั้นต่ำ {min_amount:g})",
            user_id=user_id,
            ref_type="promotion",
            ref_id=pid,
            conn=conn,
        )
    return get_promo(pid)


def update_promo(
    promo_id: int,
    name: str | None = None,
    promo_type: str | None = None,
    value: float | None = None,
    min_amount: float | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    active: bool | None = None,
    user_id: int | None = None,
    target: str | None = None,
    code: str | None = None,
    description: str | None = None,
) -> dict:
    """แก้โปร (ส่งเฉพาะที่จะแก้) ; start_at/end_at: ส่ง '' = ล้างค่า (ไม่จำกัด), None = ไม่แก้
    ไม่กระทบบิลที่ปิดไปแล้ว (บิลเก็บส่วนลดเป็นจำนวนเงินไว้แล้ว) ; ValueError ถ้าไม่พบ/ค่าไม่ถูกต้อง"""
    with db.transaction() as conn:
        old = get_promo(promo_id, conn=conn)
        if old is None:
            raise ValueError("ไม่พบโปรโมชั่น")
        new_name = name.strip() if name is not None else old["name"]
        if not new_name:
            raise ValueError("กรุณาใส่ชื่อโปรโมชั่น")
        new_type = promo_type if promo_type is not None else old["promo_type"]
        new_value = value if value is not None else old["value"]
        new_min = min_amount if min_amount is not None else old["min_amount"]
        new_target = (target.strip() if target is not None else old["target"]) or "general"
        _validate(new_type, new_value, new_min, target=new_target)
        new_start = _norm_time(start_at, False) if start_at is not None else old["start_at"]
        new_end = _norm_time(end_at, True) if end_at is not None else old["end_at"]
        if new_start and new_end and new_start > new_end:
            raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")
        new_active = (1 if active else 0) if active is not None else (1 if old["active"] else 0)
        new_code = _clean_code(code if code is not None else old.get("code"), fallback_id=promo_id, target=new_target)
        new_desc = (description.strip() if description is not None else old.get("description")) or None
        db.execute(
            "UPDATE promotions SET name=?, promo_type=?, value=?, min_amount=?, start_at=?, end_at=?, "
            "active=?, target=?, code=?, description=? WHERE id=?",
            (
                new_name,
                new_type,
                new_value,
                new_min,
                new_start,
                new_end,
                new_active,
                new_target,
                new_code,
                new_desc,
                promo_id,
            ),
            conn=conn,
        )
        log_service.log_action(
            "promo_update",
            f"แก้โปร {old['name']} -> {new_name} (ลด {_label(new_type, new_value)}, "
            f"ขั้นต่ำ {new_min:g}, ใช้งาน={new_active})",
            user_id=user_id,
            ref_type="promotion",
            ref_id=promo_id,
            conn=conn,
        )
    return get_promo(promo_id)
