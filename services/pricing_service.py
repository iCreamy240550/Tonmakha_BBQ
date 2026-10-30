"""services/pricing_service.py — คิดยอดบิลของรอบ (ไม่เขียนฐานข้อมูล ไม่ log)

สูตร (ตามกติกาธุรกิจ):
    ยอดรวม (subtotal)   = ยอดรายการชั่ง + ยอดรายการสั่ง   (จาก weigh_service / order_service ไม่คำนวณซ้ำ)
    ส่วนลด (discount)   = ส่วนลดโปร (ไม่เกินยอดรวม)
    หลังลด              = ยอดรวม − ส่วนลด
    ค่าบริการ           = หลังลด × service_charge_percent%        (ถ้า service_charge_enabled)
    VAT                 = (หลังลด + ค่าบริการ) × vat_percent%     (ถ้า vat_enabled)  ← VAT คิดบนค่าบริการด้วย
    ยอดสุทธิ (total)    = หลังลด + ค่าบริการ + VAT
ทุกขั้นปัดเป็น 2 ตำแหน่ง (ROUND_HALF_UP) แล้วจึงนำไปคิดขั้นถัดไป ; อัตราอ่านจาก settings_service ตอนเรียก
"""
from decimal import ROUND_HALF_UP, Decimal

from database import db
from services import order_service, promo_service, settings_service, weigh_service


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_totals(subtotal: float, discount: float = 0.0, service_percent: float = 0.0,
                   vat_percent: float = 0.0) -> dict:
    """คำนวณล้วน ๆ (ไม่แตะฐานข้อมูล) ; service_percent/vat_percent = 0 คือไม่คิด
    -> {'subtotal','discount','after_discount','service_charge','vat','total'} (float 2 ตำแหน่ง)
    ValueError ถ้ายอดติดลบ / ส่วนลดเกินยอดรวม / เปอร์เซ็นต์ติดลบ"""
    if subtotal < 0 or discount < 0:
        raise ValueError("ยอดเงินต้องไม่ติดลบ")
    if service_percent < 0 or vat_percent < 0:
        raise ValueError("เปอร์เซ็นต์ต้องไม่ติดลบ")
    sub, disc = _q(Decimal(str(subtotal))), _q(Decimal(str(discount)))
    if disc > sub:
        raise ValueError("ส่วนลดต้องไม่เกินยอดรวม")
    after = sub - disc
    service = _q(after * Decimal(str(service_percent)) / Decimal(100))
    vat = _q((after + service) * Decimal(str(vat_percent)) / Decimal(100))
    total = after + service + vat
    return {"subtotal": float(sub), "discount": float(disc), "after_discount": float(after),
            "service_charge": float(service), "vat": float(vat), "total": float(total)}


def get_rates() -> dict:
    """อัตราที่ใช้อยู่ตอนนี้ -> {'service_charge_enabled','service_charge_percent','vat_enabled','vat_percent'}
    (percent เป็น 0 เมื่อปิด ; ใช้แสดงบนบิล)"""
    sc_on = settings_service.get_bool("service_charge_enabled")
    vat_on = settings_service.get_bool("vat_enabled")
    return {
        "service_charge_enabled": sc_on,
        "service_charge_percent": settings_service.get_float("service_charge_percent") if sc_on else 0.0,
        "vat_enabled": vat_on,
        "vat_percent": settings_service.get_float("vat_percent") if vat_on else 0.0,
    }


def calc_bill(session_id: int, promo_id: int | None = None, conn=None) -> dict:
    """คิดบิลของรอบ ณ ตอนนี้ (ใช้ได้ทุกสถานะรอบ — ดูล่วงหน้า/ตอนเช็คเอาท์)
    promo_id: โปรที่เลือก (None = ไม่ใช้) ; ValueError ถ้าใช้โปรไม่ได้ (ปิด/นอกช่วง/ยอดไม่ถึง/ไม่พบ)
    conn: ส่งมาเมื่อเรียกภายใน transaction ของ checkout (ใช้เช็คโปรใน transaction เดียวกัน)
    -> dict: session_id, weigh_total, order_total, subtotal, promo_id, promo_name, discount, after_discount,
             service_charge_enabled, service_charge_percent, service_charge,
             vat_enabled, vat_percent, vat, total
    หมายเหตุ: ยอดชั่ง/ยอดสั่งอ่านผ่าน connection แยก (อ่านอย่างเดียว ไม่ติด lock ใน WAL)"""
    weigh_total = weigh_service.session_total(session_id)
    order_total = order_service.session_total(session_id)
    subtotal = round(weigh_total + order_total, 2)

    promo, discount = None, 0.0
    if promo_id is not None:
        promo = promo_service.check_applicable(promo_id, subtotal, conn=conn)
        discount = promo_service.calc_discount(promo, subtotal)
    else:
        try:
            s_row = db.query_one("SELECT applied_promo_id FROM table_sessions WHERE id = ?", (session_id,), conn=conn)
            app_pid = s_row["applied_promo_id"] if s_row and "applied_promo_id" in s_row.keys() else None
            if app_pid:
                promo = promo_service.check_applicable(int(app_pid), subtotal, conn=conn)
                discount = promo_service.calc_discount(promo, subtotal)
        except Exception:
            promo, discount = None, 0.0

    rates = get_rates()
    t = compute_totals(subtotal, discount, rates["service_charge_percent"], rates["vat_percent"])
    return {
        "session_id": session_id, "weigh_total": weigh_total, "order_total": order_total,
        "subtotal": t["subtotal"], "promo_id": promo["id"] if promo else None,
        "promo_name": promo["name"] if promo else None, "discount": t["discount"],
        "after_discount": t["after_discount"],
        "service_charge_enabled": rates["service_charge_enabled"],
        "service_charge_percent": rates["service_charge_percent"], "service_charge": t["service_charge"],
        "vat_enabled": rates["vat_enabled"], "vat_percent": rates["vat_percent"], "vat": t["vat"],
        "total": t["total"],
    }
