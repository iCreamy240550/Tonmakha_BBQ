"""services/qr_service.py — ลิงก์/รูป QR ของโต๊ะ และฟังก์ชันสร้าง QR รับเงิน PromptPay (แยกกันชัดเจน)

1. QR โต๊ะ (สำหรับลูกค้าสแกนสั่งอาหาร):
   ลิงก์ QR = {public_base_url}/t/<เลขโต๊ะ>?k=<รหัสลับ>
   เก็บไฟล์ที่ assets/qr_codes/table_<เลข>.png

2. QR รับเงิน PromptPay (มาตรฐาน EMVCo / Thai QR Payment):
   ระบุยอดชำระสุทธิ (Tag 54) ตามบิลจริง + หมายเลขผู้รับจากตั้งค่า (promptpay_id)
   หมายเหตุสำคัญ: การสร้าง/แสดง QR ไม่ได้ยืนยันว่ามีเงินโอนเข้าจริง พนักงานต้องตรวจสอบยอดเงินในแอปธนาคารก่อนกดยืนยันชำระเงิน
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import secrets

from PIL import Image, ImageDraw

import config
from services import settings_service, shop_service, table_service


def _render_qr_image(payload: str, box_size: int = 10, border: int = 4) -> Image.Image:
    """สร้างภาพ QR Code มาตรฐาน ISO/IEC 18004 (ใช้ไลบรารี qrcode หรือ reportlab.graphics.barcode.qrencoder)"""
    if not payload or not isinstance(payload, str):
        raise ValueError("ข้อมูลสำหรับสร้าง QR ไม่ถูกต้อง")
    # 1) ลองใช้แพ็กเกจ qrcode มาตรฐาน (ตรวจว่ามีโมดูลย่อย qrcode.main จริง)
    try:
        import qrcode
        import qrcode.main  # noqa: F401
        qr = qrcode.QRCode(box_size=box_size, border=border)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        if hasattr(img, "get_image"):
            img = img.get_image()
        return img.convert("RGB")
    except ImportError:
        pass

    # 2) ใช้ตัวเข้ารหัส ISO/IEC 18004 มาตรฐานใน reportlab.graphics.barcode.qrencoder
    try:
        from reportlab.graphics.barcode import qrencoder
        q = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
        q.addData(payload)
        q.make()
        modules = q.modules
        n = len(modules)
        if n <= 0:
            raise ValueError("ไม่สามารถสร้างตาราง QR ได้")
        total = (n + border * 2) * box_size
        img = Image.new("RGB", (total, total), "white")
        draw = ImageDraw.Draw(img)
        for r in range(n):
            for c in range(n):
                if modules[r][c]:
                    x0 = (c + border) * box_size
                    y0 = (r + border) * box_size
                    draw.rectangle([x0, y0, x0 + box_size - 1, y0 + box_size - 1], fill="black")
        return img
    except Exception as e:
        raise ValueError(f"สร้างภาพ QR Code ไม่สำเร็จ: {e}") from None


# ================================================================
# ส่วนที่ 1: QR สำหรับสแกนเข้าโต๊ะ (Table QR)
# ================================================================

def build_url(table_no: int, secret_key: str) -> str:
    """ลิงก์เต็มที่ใส่ใน QR ของโต๊ะ (ฐานลิงก์จากตั้งค่า public_base_url)"""
    base = (settings_service.get_setting("public_base_url", config.PUBLIC_BASE_URL) or "").rstrip("/")
    return base + config.QR_PATH_TEMPLATE.format(table_no=table_no, secret_key=secret_key)


def get_table_url(table_id: int) -> str:
    """ลิงก์ QR ของโต๊ะตาม id ; ValueError ถ้าไม่พบโต๊ะ"""
    t = table_service.get_table(table_id)
    if t is None:
        raise ValueError("ไม่พบโต๊ะ")
    return build_url(t["table_no"], t["secret_key"])


def verify_key(table_no: int, key: str) -> dict | None:
    """ตรวจเลขโต๊ะ+รหัสลับ -> dict โต๊ะ ถ้าถูกและโต๊ะเปิดใช้งาน ; None ถ้าผิด"""
    t = table_service.get_table_by_no(table_no)
    if t is None or not t["active"] or not key:
        return None
    return t if secrets.compare_digest(str(t["secret_key"]), str(key)) else None


def generate_qr_image(table_id: int, out_dir: Path | None = None) -> Path:
    """สร้างไฟล์ PNG ของ QR โต๊ะ -> พาธไฟล์ (assets/qr_codes/table_<เลข>.png)
    ValueError ถ้าไม่พบโต๊ะ"""
    t = table_service.get_table(table_id)
    if t is None:
        raise ValueError("ไม่พบโต๊ะ")
    out_dir = Path(out_dir) if out_dir else config.QR_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"table_{t['table_no']}.png"
    img = _render_qr_image(build_url(t["table_no"], t["secret_key"]))
    img.save(str(path), format="PNG")
    return path


def generate_all_qr(out_dir: Path | None = None) -> list[Path]:
    """สร้าง QR ของทุกโต๊ะที่เปิดใช้งาน -> list พาธไฟล์"""
    return [generate_qr_image(t["id"], out_dir) for t in table_service.list_tables()]


def resolve_scan(table_no: int, key: str, device_id: str, device_info: str | None = None) -> dict:
    """ลำดับสแกนตามกติกา: 1) ร้านปิด 2) รหัสผิด 3) สร้าง/ต่อรอบ pending
    -> {'ok': bool, 'code': str, 'message': str(ไทย), 'table': dict|None, 'session': dict|None}
    code: 'shop_closed' | 'invalid_qr' | 'table_busy' | 'ok'
    เครื่องเดิมสแกนซ้ำ = ได้รอบเดิมกลับ (code 'ok')"""
    if not shop_service.is_open():
        return {"ok": False, "code": "shop_closed", "message": "ร้านปิดอยู่", "table": None, "session": None}
    table = verify_key(table_no, key)
    if table is None:
        return {"ok": False, "code": "invalid_qr", "message": "QR ไม่ถูกต้อง", "table": None, "session": None}
    safe_table = {k: v for k, v in table.items() if k != "secret_key"}
    try:
        session = table_service.start_session(table["id"], device_id, device_info)
    except ValueError:
        return {"ok": False, "code": "table_busy", "message": "โต๊ะนี้มีลูกค้าใช้งานอยู่แล้ว",
                "table": safe_table, "session": None}
    return {"ok": True, "code": "ok", "message": "ส่งคำขอแล้ว รอพนักงานยืนยัน",
            "table": safe_table, "session": session}


# ================================================================
# ส่วนที่ 2: QR รับเงิน PromptPay มาตรฐาน EMVCo (แยกจาก QR โต๊ะ)
# ================================================================

def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(data: str | bytes) -> str:
    """คำนวณ CRC-16/CCITT-FALSE (polynomial 0x1021, initial 0xFFFF) สำหรับ EMVCo Tag 63"""
    raw = data.encode("ascii") if isinstance(data, str) else data
    crc = 0xFFFF
    for byte in raw:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def validate_promptpay_id(promptpay_id: str | None) -> tuple[str, str]:
    """ตรวจสอบหมายเลข PromptPay
    รองรับ:
    - เบอร์โทรศัพท์มือถือ 10 หลัก (ขึ้นต้นด้วย 0 เช่น 0123456789) -> ('01', '0066800000000')
    - เลขประจำตัวประชาชน/เลขผู้เสียภาษี 13 หลัก -> ('02', '<13 หลัก>')
    - e-Wallet ID 15 หลัก -> ('03', '<15 หลัก>')
    คืนค่า ( clean_display_id, emv_merchant_subtag_tlv ) ; ผิดรูปแบบ -> ValueError ภาษาไทย"""
    raw = (promptpay_id or "").strip().replace("-", "").replace(" ", "")
    if not raw:
        raise ValueError("กรุณาระบุหมายเลข PromptPay")
    if not raw.isdigit():
        raise ValueError("หมายเลข PromptPay ต้องเป็นตัวเลขเท่านั้น")
    if len(raw) == 10 and raw.startswith("0") and raw[1] in "689":
        formatted = "0066" + raw[1:]
        return raw, _tlv("01", formatted)
    if len(raw) == 13:
        return raw, _tlv("02", raw)
    if len(raw) == 15:
        return raw, _tlv("03", raw)
    raise ValueError(
        "รูปแบบหมายเลข PromptPay ไม่ถูกต้อง (ต้องเป็นเบอร์มือถือ 10 หลัก เช่น 0123456789 หรือเลขบัตรประชาชน 13 หลัก)"
    )


def _parse_promptpay_amount(amount) -> Decimal:
    if amount is None or isinstance(amount, bool):
        raise ValueError("กรุณาระบุยอดเงินสำหรับสร้าง QR PromptPay")
    try:
        dec = Decimal(str(amount).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        raise ValueError("ยอดเงินสำหรับสร้าง QR PromptPay ต้องเป็นตัวเลขที่ถูกต้อง") from None
    if not dec.is_finite() or dec <= 0:
        raise ValueError("ยอดเงินสำหรับสร้าง QR PromptPay ต้องมากกว่า 0")
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_promptpay_payload(amount, promptpay_id: str | None = None) -> str:
    """สร้าง EMVCo Payload มาตรฐาน PromptPay แบบระบุยอดเงิน (Tag 54)
    ValueError ถ้าหมายเลข PromptPay หรือยอดเงินไม่ถูกต้อง"""
    target_id = (
        promptpay_id
        if promptpay_id is not None
        else settings_service.get_setting("promptpay_id", config.DEFAULT_PROMPTPAY_ID)
    )
    _, subtag_tlv = validate_promptpay_id(target_id)
    amt_dec = _parse_promptpay_amount(amount)
    amt_str = f"{amt_dec:.2f}"

    merchant_info = _tlv("00", "A000000677010111") + subtag_tlv
    body = (
        _tlv("00", "01")                # Payload Format Indicator
        + _tlv("01", "12")              # Dynamic QR (มีระบุยอดเงิน)
        + _tlv("29", merchant_info)     # Merchant Account Information (PromptPay)
        + _tlv("58", "TH")              # Country Code
        + _tlv("53", "764")             # Currency (764 = THB)
        + _tlv("54", amt_str)           # Transaction Amount
        + "6304"                        # CRC Tag + Length
    )
    return body + crc16_ccitt(body)


def verify_promptpay_payload(payload: str, expected_amount=None) -> bool:
    """ตรวจสอบความถูกต้องของ EMVCo PromptPay payload (CRC16 และยอดเงิน Tag 54)"""
    if not payload or not isinstance(payload, str) or len(payload) < 20 or "6304" not in payload:
        return False
    body, crc_hex = payload[:-4], payload[-4:]
    if not body.endswith("6304"):
        return False
    if crc16_ccitt(body) != crc_hex.upper():
        return False
    if "A000000677010111" not in payload:
        return False
    if expected_amount is not None:
        amt_dec = _parse_promptpay_amount(expected_amount)
        expected_tag = _tlv("54", f"{amt_dec:.2f}")
        if expected_tag not in payload:
            return False
    return True


def get_promptpay_settings() -> dict:
    """คืนค่าตั้งค่า PromptPay ปัจจุบัน {'promptpay_id': str, 'promptpay_name': str}"""
    pp_id = (settings_service.get_setting("promptpay_id", config.DEFAULT_PROMPTPAY_ID) or "").strip()
    pp_name = (settings_service.get_setting("promptpay_name", config.DEFAULT_PROMPTPAY_NAME) or "").strip()
    return {"promptpay_id": pp_id, "promptpay_name": pp_name}


def generate_promptpay_qr(amount, promptpay_id: str | None = None,
                          promptpay_name: str | None = None,
                          out_path: Path | str | None = None) -> dict:
    """สร้างข้อมูลและรูปภาพ QR Code PromptPay สำหรับรับชำระเงินตามยอดสุทธิ
    คืน dict:
      - payload: EMVCo string
      - image: PIL.Image.Image
      - amount: float (2 ตำแหน่ง)
      - amount_text: '200.00'
      - promptpay_id: หมายเลขผู้รับ
      - promptpay_name: ชื่อบัญชีสำหรับให้พนักงานตรวจสอบ
      - status: 'awaiting_verification'
      - status_th: 'รอตรวจสอบการโอน'
    ValueError ถ้าหมายเลขหรือยอดเงินไม่ถูกต้อง หรือสร้างภาพไม่สำเร็จ"""
    cfg = get_promptpay_settings()
    raw_id = promptpay_id if promptpay_id is not None else cfg["promptpay_id"]
    clean_id, _ = validate_promptpay_id(raw_id)
    acc_name = (promptpay_name if promptpay_name is not None else cfg["promptpay_name"]).strip() or config.DEFAULT_PROMPTPAY_NAME
    amt_dec = _parse_promptpay_amount(amount)
    payload = build_promptpay_payload(amt_dec, promptpay_id=clean_id)
    if not verify_promptpay_payload(payload, expected_amount=amt_dec):
        raise ValueError("ตรวจสอบโครงสร้างข้อมูล PromptPay QR ไม่ผ่าน")

    img = _render_qr_image(payload, box_size=8, border=3)
    if img is None or img.width <= 0 or img.height <= 0:
        raise ValueError("ไม่สามารถสร้างภาพ QR PromptPay ได้")

    saved_path = None
    if out_path is not None:
        saved_path = Path(out_path)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(saved_path), format="PNG")

    return {
        "payload": payload,
        "image": img,
        "path": saved_path,
        "amount": float(amt_dec),
        "amount_text": f"{amt_dec:,.2f}",
        "promptpay_id": clean_id,
        "promptpay_name": acc_name,
        "status": "awaiting_verification",
        "status_th": "รอตรวจสอบการโอน",
    }
