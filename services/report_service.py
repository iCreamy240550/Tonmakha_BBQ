"""services/report_service.py — รายงานสำหรับเจ้าของ (อ่านอย่างเดียว ยกเว้น export ไฟล์ CSV)

- ยอดขายนับจากบิลที่ชำระแล้ว (bills.paid_at) ; ช่วงวันที่ 'YYYY-MM-DD' รวมทั้งวันเริ่มและวันสิ้นสุด
- ไม่ส่งวันที่ = วันนี้ ; date_from > date_to หรือรูปแบบผิด -> ValueError
- รายการขายแยกตามเมนู: ชั่งกิโลนับเป็น กก. (กรัม/1000), เมนูปกตินับเป็นจำนวนชิ้น
- รายการที่ยกเลิกไม่ถูกนับในยอดขาย
"""
import csv
from datetime import date, datetime, timedelta

import config
from database import db
from services import alert_service, stock_service, table_service


# ---------------------------------------------------------------- ตัวช่วย

def _range(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    """-> (date_from, date_to) ตรวจรูปแบบแล้ว ; ไม่ส่ง = วันนี้"""
    today = date.today().isoformat()
    f, t = date_from or date_to or today, date_to or date_from or today
    try:
        df, dt = datetime.strptime(f, "%Y-%m-%d"), datetime.strptime(t, "%Y-%m-%d")
    except ValueError:
        raise ValueError("รูปแบบวันที่ไม่ถูกต้อง (ใช้ ปี-เดือน-วัน เช่น 2026-10-31)") from None
    if df > dt:
        raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")
    return f, t


def _bounds(f: str, t: str) -> tuple[str, str]:
    return f"{f} 00:00:00", f"{t} 23:59:59"


# ---------------------------------------------------------------- ยอดขาย

def sales_summary(date_from: str | None = None, date_to: str | None = None) -> dict:
    """สรุปยอดขายในช่วงวันที่
    -> {'date_from','date_to','bill_count','subtotal','discount','service_charge','vat','total','avg_per_bill',
        'by_payment': {method: {'method_th','count','total'}}}   (ทุกวิธีชำระมีคีย์เสมอ แม้เป็น 0)"""
    f, t = _range(date_from, date_to)
    lo, hi = _bounds(f, t)
    r = db.query_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(subtotal),0) AS sub, COALESCE(SUM(discount),0) AS disc, "
        "COALESCE(SUM(service_charge),0) AS sc, COALESCE(SUM(vat),0) AS vat, COALESCE(SUM(total),0) AS tot "
        "FROM bills WHERE paid_at BETWEEN ? AND ?", (lo, hi))
    from services.checkout_service import PAYMENT_METHODS_TH
    by = {m: {"method_th": th, "count": 0, "total": 0.0} for m, th in PAYMENT_METHODS_TH.items()}
    for row in db.query_all("SELECT payment_method AS m, COUNT(*) AS n, SUM(total) AS tot FROM bills "
                            "WHERE paid_at BETWEEN ? AND ? GROUP BY payment_method", (lo, hi)):
        by.setdefault(row["m"], {"method_th": row["m"], "count": 0, "total": 0.0})
        by[row["m"]].update(count=row["n"], total=round(row["tot"], 2))
    n = r["n"]
    return {"date_from": f, "date_to": t, "bill_count": n, "subtotal": round(r["sub"], 2),
            "discount": round(r["disc"], 2), "service_charge": round(r["sc"], 2), "vat": round(r["vat"], 2),
            "total": round(r["tot"], 2), "avg_per_bill": round(r["tot"] / n, 2) if n else 0.0, "by_payment": by}


def daily_sales(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """ยอดขายรายวัน -> [{'date','bill_count','total'}] เรียงวันที่เก่า->ใหม่ ครบทุกวันในช่วง (วันไม่มีขาย = 0)"""
    f, t = _range(date_from, date_to)
    lo, hi = _bounds(f, t)
    got = {r["d"]: r for r in db.query_all(
        "SELECT substr(paid_at,1,10) AS d, COUNT(*) AS n, SUM(total) AS tot FROM bills "
        "WHERE paid_at BETWEEN ? AND ? GROUP BY d", (lo, hi))}
    out, day, end = [], datetime.strptime(f, "%Y-%m-%d").date(), datetime.strptime(t, "%Y-%m-%d").date()
    while day <= end:
        k = day.isoformat()
        out.append({"date": k, "bill_count": got[k]["n"] if k in got else 0,
                    "total": round(got[k]["tot"], 2) if k in got else 0.0})
        day += timedelta(days=1)
    return out


def hourly_sales(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """ยอดขายรวมตามชั่วโมงของวัน (ทุกวันในช่วงรวมกัน) -> 24 แถว [{'hour':0..23,'bill_count','total'}]"""
    f, t = _range(date_from, date_to)
    lo, hi = _bounds(f, t)
    got = {int(r["h"]): r for r in db.query_all(
        "SELECT substr(paid_at,12,2) AS h, COUNT(*) AS n, SUM(total) AS tot FROM bills "
        "WHERE paid_at BETWEEN ? AND ? GROUP BY h", (lo, hi))}
    return [{"hour": h, "bill_count": got[h]["n"] if h in got else 0,
             "total": round(got[h]["tot"], 2) if h in got else 0.0} for h in range(24)]


def top_items(date_from: str | None = None, date_to: str | None = None, limit: int = 10) -> list[dict]:
    """เมนูขายดี (เรียงตามยอดเงินมากไปน้อย) เฉพาะรอบที่ชำระแล้วในช่วงวันที่
    -> [{'menu_item_id','name','item_type','quantity','unit','amount'}]  quantity = กก. (ชั่ง) หรือชิ้น (ปกติ)
    ชื่อใช้ชื่อตอนขาย (snapshot) ; เมนูเดียวกันรวมเป็นแถวเดียวตาม menu_item_id"""
    f, t = _range(date_from, date_to)
    lo, hi = _bounds(f, t)
    items: dict[int, dict] = {}
    for r in db.query_all(
            "SELECT w.menu_item_id AS mid, MAX(w.name_snapshot) AS name, SUM(w.weight_grams) AS g, SUM(w.amount) AS amt "
            "FROM weigh_entries w JOIN bills b ON b.session_id = w.session_id "
            "WHERE w.status = 'active' AND b.paid_at BETWEEN ? AND ? GROUP BY w.menu_item_id", (lo, hi)):
        items[r["mid"]] = {"menu_item_id": r["mid"], "name": r["name"], "item_type": config.MENU_TYPE_WEIGHED,
                           "quantity": round(r["g"] / config.GRAMS_PER_KG, 3), "unit": "กก.",
                           "amount": round(r["amt"], 2)}
    for r in db.query_all(
            "SELECT oi.menu_item_id AS mid, MAX(oi.name_snapshot) AS name, SUM(oi.quantity) AS q, "
            "SUM(oi.unit_price * oi.quantity) AS amt FROM order_items oi JOIN orders o ON o.id = oi.order_id "
            "JOIN bills b ON b.session_id = o.session_id "
            "WHERE oi.status != 'cancelled' AND b.paid_at BETWEEN ? AND ? GROUP BY oi.menu_item_id", (lo, hi)):
        items[r["mid"]] = {"menu_item_id": r["mid"], "name": r["name"], "item_type": config.MENU_TYPE_NORMAL,
                           "quantity": r["q"], "unit": "ชิ้น", "amount": round(r["amt"], 2)}
    return sorted(items.values(), key=lambda x: x["amount"], reverse=True)[:max(0, limit)]


# ---------------------------------------------------------------- ยกเลิก

def cancellations(date_from: str | None = None, date_to: str | None = None) -> dict:
    """รายการที่ถูกยกเลิก + เหตุผล ในช่วงวันที่ (ให้เจ้าของตรวจความผิดปกติ)"""
    f, t = _range(date_from, date_to)
    lo, hi = _bounds(f, t)
    rows = []
    for r in db.query_all(
            "SELECT t.table_no, oi.name_snapshot AS name, oi.quantity AS q, oi.unit_price * oi.quantity AS amt, "
            "oi.cancel_reason AS reason, u.display_name  AS who, oi.cancelled_at AS at "
            "FROM order_items oi JOIN orders o ON o.id = oi.order_id JOIN table_sessions s ON s.id = o.session_id "
            "JOIN tables t ON t.id = s.table_id LEFT JOIN users u ON u.id = oi.cancelled_by "
            "WHERE oi.status = 'cancelled' AND oi.cancelled_at BETWEEN ? AND ?", (lo, hi)):
        rows.append({"kind": "order_item", "table_no": r["table_no"], "name": r["name"], "quantity": r["q"],
                     "amount": round(r["amt"], 2), "reason": r["reason"], "by": r["who"], "at": r["at"]})
    for r in db.query_all(
            "SELECT t.table_no, w.name_snapshot AS name, w.weight_grams AS g, w.amount AS amt, "
            "w.cancel_reason AS reason, u.display_name  AS who, w.created_at AS at "
            "FROM weigh_entries w JOIN table_sessions s ON s.id = w.session_id JOIN tables t ON t.id = s.table_id "
            "LEFT JOIN users u ON u.id = w.created_by "
            "WHERE w.status = 'cancelled' AND w.created_at BETWEEN ? AND ?", (lo, hi)):
        rows.append({"kind": "weigh_entry", "table_no": r["table_no"], "name": r["name"],
                     "quantity": round(r["g"] / config.GRAMS_PER_KG, 3), "amount": round(r["amt"], 2),
                     "reason": r["reason"], "by": r["who"], "at": r["at"]})
    rows.sort(key=lambda x: x["at"] or "", reverse=True)
    sessions = [{"table_no": r["table_no"], "cancelled_by": r["cancelled_by"], "reason": r["cancel_reason"],
                 "at": r["closed_at"]} for r in db.query_all(
        "SELECT t.table_no, s.cancelled_by, s.cancel_reason, s.closed_at FROM table_sessions s "
        "JOIN tables t ON t.id = s.table_id WHERE s.status = 'cancelled' AND s.closed_at BETWEEN ? AND ? "
        "ORDER BY s.id DESC", (lo, hi))]
    return {"items": rows, "cancelled_sessions": sessions, "item_count": len(rows),
            "item_amount": round(sum(x["amount"] for x in rows), 2)}


# ---------------------------------------------------------------- แดชบอร์ด

def today_overview() -> dict:
    """ตัวเลขหน้าแดชบอร์ดเจ้าของ ณ ตอนนี้"""
    today = date.today().isoformat()
    tables = table_service.list_tables_with_status()
    low = stock_service.list_low_stock()
    canc = cancellations(today, today)
    return {
        "sales": sales_summary(today, today),
        "tables_total": len(tables),
        "tables_in_use": sum(1 for x in tables if x["status"] == config.SESSION_OPEN),
        "tables_pending": sum(1 for x in tables if x["status"] == config.SESSION_PENDING),
        "tables_awaiting_payment": sum(1 for x in tables if x["status"] == config.SESSION_AWAITING_PAYMENT),
        "low_stock": low, "low_stock_count": len(low),
        "active_alerts": alert_service.active_count(),
        "cancelled_items_today": canc["item_count"], "cancelled_sessions_today": len(canc["cancelled_sessions"]),
    }


# ---------------------------------------------------------------- ส่งออก CSV

def export_sales_csv(date_from: str | None = None, date_to: str | None = None, out_dir=None):
    """ส่งออกบิลที่ชำระแล้วในช่วงวันที่เป็น CSV (utf-8-sig เปิดใน Excel แล้วภาษาไทยไม่เพี้ยน)
    -> Path ไฟล์ exports/sales_<จาก>_<ถึง>.csv (out_dir ไม่ส่ง = config.EXPORTS_DIR) ; เขียนทับไฟล์ชื่อเดิม
    คอลัมน์: บิล, วันเวลาชำระ, โต๊ะ, ยอดรวม, โปร, ส่วนลด, ค่าบริการ, ภาษีมูลค่าเพิ่ม, ยอดสุทธิ, ช่องทางชำระ, ผู้รับเงิน"""
    from pathlib import Path

    from services.checkout_service import list_bills
    f, t = _range(date_from, date_to)
    out = Path(out_dir) if out_dir else Path(config.EXPORTS_DIR)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"sales_{f}_{t}.csv"
    bills = list(reversed(list_bills(date_from=f, date_to=t, limit=1_000_000)))
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["บิล", "วันเวลาชำระ", "โต๊ะ", "ยอดรวม", "โปร", "ส่วนลด", "ค่าบริการ", "ภาษีมูลค่าเพิ่ม", "ยอดสุทธิ",
                    "ช่องทางชำระ", "ผู้รับเงิน"])
        for b in bills:
            tbl_disp = "สั่งกลับบ้าน" if b["table_no"] == 0 else b["table_no"]
            w.writerow([b["id"], b["paid_at"], tbl_disp, f"{b['subtotal']:.2f}", b["promo_name"] or "",
                        f"{b['discount']:.2f}", f"{b['service_charge']:.2f}", f"{b['vat']:.2f}",
                        f"{b['total']:.2f}", b["payment_method_th"], b["cashier_name"] or ""])
    return path
