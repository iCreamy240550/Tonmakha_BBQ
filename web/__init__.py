"""แพ็กเกจเว็บลูกค้า — คง web/session.py ไว้สำหรับระบบตะกร้าและรอบโต๊ะ
ส่วนโค้ด NiceGUI/CustomTkinter เดิมถูกย้ายไปเก็บไว้ใน legacy/ เพื่อเทียบอ้างอิง"""
from pathlib import Path
import sys

_LEGACY_DIR = Path(__file__).resolve().parent.parent / "legacy"
if _LEGACY_DIR.is_dir():
    _legacy_str = str(_LEGACY_DIR)
    if _legacy_str not in sys.path:
        sys.path.append(_legacy_str)
    _legacy_web = str(_LEGACY_DIR / "web")
    if _legacy_web not in __path__:
        __path__.append(_legacy_web)
