"""services/email_service.py — ระบบส่งอีเมลผ่าน SMTP มาตรฐาน (smtplib) และเทมเพลตอีเมลรหัส OTP สองภาษา

ข้อกำหนดด้านความปลอดภัย:
- รองรับพอร์ต 587 (STARTTLS) และ 465 (SSL) พร้อม timeout 15 วินาที
- ห้ามพิมพ์ ห้าม log หรือส่งคืนรหัสผ่าน SMTP หรือรหัส OTP ในข้อความผิดพลาดหรือ log เด็ดขาด
- เมื่อยังไม่ตั้งค่า SMTP หรือส่งไม่สำเร็จ ให้ raise ValueError("ส่งอีเมลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")
"""
from __future__ import annotations

from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import html
import logging
import re
import smtplib
import ssl

import config
from services import settings_service

logger = logging.getLogger("tonmakha.email")

SMTP_TIMEOUT_SECONDS = 15
GENERIC_EMAIL_ERROR_MSG = "ส่งอีเมลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"

_PURPOSE_META = {
    "signup": {
        "subject_th": "รหัส OTP ยืนยันการสมัครสมาชิก",
        "subject_en": "Your verification code",
        "title_th": "ยืนยันการสมัครสมาชิก",
        "desc_th": "กรุณานำรหัส OTP ด้านล่างไปกรอกในหน้าสมัครสมาชิกเพื่อยืนยันอีเมลของคุณ",
        "title_en": "Verify Your Membership Registration",
        "desc_en": "Please enter the verification code below on the sign-up page to verify your email address.",
    },
    "reset": {
        "subject_th": "รหัส OTP สำหรับตั้งรหัสผ่านใหม่",
        "subject_en": "Password reset verification code",
        "title_th": "ตั้งรหัสผ่านใหม่ (ลืมรหัสผ่าน)",
        "desc_th": "กรุณานำรหัส OTP ด้านล่างไปกรอกเพื่อยืนยันตัวตนและกำหนดรหัสผ่านใหม่ของคุณ",
        "title_en": "Reset Your Password",
        "desc_en": "Please enter the verification code below to verify your identity and set a new password.",
    },
}


def _strip_crlf(text: str) -> str:
    return re.sub(r"[\r\n]+", " ", str(text or "")).strip()


def _sanitize_error_for_log(exc: BaseException, redact_secrets: tuple[str, ...] = ()) -> str:
    """ล้างข้อมูลลับ (เช่น รหัสผ่าน SMTP หรือรหัส 6 หลัก) ออกจากข้อความ exception ก่อนเขียนลง server log"""
    raw = _strip_crlf(str(exc))
    for sec in redact_secrets:
        if sec and len(sec) >= 3:
            raw = raw.replace(sec, "***")
    # ซ่อนตัวเลข 6 หลักต่อเนื่องกันเผื่อกรณีข้อความสะท้อนเนื้อหา
    raw = re.sub(r"\b\d{6}\b", "***", raw)
    return raw[:300]


def is_smtp_configured() -> bool:
    """ตรวจสอบว่าตั้งค่า SMTP ครบถ้วนพร้อมส่งอีเมลจริงหรือไม่"""
    host = (getattr(config, "SMTP_HOST", "") or "").strip()
    port = int(getattr(config, "SMTP_PORT", 0) or 0)
    user = (getattr(config, "SMTP_USER", "") or "").strip()
    password = (getattr(config, "SMTP_PASSWORD", "") or "").strip()
    return bool(host and port > 0 and user and password)


def _get_shop_name() -> str:
    try:
        name = (settings_service.get_setting("shop_name", config.APP_NAME) or "").strip()
        if name:
            return _strip_crlf(name)
    except Exception:
        pass
    return _strip_crlf(config.APP_NAME)


def build_otp_email(
    otp_code: str,
    purpose: str = "signup",
    expires_minutes: int = 10,
    shop_name: str | None = None,
) -> tuple[str, str, str]:
    """สร้าง (subject, text_body, html_body) สำหรับอีเมล OTP ตามธีมร้านต้นมะค่า (สองภาษา ไทย-อังกฤษ)"""
    meta = _PURPOSE_META.get(purpose, _PURPOSE_META["signup"])
    resolved_shop = _strip_crlf(shop_name or _get_shop_name())
    clean_code = _strip_crlf(otp_code)
    exp_min = int(expires_minutes)

    subject = _strip_crlf(f"[{resolved_shop}] {meta['subject_th']} | {meta['subject_en']}")

    text_body = (
        f"{resolved_shop}\n"
        f"{meta['title_th']}\n\n"
        f"{meta['desc_th']}\n\n"
        f"รหัส OTP ของคุณคือ: {clean_code}\n"
        f"(รหัสนี้มีอายุการใช้งาน {exp_min} นาที)\n\n"
        f"คำเตือนความปลอดภัย:\n"
        f"- อย่าบอกรหัสนี้กับใคร ทางร้านจะไม่ขอรหัสทางโทรศัพท์หรือแชท\n"
        f"- หากคุณไม่ได้ทำรายการนี้ กรุณาเพิกเฉยต่ออีเมลฉบับนี้\n\n"
        f"----------------------------------------\n"
        f"{meta['title_en']}\n"
        f"{meta['desc_en']}\n"
        f"Your verification code is: {clean_code} (valid for {exp_min} minutes).\n"
        f"Never share this code with anyone. Our staff will never ask for this code via phone or chat.\n"
        f"If you did not request this code, please ignore this email.\n"
    )

    esc_shop = html.escape(resolved_shop, quote=True)
    esc_title_th = html.escape(meta["title_th"], quote=True)
    esc_desc_th = html.escape(meta["desc_th"], quote=True)
    esc_title_en = html.escape(meta["title_en"], quote=True)
    esc_desc_en = html.escape(meta["desc_en"], quote=True)
    esc_code = html.escape(clean_code, quote=True)
    esc_exp = html.escape(str(exp_min), quote=True)

    html_body = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(subject, quote=True)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f6f1ea;font-family:'Prompt',Tahoma,Arial,sans-serif;color:#2b2118;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f6f1ea;padding:24px 12px;">
  <tr>
    <td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;background-color:#ffffff;border:1px solid #e6dccd;border-radius:12px;overflow:hidden;">
        <tr>
          <td style="background-color:#2b2118;padding:20px 24px;text-align:center;">
            <div style="font-size:20px;font-weight:700;color:#e8590c;line-height:1.4;">{esc_shop}</div>
            <div style="font-size:14px;color:#fff7ed;margin-top:4px;line-height:1.4;">{esc_title_th}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:24px;background-color:#ffffff;color:#2b2118;">
            <p style="margin:0 0 16px 0;font-size:15px;line-height:1.6;color:#2b2118;">{esc_desc_th}</p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:16px 0;">
              <tr>
                <td align="center" style="background-color:#fff7ed;border:2px solid #e8590c;border-radius:8px;padding:16px;">
                  <div style="font-size:12px;color:#7a6d60;margin-bottom:4px;">รหัสยืนยันตัวตน (OTP)</div>
                  <div style="font-size:32px;font-weight:700;letter-spacing:8px;color:#2b2118;font-family:'Prompt',monospace;">{esc_code}</div>
                  <div style="font-size:13px;color:#e8590c;font-weight:600;margin-top:8px;">รหัสมีอายุการใช้งาน {esc_exp} นาที</div>
                </td>
              </tr>
            </table>
            <div style="background-color:#faf6f0;border-left:4px solid #e8590c;padding:12px 16px;border-radius:6px;margin:16px 0;">
              <p style="margin:0 0 6px 0;font-size:13px;line-height:1.5;color:#2b2118;font-weight:600;">
                อย่าบอกรหัสนี้กับใคร ทางร้านจะไม่ขอรหัสทางโทรศัพท์หรือแชท
              </p>
              <p style="margin:0;font-size:13px;line-height:1.5;color:#7a6d60;">
                หากคุณไม่ได้ทำรายการนี้ กรุณาเพิกเฉย
              </p>
            </div>
            <hr style="border:none;border-top:1px solid #e6dccd;margin:20px 0;">
            <div style="font-size:12px;line-height:1.5;color:#7a6d60;">
              <div style="font-weight:600;color:#2b2118;margin-bottom:4px;">{esc_title_en}</div>
              <p style="margin:0 0 8px 0;">{esc_desc_en}</p>
              <p style="margin:0 0 4px 0;">This verification code expires in <strong>{esc_exp} minutes</strong>.</p>
              <p style="margin:0;">Never share this code with anyone. Our staff will never ask for this code via phone or chat. If you did not request this, please ignore this email.</p>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""
    return subject, text_body, html_body


def send_mail(to_email: str, subject: str, text: str, html: str | None = None) -> None:
    """ส่งอีเมลผ่าน SMTP (พอร์ต 587 STARTTLS หรือ 465 SSL, timeout 15 วินาที)
    หากยังไม่ตั้งค่า SMTP หรือเกิดข้อผิดพลาด จะ log ชนิด exception และ raise ValueError ข้อความไทยกลาง ๆ
    """
    clean_to = _strip_crlf(to_email)
    clean_subject = _strip_crlf(subject)
    if not clean_to or "@" not in clean_to:
        raise ValueError(GENERIC_EMAIL_ERROR_MSG)

    if not is_smtp_configured():
        logger.warning("SMTPError [NotConfigured]: ยังไม่ได้ตั้งค่า SMTP_USER หรือ SMTP_PASSWORD")
        raise ValueError(GENERIC_EMAIL_ERROR_MSG)

    host = _strip_crlf(getattr(config, "SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com")
    port = int(getattr(config, "SMTP_PORT", 587) or 587)
    user = _strip_crlf(getattr(config, "SMTP_USER", ""))
    password = getattr(config, "SMTP_PASSWORD", "") or ""
    from_addr = _strip_crlf(getattr(config, "SMTP_FROM", "") or user)
    from_name = _strip_crlf(getattr(config, "SMTP_FROM_NAME", "") or _get_shop_name())

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(clean_subject, "utf-8")
    msg["From"] = formataddr((str(Header(from_name, "utf-8")), from_addr))
    msg["To"] = clean_to

    msg.attach(MIMEText(text or "", "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS, context=context) as server:
                server.ehlo()
                server.login(user, password)
                server.sendmail(from_addr, [clean_to], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.sendmail(from_addr, [clean_to], msg.as_string())
    except Exception as exc:
        safe_err = _sanitize_error_for_log(exc, redact_secrets=(password, user))
        logger.warning("SMTP send failed [%s]: %s", exc.__class__.__name__, safe_err)
        raise ValueError(GENERIC_EMAIL_ERROR_MSG) from None


def send_otp_email(
    to_email: str,
    otp_code: str,
    purpose: str = "signup",
    expires_minutes: int = 10,
) -> None:
    """สร้างอีเมล OTP จากเทมเพลตของร้านแล้วส่งผ่าน send_mail()"""
    subject, text_body, html_body = build_otp_email(
        otp_code=otp_code,
        purpose=purpose,
        expires_minutes=expires_minutes,
    )
    send_mail(to_email, subject, text_body, html=html_body)
