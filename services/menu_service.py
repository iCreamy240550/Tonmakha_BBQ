"""services/menu_service.py — หมวดเมนู, เมนู, ราคา, สถานะหมด, รูปภาพเมนู, การลบเมนูอย่างปลอดภัย

item_type: 'weighed' (ชั่งกิโล ราคา = บาท/กก.) หรือ 'normal' (ปกติ ราคา = บาท/หน่วย)
เมนูหมด: พนักงานกดเอง (set_sold_out) หรือหมดอัตโนมัติเมื่อสต๊อกที่ผูกไว้เป็น 0 (stock_service เรียก)
เมื่อเมนูเปลี่ยนเป็นหมด จะส่งข้อความแจ้งทุกโต๊ะที่กำลังใช้งาน
รูปภาพเมนู: รองรับ JPG/JPEG, PNG, WebP ขนาดไม่เกิน 5 MB ปรับสัดส่วน 1:1 (square) อัตโนมัติ เก็บใน assets/uploads/menu/
การลบเมนู: ตรวจสอบความสัมพันธ์กับประวัติการขาย/ออเดอร์/รายการชั่งน้ำหนักก่อนลบ หากไม่มีประวัติอ้างอิงจะลบจริง หากมีประวัติจะทำ soft delete (active=0) เพื่อรักษาประวัติการขายเก่า
ข้อผิดพลาดตามกติกา -> ValueError ข้อความไทย
"""
from io import BytesIO
from pathlib import Path
import secrets

from PIL import Image, ImageOps, UnidentifiedImageError

import config
from database import db
from services import auth_service, log_service, notice_service

_UNSET = object()
_TYPES = (config.MENU_TYPE_WEIGHED, config.MENU_TYPE_NORMAL)
_ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

_ITEM_SELECT = (
    "SELECT m.*, c.name AS category_name, "
    "s.quantity AS stock_quantity, s.unit AS stock_unit, s.name AS stock_name, s.active AS stock_active "
    "FROM menu_items m "
    "JOIN menu_categories c ON c.id = m.category_id "
    "LEFT JOIN stock_items s ON s.id = m.stock_item_id"
)


def _check_price(price) -> float:
    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValueError("ราคาต้องเป็นตัวเลข")
    if price < 0:
        raise ValueError("ราคาต้องไม่ติดลบ")
    return round(price, 2)


def _fmt_qty(value: float | int | None) -> str:
    if value is None:
        return "0"
    v = max(0.0, float(value))
    if v == int(v):
        return str(int(v))
    return f"{v:,.3f}".rstrip("0").rstrip(".")


def resolve_image_file(image_path: str | None) -> Path | None:
    """คืน Path ของไฟล์รูปภาพที่มีอยู่จริงในโฟลเดอร์ assets/uploads เท่านั้น ; ถ้าไม่มีหรือไฟล์หาย คืน None"""
    if not image_path or not isinstance(image_path, str):
        return None
    clean = image_path.strip().lstrip("/\\")
    if not clean:
        return None
    try:
        full = (config.ASSETS_DIR / clean).resolve()
        uploads_root = config.UPLOADS_DIR.resolve()
        if not str(full).startswith(str(uploads_root)):
            return None
        return full if full.is_file() else None
    except OSError:
        return None


def get_item_image_file(item_or_id) -> Path | None:
    """รับ dict เมนู หรือ item_id -> Path รูปภาพที่มีอยู่จริง หรือ None"""
    if isinstance(item_or_id, int):
        item = get_item(item_or_id)
        return resolve_image_file(item.get("image_path") if item else None)
    if isinstance(item_or_id, dict):
        return resolve_image_file(item_or_id.get("image_path"))
    return None


def _item(row) -> dict:
    d = dict(row)
    has_stock = d.get("stock_item_id") is not None
    raw_qty = d.get("stock_quantity")
    stock_qty = max(0.0, float(raw_qty)) if (has_stock and raw_qty is not None) else (0.0 if has_stock else None)
    stock_unit = (d.get("stock_unit") or "").strip() if has_stock else None
    sold_out = bool(d["is_sold_out"]) or (has_stock and (stock_qty is None or stock_qty <= 0))

    d["is_sold_out"] = sold_out
    d["manual_sold_out"] = bool(row["is_sold_out"])
    d["active"] = bool(d["active"])
    d["stock_quantity"] = stock_qty
    d["stock_unit"] = stock_unit

    # ข้อความสต๊อกคงเหลือสำหรับแสดงผล
    if sold_out:
        d["stock_text"] = f"คงเหลือ 0 {stock_unit}".strip() if stock_unit else "คงเหลือ 0"
    elif stock_qty is not None:
        qty_txt = _fmt_qty(stock_qty)
        d["stock_text"] = f"คงเหลือ {qty_txt} {stock_unit}".strip() if stock_unit else f"คงเหลือ {qty_txt}"
    else:
        d["stock_text"] = "พร้อมจำหน่าย"

    img_file = resolve_image_file(d.get("image_path"))
    d["has_image"] = img_file is not None
    d["image_url"] = f"/{d['image_path'].lstrip('/')}" if img_file is not None else None
    if img_file is None:
        d["image_path"] = None
    return d


def _require_owner(user_id: int | None, action_desc: str = "จัดการรูปภาพเมนู") -> None:
    if user_id is not None:
        user = auth_service.get_user(user_id)
        if user is None or not auth_service.is_owner(user):
            raise ValueError(f"เฉพาะเจ้าของร้านเท่านั้นที่สามารถ{action_desc}ได้")


def _cleanup_unused_image_file(image_path: str | None, exclude_item_id: int | None = None, conn=None) -> None:
    """ลบไฟล์รูปออกจากดิสก์อย่างปลอดภัย เฉพาะเมื่อไม่มีเมนูอื่นใช้งานไฟล์นี้อยู่"""
    if not image_path:
        return
    if exclude_item_id is not None:
        in_use = db.query_one(
            "SELECT 1 FROM menu_items WHERE image_path = ? AND id != ? LIMIT 1",
            (image_path, exclude_item_id), conn=conn,
        )
    else:
        in_use = db.query_one(
            "SELECT 1 FROM menu_items WHERE image_path = ? LIMIT 1",
            (image_path,), conn=conn,
        )
    if in_use is not None:
        return
    full = resolve_image_file(image_path)
    if full is not None:
        try:
            full.unlink(missing_ok=True)
        except OSError:
            pass


def _process_and_store_image(item_id: int, source, original_filename: str | None = None) -> str:
    """ตรวจสอบชนิดไฟล์/ขนาดไฟล์ ปรับขนาด 1:1 (square) โดยไม่บิดสัดส่วน แล้วบันทึกเป็นชื่อไฟล์ปลอดภัย
    คืนค่า relative path เช่น 'uploads/menu/menu_1_a1b2c3d4e5f6.png'"""
    raw_bytes: bytes
    ext_hint = ""
    if isinstance(source, (str, Path)):
        src_path = Path(source)
        if not src_path.exists() or not src_path.is_file():
            raise ValueError("ไม่พบไฟล์รูปภาพที่เลือก")
        ext_hint = (original_filename or src_path.name).lower()
        size = src_path.stat().st_size
        if size <= 0:
            raise ValueError("ไฟล์รูปภาพว่างเปล่า")
        if size > config.MAX_IMAGE_SIZE_BYTES:
            raise ValueError(f"ไฟล์รูปภาพมีขนาดใหญ่เกินกำหนด (สูงสุดไม่เกิน {config.MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB)")
        raw_bytes = src_path.read_bytes()
    elif isinstance(source, (bytes, bytearray)):
        ext_hint = (original_filename or "").lower()
        if len(source) <= 0:
            raise ValueError("ไฟล์รูปภาพว่างเปล่า")
        if len(source) > config.MAX_IMAGE_SIZE_BYTES:
            raise ValueError(f"ไฟล์รูปภาพมีขนาดใหญ่เกินกำหนด (สูงสุดไม่เกิน {config.MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB)")
        raw_bytes = bytes(source)
    else:
        raise ValueError("รูปแบบข้อมูลรูปภาพไม่ถูกต้อง")

    if ext_hint and "." in ext_hint:
        suffix = "." + ext_hint.rsplit(".", 1)[-1]
        if suffix not in config.ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError("นามสกุลไฟล์ไม่รองรับ (รองรับเฉพาะ JPG, JPEG, PNG และ WebP)")

    try:
        with Image.open(BytesIO(raw_bytes)) as probe:
            fmt = (probe.format or "").upper()
            probe.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("ไฟล์รูปภาพไม่ถูกต้องหรือเสียหาย (รองรับเฉพาะ JPG, PNG และ WebP)") from None

    if fmt not in _ALLOWED_FORMATS:
        raise ValueError("ชนิดไฟล์รูปภาพไม่รองรับ (รองรับเฉพาะ JPG, PNG และ WebP)")

    try:
        with Image.open(BytesIO(raw_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            if img.width <= 0 or img.height <= 0:
                raise ValueError("ขนาดรูปภาพไม่ถูกต้อง")
            dim = min(config.MENU_IMAGE_MAX_DIM, max(64, min(img.width, img.height)))
            if fmt == "JPEG":
                img = img.convert("RGB")
                out_ext = ".jpg"
                save_fmt = "JPEG"
                save_kwargs = {"quality": 88, "optimize": True}
            elif fmt == "WEBP":
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                out_ext = ".webp"
                save_fmt = "WEBP"
                save_kwargs = {"quality": 88}
            else:
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                out_ext = ".png"
                save_fmt = "PNG"
                save_kwargs = {"optimize": True}

            square = ImageOps.fit(img, (dim, dim), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            config.MENU_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = f"menu_{int(item_id)}_{secrets.token_hex(8)}{out_ext}"
            dest_path = config.MENU_IMAGE_DIR / safe_name
            square.save(str(dest_path), format=save_fmt, **save_kwargs)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"ประมวลผลรูปภาพไม่สำเร็จ: {e}") from None

    return f"uploads/menu/{safe_name}"


# ---------------------------------------------------------------- หมวด

def list_categories(include_inactive: bool = False) -> list[dict]:
    """หมวดเรียงตาม sort_order"""
    sql = "SELECT * FROM menu_categories" + ("" if include_inactive else " WHERE active = 1") + " ORDER BY sort_order, id"
    return [dict(r) for r in db.query_all(sql)]


def add_category(name: str, sort_order: int | None = None, user_id: int | None = None) -> dict:
    """เพิ่มหมวด -> dict ; ValueError ถ้าชื่อว่าง"""
    name = (name or "").strip()
    if not name:
        raise ValueError("กรุณากรอกชื่อหมวด")
    with db.transaction() as conn:
        if sort_order is None:
            sort_order = db.query_one("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM menu_categories", conn=conn)["n"]
        cid = db.execute("INSERT INTO menu_categories (name, sort_order, active) VALUES (?, ?, 1)",
                         (name, sort_order), conn=conn)
        log_service.log_action("menu_category_add", f"เพิ่มหมวด {name}", user_id=user_id,
                               ref_type="menu_category", ref_id=cid, conn=conn)
    return dict(db.query_one("SELECT * FROM menu_categories WHERE id = ?", (cid,)))


def update_category(category_id: int, name: str | None = None, sort_order: int | None = None,
                    active: bool | None = None, user_id: int | None = None) -> dict:
    """แก้ชื่อ/ลำดับ/เปิด-ปิดหมวด (ส่งเฉพาะที่จะแก้) ; ValueError ถ้าไม่พบ"""
    with db.transaction() as conn:
        c = db.query_one("SELECT * FROM menu_categories WHERE id = ?", (category_id,), conn=conn)
        if c is None:
            raise ValueError("ไม่พบหมวดนี้")
        new = (((name or "").strip() or c["name"]), c["sort_order"] if sort_order is None else sort_order,
               c["active"] if active is None else (1 if active else 0))
        db.execute("UPDATE menu_categories SET name=?, sort_order=?, active=? WHERE id=?", (*new, category_id), conn=conn)
        log_service.log_action("menu_category_update", f"แก้หมวด {c['name']}: ชื่อ={new[0]}, ใช้งาน={new[2]}",
                               user_id=user_id, ref_type="menu_category", ref_id=category_id, conn=conn)
    return dict(db.query_one("SELECT * FROM menu_categories WHERE id = ?", (category_id,)))


# ---------------------------------------------------------------- เมนู

def get_item(item_id: int, conn=None) -> dict | None:
    """เมนูตาม id -> dict หรือ None"""
    row = db.query_one(_ITEM_SELECT + " WHERE m.id = ?", (item_id,), conn=conn)
    return _item(row) if row else None


def list_items(category_id: int | None = None, include_inactive: bool = False) -> list[dict]:
    """เมนูเรียงตามหมวด/ลำดับ (+ category_name, stock_quantity, stock_unit, image_path)"""
    where, params = [], []
    if category_id is not None:
        where.append("m.category_id = ?")
        params.append(category_id)
    if not include_inactive:
        where.append("m.active = 1")
    sql = (_ITEM_SELECT
           + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY c.sort_order, c.id, m.sort_order, m.id")
    return [_item(r) for r in db.query_all(sql, tuple(params))]


def get_menu_for_customer() -> list[dict]:
    """เมนูสำหรับหน้าลูกค้า: หมวดที่เปิด + เมนูที่เปิด (รวมที่หมด ให้ UI แสดงว่า 'สินค้าหมด')
    -> [{'id','name','items':[{'id','name','item_type','price','is_sold_out','stock_item_id',
         'stock_quantity','stock_unit','stock_text','image_path','image_url','has_image'}]}]"""
    keys = (
        "id", "name", "item_type", "price", "is_sold_out",
        "stock_item_id", "stock_quantity", "stock_unit", "stock_text",
        "image_path", "image_url", "has_image",
    )
    result = []
    for cat in list_categories():
        items = [{k: it.get(k) for k in keys} for it in list_items(cat["id"])]
        if items:
            result.append({"id": cat["id"], "name": cat["name"], "items": items})
    return result


def add_item(category_id: int, name: str, item_type: str, price, stock_item_id: int | None = None,
             sort_order: int | None = None, image_source=None, user_id: int | None = None) -> dict:
    """เพิ่มเมนู -> dict ; ValueError ถ้าข้อมูลไม่ถูกต้อง/ไม่พบหมวด/ไม่พบสต๊อก"""
    name = (name or "").strip()
    if not name:
        raise ValueError("กรุณากรอกชื่อเมนู")
    if item_type not in _TYPES:
        raise ValueError("ประเภทเมนูไม่ถูกต้อง")
    price = _check_price(price)
    if image_source is not None:
        _require_owner(user_id)
    with db.transaction() as conn:
        if db.query_one("SELECT 1 FROM menu_categories WHERE id = ?", (category_id,), conn=conn) is None:
            raise ValueError("ไม่พบหมวดนี้")
        if stock_item_id is not None and db.query_one("SELECT 1 FROM stock_items WHERE id = ?", (stock_item_id,), conn=conn) is None:
            raise ValueError("ไม่พบรายการสต๊อกที่ผูก")
        if sort_order is None:
            sort_order = db.query_one("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM menu_items WHERE category_id = ?",
                                      (category_id,), conn=conn)["n"]
        iid = db.execute(
            "INSERT INTO menu_items (category_id, name, item_type, price, is_sold_out, stock_item_id, sort_order, active) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, 1)", (category_id, name, item_type, price, stock_item_id, sort_order), conn=conn)
        if image_source is not None:
            rel_path = _process_and_store_image(iid, image_source)
            db.execute("UPDATE menu_items SET image_path = ? WHERE id = ?", (rel_path, iid), conn=conn)
            log_service.log_action("menu_image_update", f"อัปโหลดรูปเมนู {name}", user_id=user_id,
                                   ref_type="menu_item", ref_id=iid, conn=conn)
        log_service.log_action("menu_item_add", f"เพิ่มเมนู {name} ราคา {price:g}", user_id=user_id,
                               ref_type="menu_item", ref_id=iid, conn=conn)
    return get_item(iid)


def update_item(item_id: int, name=_UNSET, price=_UNSET, category_id=_UNSET, stock_item_id=_UNSET,
                active=_UNSET, sort_order=_UNSET, image_source=_UNSET, user_id: int | None = None) -> dict:
    """แก้เมนู (ส่งเฉพาะฟิลด์ที่จะแก้ ; stock_item_id=None = เลิกผูกสต๊อก ; image_source=None = ลบรูป)
    log การแก้ราคาและรูปแยกต่างหาก ; ValueError ถ้าไม่พบเมนู/ข้อมูลผิด"""
    if image_source is not _UNSET:
        _require_owner(user_id)
    with db.transaction() as conn:
        m = db.query_one("SELECT * FROM menu_items WHERE id = ?", (item_id,), conn=conn)
        if m is None:
            raise ValueError("ไม่พบเมนูนี้")
        new_name = m["name"] if name is _UNSET else ((name or "").strip() or m["name"])
        new_price = m["price"] if price is _UNSET else _check_price(price)
        new_cat = m["category_id"] if category_id is _UNSET else category_id
        new_stock = m["stock_item_id"] if stock_item_id is _UNSET else stock_item_id
        new_active = m["active"] if active is _UNSET else (1 if active else 0)
        new_sort = m["sort_order"] if sort_order is _UNSET else sort_order
        if db.query_one("SELECT 1 FROM menu_categories WHERE id = ?", (new_cat,), conn=conn) is None:
            raise ValueError("ไม่พบหมวดนี้")
        if new_stock is not None and db.query_one("SELECT 1 FROM stock_items WHERE id = ?", (new_stock,), conn=conn) is None:
            raise ValueError("ไม่พบรายการสต๊อกที่ผูก")

        old_img = m["image_path"]
        new_img = old_img
        if image_source is None:
            new_img = None
        elif image_source is not _UNSET:
            new_img = _process_and_store_image(item_id, image_source)

        db.execute(
            "UPDATE menu_items SET name=?, price=?, category_id=?, stock_item_id=?, image_path=?, active=?, sort_order=? WHERE id=?",
            (new_name, new_price, new_cat, new_stock, new_img, new_active, new_sort, item_id), conn=conn,
        )
        if image_source is not _UNSET and old_img and old_img != new_img:
            _cleanup_unused_image_file(old_img, exclude_item_id=item_id, conn=conn)
        if image_source is None and old_img:
            log_service.log_action("menu_image_delete", f"ลบรูปเมนู {new_name}", user_id=user_id,
                                   ref_type="menu_item", ref_id=item_id, conn=conn)
        elif image_source not in (_UNSET, None):
            log_service.log_action("menu_image_update", f"อัปเดตรูปเมนู {new_name}", user_id=user_id,
                                   ref_type="menu_item", ref_id=item_id, conn=conn)
        if new_price != m["price"]:
            log_service.log_action("menu_price_change", f"แก้ราคา {m['name']}: {m['price']:g} -> {new_price:g}",
                                   user_id=user_id, ref_type="menu_item", ref_id=item_id, conn=conn)
        log_service.log_action("menu_item_update", f"แก้เมนู {m['name']}: ชื่อ={new_name}, ใช้งาน={new_active}",
                               user_id=user_id, ref_type="menu_item", ref_id=item_id, conn=conn)
    return get_item(item_id)


def set_item_image(item_id: int, source, original_filename: str | None = None,
                   user_id: int | None = None) -> dict:
    """อัปโหลด/เปลี่ยนรูปของเมนู (เฉพาะเจ้าของร้าน) -> dict เมนู"""
    _require_owner(user_id)
    with db.transaction() as conn:
        m = db.query_one("SELECT * FROM menu_items WHERE id = ?", (item_id,), conn=conn)
        if m is None:
            raise ValueError("ไม่พบเมนูนี้")
        old_img = m["image_path"]
        new_img = _process_and_store_image(item_id, source, original_filename=original_filename)
        db.execute("UPDATE menu_items SET image_path = ? WHERE id = ?", (new_img, item_id), conn=conn)
        if old_img and old_img != new_img:
            _cleanup_unused_image_file(old_img, exclude_item_id=item_id, conn=conn)
        log_service.log_action("menu_image_update", f"อัปเดตรูปเมนู {m['name']}", user_id=user_id,
                               ref_type="menu_item", ref_id=item_id, conn=conn)
    return get_item(item_id)


def delete_item_image(item_id: int, user_id: int | None = None) -> dict:
    """ลบรูปของเมนูอย่างปลอดภัย (ไม่ลบไฟล์หากเมนูอื่นยังอ้างอิงอยู่) -> dict เมนู"""
    _require_owner(user_id)
    with db.transaction() as conn:
        m = db.query_one("SELECT * FROM menu_items WHERE id = ?", (item_id,), conn=conn)
        if m is None:
            raise ValueError("ไม่พบเมนูนี้")
        old_img = m["image_path"]
        if old_img:
            db.execute("UPDATE menu_items SET image_path = NULL WHERE id = ?", (item_id,), conn=conn)
            _cleanup_unused_image_file(old_img, exclude_item_id=item_id, conn=conn)
            log_service.log_action("menu_image_delete", f"ลบรูปเมนู {m['name']}", user_id=user_id,
                                   ref_type="menu_item", ref_id=item_id, conn=conn)
    return get_item(item_id)


def get_delete_impact(item_id: int, conn=None) -> dict:
    """ตรวจสอบความสัมพันธ์ของเมนูกับรายการออเดอร์และรายการชั่งน้ำหนักก่อนลบ
    -> {'menu_item': dict, 'order_refs': int, 'weigh_refs': int, 'can_hard_delete': bool, 'impact_text': str}"""
    item = get_item(item_id, conn=conn)
    if item is None:
        raise ValueError("ไม่พบเมนูนี้")
    order_refs = db.query_one(
        "SELECT COUNT(*) AS c FROM order_items WHERE menu_item_id = ?",
        (item_id,), conn=conn,
    )["c"]
    weigh_refs = db.query_one(
        "SELECT COUNT(*) AS c FROM weigh_entries WHERE menu_item_id = ?",
        (item_id,), conn=conn,
    )["c"]
    can_hard_delete = (order_refs == 0 and weigh_refs == 0)
    parts = []
    if order_refs:
        parts.append(f"รายการสั่งอาหาร {order_refs} รายการ")
    if weigh_refs:
        parts.append(f"รายการชั่งน้ำหนัก {weigh_refs} รายการ")
    if can_hard_delete:
        impact_text = f"เมนู \"{item['name']}\" ยังไม่มีประวัติการสั่งหรือการชั่ง ระบบจะลบออกจากฐานข้อมูลอย่างถาวร"
    else:
        impact_text = (
            f"เมนู \"{item['name']}\" มีข้อมูลอ้างอิงในประวัติการขาย (" + " · ".join(parts) + ")\n"
            "เพื่อไม่ให้ข้อมูลการขายเก่าและรายละเอียดในบิลเสียหาย ระบบจะปิดใช้งาน (Soft Delete) เมนูนี้แทนการลบถาวร"
        )
    return {
        "menu_item": item,
        "order_refs": order_refs,
        "weigh_refs": weigh_refs,
        "can_hard_delete": can_hard_delete,
        "impact_text": impact_text,
    }


def delete_item(item_id: int, user_id: int | None = None, allow_soft_delete: bool = True) -> dict:
    """ลบรายการเมนูออกจากระบบ (เฉพาะเจ้าของร้าน):
    - หากเมนูไม่ถูกอ้างอิงในประวัติออเดอร์/รายการชั่ง จะลบจริงออกจากตาราง menu_items และลบรูปภาพที่ไม่ใช้แล้ว
    - หากเมนูถูกอ้างอิงในประวัติการขายเก่า จะใช้วิธี soft delete (ตั้ง active = 0) เพื่อรักษาความสมบูรณ์ของบิลและรายงานย้อนหลัง"""
    _require_owner(user_id, "ลบรายการเมนู")
    with db.transaction() as conn:
        impact = get_delete_impact(item_id, conn=conn)
        item = impact["menu_item"]
        raw_row = db.query_one("SELECT image_path FROM menu_items WHERE id = ?", (item_id,), conn=conn)
        old_img = raw_row["image_path"] if raw_row else None

        if impact["can_hard_delete"]:
            db.execute("DELETE FROM menu_items WHERE id = ?", (item_id,), conn=conn)
            if old_img:
                _cleanup_unused_image_file(old_img, exclude_item_id=item_id, conn=conn)
            log_service.log_action(
                "menu_item_delete",
                f"ลบเมนู {item['name']} ถาวร",
                user_id=user_id, ref_type="menu_item", ref_id=item_id, conn=conn,
            )
            return {
                "id": item_id,
                "name": item["name"],
                "action": "deleted",
                "deleted": True,
                "soft_deleted": False,
                "message": f"ลบเมนู \"{item['name']}\" เรียบร้อยแล้ว",
            }

        reason_parts = []
        if impact["order_refs"]:
            reason_parts.append(f"ออเดอร์ {impact['order_refs']} รายการ")
        if impact["weigh_refs"]:
            reason_parts.append(f"รายการชั่ง {impact['weigh_refs']} รายการ")
        reason_str = ", ".join(reason_parts)

        if not allow_soft_delete:
            raise ValueError(
                f"ไม่สามารถลบเมนู \"{item['name']}\" แบบถาวรได้ เนื่องจากมีประวัติการขายอ้างอิง ({reason_str})"
            )

        db.execute(
            "UPDATE menu_items SET active = 0, is_sold_out = 1 WHERE id = ?",
            (item_id,), conn=conn,
        )
        log_service.log_action(
            "menu_item_delete",
            f"ปิดใช้งานเมนู {item['name']} แทนการลบถาวรเพื่อรักษาประวัติการขาย ({reason_str})",
            user_id=user_id, ref_type="menu_item", ref_id=item_id, conn=conn,
        )
        return {
            "id": item_id,
            "name": item["name"],
            "action": "soft_deleted",
            "deleted": False,
            "soft_deleted": True,
            "message": f"เมนู \"{item['name']}\" มีประวัติการขายอ้างอิง ({reason_str}) ระบบจึงนำออกจากรายการขายและเก็บประวัติเดิมไว้",
        }


def set_sold_out(item_id: int, sold_out: bool, user_id: int | None = None,
                 auto: bool = False, conn=None) -> bool:
    """ตั้ง/ยกเลิกสถานะหมด -> True ถ้าสถานะเปลี่ยนจริง (เหมือนเดิม = False ไม่ log)
    เมื่อเปลี่ยนเป็นหมด ส่งข้อความแจ้งทุกโต๊ะที่ใช้งาน ; auto=True = ระบบตั้งเองจากสต๊อก 0
    ValueError ถ้าไม่พบเมนู"""
    def _do(c) -> bool:
        m = db.query_one("SELECT * FROM menu_items WHERE id = ?", (item_id,), conn=c)
        if m is None:
            raise ValueError("ไม่พบเมนูนี้")
        flag = 1 if sold_out else 0
        if m["is_sold_out"] == flag:
            return False
        db.execute("UPDATE menu_items SET is_sold_out = ? WHERE id = ?", (flag, item_id), conn=c)
        if sold_out:
            notice_service.broadcast_open_sessions("sold_out", f"ขออภัย เมนู {m['name']} หมดแล้ว", conn=c)
        how = "ระบบ (สต๊อกหมด)" if auto else None
        log_service.log_action("menu_sold_out" if sold_out else "menu_available",
                               f"{m['name']} {'หมด' if sold_out else 'กลับมามีขาย'}",
                               user_id=None if auto else user_id, actor=how, ref_type="menu_item", ref_id=item_id, conn=c)
        return True
    if conn is not None:
        return _do(conn)
    with db.transaction() as c:
        return _do(c)
