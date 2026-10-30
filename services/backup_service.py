"""services/backup_service.py — สำรอง/กู้คืนฐานข้อมูล SQLite (ไฟล์เดียว tonmakha.db)

- สำรองด้วย sqlite3 backup API (ปลอดภัยแม้ฝั่งเว็บมือถือกำลังใช้ DB อยู่ / โหมด WAL) ได้ไฟล์ .db เดียวที่เปิดได้เลย
- ไฟล์อยู่ใน config.BACKUPS_DIR ชื่อ  tonmakha_<ชนิด>_<YYYYmmdd>_<HHMMSS>.db
  ชนิด: manual (เจ้าของกดเอง) | auto (สำรองอัตโนมัติรายวัน) | prerestore (สำรองกันพลาดอัตโนมัติก่อนกู้คืน)
- ชื่อไฟล์ที่รับจากผู้เรียกต้องเป็นไฟล์ในโฟลเดอร์สำรองที่ชื่อตรงรูปแบบข้างบนเท่านั้น (กัน path traversal)
- กู้คืน: ต้องปิดร้านและไม่มีรอบค้าง, ตรวจไฟล์ก่อน (integrity_check + มีครบ 17 ตาราง), สำรองสถานะปัจจุบันก่อนเสมอ,
  หลังกู้คืนตั้งร้านเป็น "ปิด" ; ควรให้ผู้ใช้รีสตาร์ตแอปหลังกู้คืน
"""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import config
from database import db, schema
from services import log_service

KINDS = ("manual", "auto", "prerestore")
KIND_TH = {"manual": "สำรองเอง", "auto": "สำรองอัตโนมัติ", "prerestore": "สำรองก่อนกู้คืน"}
DEFAULT_KEEP_AUTO = 14

_NAME_RE = re.compile(r"^tonmakha_(manual|auto|prerestore)_(\d{8})_(\d{6})(?:_(\d+))?\.db$")


# ---------------------------------------------------------------- ตัวช่วยภายใน

def _dir() -> Path:
    d = Path(config.BACKUPS_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _info(path: Path) -> dict:
    m = _NAME_RE.match(path.name)
    kind = m.group(1)
    created = datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S").strftime(db.TIME_FORMAT)
    return {"filename": path.name, "path": path, "kind": kind, "kind_th": KIND_TH[kind],
            "size_bytes": path.stat().st_size, "created_at": created}


def _safe_path(filename: str) -> Path:
    """ชื่อไฟล์ -> path ในโฟลเดอร์สำรอง ; ValueError ถ้าชื่อไม่ถูกต้อง/ไม่มีไฟล์"""
    if not isinstance(filename, str) or Path(filename).name != filename or not _NAME_RE.match(filename):
        raise ValueError("ชื่อไฟล์สำรองไม่ถูกต้อง")
    p = _dir() / filename
    if not p.is_file():
        raise ValueError("ไม่พบไฟล์สำรองนี้")
    return p


def _verify_file(path: Path) -> None:
    """ตรวจว่าเป็นฐานข้อมูลของแอปนี้และไม่เสียหาย ; ValueError ถ้าไม่ผ่าน"""
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("ไฟล์สำรองเสียหาย (integrity_check ไม่ผ่าน)")
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        raise ValueError("ไฟล์นี้ไม่ใช่ฐานข้อมูลที่ใช้ได้") from None
    missing = [t for t in schema.TABLE_NAMES if t not in names]
    if missing:
        raise ValueError("ไฟล์สำรองไม่ครบตาราง (ขาด: " + ", ".join(missing[:3]) + ("..." if len(missing) > 3 else "") + ")")


def _write_backup(kind: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = _dir()
    final, n = d / f"tonmakha_{kind}_{stamp}.db", 1
    while final.exists():
        n += 1
        final = d / f"tonmakha_{kind}_{stamp}_{n}.db"
    tmp = d / (final.name + ".tmp")
    src = db.get_connection()
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")  # ให้เป็นไฟล์เดียว ไม่มี -wal/-shm
            dst.commit()
        finally:
            dst.close()
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    tmp.replace(final)
    return final


# ---------------------------------------------------------------- สาธารณะ

def create_backup(user_id: int | None = None, kind: str = "manual") -> dict:
    """สำรองฐานข้อมูลตอนนี้ -> dict {filename, path, kind, kind_th, size_bytes, created_at} ; log 'backup_create'
    kind: 'manual' (ค่าเริ่มต้น) | 'auto' | 'prerestore'"""
    if kind not in KINDS:
        raise ValueError("ชนิดการสำรองไม่ถูกต้อง")
    path = _write_backup(kind)
    info = _info(path)
    log_service.log_action("backup_create", f"สำรองข้อมูล {path.name} ({info['size_bytes']:,} ไบต์)",
                           user_id=user_id, actor=None if user_id else "ระบบ", ref_type="backup")
    return info


def list_backups(kind: str | None = None) -> list[dict]:
    """ไฟล์สำรองทั้งหมด ใหม่สุดก่อน ; kind กรองชนิด ; แต่ละ dict เหมือน create_backup"""
    items = [_info(p) for p in _dir().iterdir() if p.is_file() and _NAME_RE.match(p.name)]
    if kind:
        items = [i for i in items if i["kind"] == kind]
    return sorted(items, key=lambda i: (i["created_at"], i["filename"]), reverse=True)


def delete_backup(filename: str, user_id: int | None = None) -> None:
    """ลบไฟล์สำรอง (log 'backup_delete') ; ValueError ถ้าชื่อไม่ถูกต้อง/ไม่พบ"""
    p = _safe_path(filename)
    p.unlink()
    log_service.log_action("backup_delete", f"ลบไฟล์สำรอง {filename}", user_id=user_id, ref_type="backup")


def prune_auto_backups(keep: int = DEFAULT_KEEP_AUTO) -> int:
    """เก็บไฟล์ auto ล่าสุด `keep` ไฟล์ ลบที่เก่ากว่า (ไม่แตะ manual/prerestore) -> จำนวนที่ลบ"""
    old = list_backups("auto")[max(0, keep):]
    for i in old:
        i["path"].unlink(missing_ok=True)
    if old:
        log_service.log_action("backup_prune", f"ลบไฟล์สำรองอัตโนมัติเก่า {len(old)} ไฟล์", actor="ระบบ",
                               ref_type="backup")
    return len(old)


def auto_backup(keep: int = DEFAULT_KEEP_AUTO) -> dict | None:
    """สำรองอัตโนมัติวันละครั้ง: ถ้าวันนี้ยังไม่มีไฟล์ auto -> สร้างแล้วคืน dict ; มีแล้ว -> None
    แล้วลบไฟล์ auto ที่เกิน `keep` ไฟล์ (main.py เรียกตอนเปิดแอป)"""
    today = datetime.now().strftime(db.TIME_FORMAT)[:10]
    if any(i["created_at"].startswith(today) for i in list_backups("auto")):
        return None
    info = create_backup(kind="auto")
    prune_auto_backups(keep)
    return info


def restore_backup(filename: str, user_id: int | None = None) -> dict:
    """กู้คืนฐานข้อมูลจากไฟล์สำรอง (เขียนทับข้อมูลปัจจุบันทั้งหมด!)
    -> dict ไฟล์ prerestore ที่สำรองไว้ก่อน (+ 'active_sessions' = จำนวนโต๊ะที่ยังค้าง pending/open/awaiting_payment
       อยู่ในข้อมูลที่กู้คืนมา — ถ้าไฟล์สำรองถูกสร้างตอนร้านเปิด ; UI ควรเตือนให้พนักงานเคลียร์ที่หน้าโต๊ะ)
    เงื่อนไข: ปิดร้านแล้วและไม่มีโต๊ะค้าง ; ไฟล์ต้องผ่านการตรวจ ; ValueError (ข้อความไทย) ถ้าไม่ผ่าน
    หลังกู้คืน: ร้านเป็น 'ปิด' + log 'backup_restore' (ลงฐานข้อมูลที่กู้คืนแล้ว) — ควรรีสตาร์ตแอป/เว็บ"""
    from services import shop_service
    p = _safe_path(filename)
    _verify_file(p)
    if shop_service.is_open():
        raise ValueError("กู้คืนไม่ได้ขณะร้านเปิด — ปิดร้านก่อน")
    if shop_service.active_session_count() > 0:
        raise ValueError("กู้คืนไม่ได้ — ยังมีโต๊ะค้างอยู่")
    safety = create_backup(user_id=user_id, kind="prerestore")
    src = sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True)
    dst = db.get_connection()
    try:
        src.backup(dst)
        dst.commit()
    finally:
        src.close()
        dst.close()
    now = db.now_str()
    db.execute("UPDATE shop_status SET is_open = 0, changed_at = ?, changed_by = ? WHERE id = 1",
               (now, user_id if user_id and db.query_one("SELECT 1 FROM users WHERE id = ?", (user_id,)) else None))
    log_service.log_action("backup_restore", f"กู้คืนข้อมูลจาก {filename} (สำรองก่อนกู้: {safety['filename']})",
                           user_id=user_id if user_id and db.query_one("SELECT 1 FROM users WHERE id = ?", (user_id,))
                           else None, actor=None if user_id else "ระบบ", ref_type="backup")
    safety["active_sessions"] = shop_service.active_session_count()
    return safety
