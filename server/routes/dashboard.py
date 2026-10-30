"""server/routes/dashboard.py — API หน้าแดชบอร์ดและรายงานของเจ้าของร้าน"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from server import auth as server_auth
from server.deps import require_owner
from server.helpers import baht, ce_to_be_year, fmt_datetime, format_thai_date, money, open_folder, parse_date
from services import checkout_service, report_service

router = APIRouter(prefix="/api/owner", tags=["dashboard_report"], dependencies=[Depends(require_owner)])

CANCELLED_BY_TH = {"staff": "พนักงาน", "customer": "ลูกค้า"}
KIND_TH = {"order_item": "รายการสั่ง", "weigh_entry": "รายการชั่ง", "session": "ยกเลิกทั้งโต๊ะ"}
BILL_LIMIT = 300


class ExportCsvRequest(BaseModel):
    date_from: str
    date_to: str


class OpenFolderRequest(BaseModel):
    target: str = "exports"


def _fmt_iso_to_be(iso_date: str | None) -> str:
    if not iso_date or len(str(iso_date)) < 10:
        return str(iso_date or "-")
    s = str(iso_date)[:10]
    try:
        y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        return f"{d:02d}/{m:02d}/{ce_to_be_year(y)}"
    except ValueError:
        return s


def _quick_range(kind: str) -> tuple[str, str]:
    today = date.today()
    if kind == "today":
        a = b = today
    elif kind == "yesterday":
        a = b = today - timedelta(days=1)
    elif kind == "7days":
        a, b = today - timedelta(days=6), today
    elif kind == "month":
        a, b = today.replace(day=1), today
    else:
        b = today.replace(day=1) - timedelta(days=1)
        a = b.replace(day=1)
    return a.isoformat(), b.isoformat()


@router.get("/dashboard/overview")
def get_today_overview() -> dict:
    data = report_service.today_overview()
    sales = data["sales"]
    data["subtitle"] = f"ข้อมูลวันนี้: {format_thai_date(sales['date_from'], short_month=True)}"
    return data


@router.get("/dashboard/report")
def get_report_data(
    date_from: str | None = None,
    date_to: str | None = None,
    quick: str | None = None,
) -> dict:
    if quick:
        f, t = _quick_range(quick)
    else:
        today_iso = date.today().isoformat()
        f = parse_date(date_from or today_iso, "วันที่เริ่ม", allow_empty=False)
        t = parse_date(date_to or f, "วันที่สิ้นสุด", allow_empty=False)
    if f > t:
        raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")

    summary = report_service.sales_summary(f, t)
    daily = report_service.daily_sales(f, t)
    for d in daily:
        d["date_be_label"] = f"{_fmt_iso_to_be(d['date'])} ({d['date']})"

    hourly = report_service.hourly_sales(f, t)
    for h in hourly:
        h["hour_label"] = f"{h['hour']:02d}:00 - {h['hour']:02d}:59"

    top = report_service.top_items(f, t, 20)
    for i, row in enumerate(top, start=1):
        row["rank"] = i
        row["qty_label"] = f"{row['quantity']:g} {row['unit']}"

    canc = report_service.cancellations(f, t)
    canc_rows = []
    for it in canc["items"]:
        it_copy = dict(it)
        qty = it_copy["quantity"]
        it_copy["name"] = f"{it_copy['name']} {qty:g} กก." if it_copy["kind"] == "weigh_entry" else f"{it_copy['name']} ×{qty:g}"
        it_copy["kind_th"] = KIND_TH.get(it_copy["kind"], it_copy["kind"])
        it_copy["at_fmt"] = fmt_datetime(it_copy["at"])
        it_copy["amount_fmt"] = money(it_copy["amount"]) if it_copy["amount"] is not None else "-"
        it_copy["by"] = it_copy.get("by") or "-"
        canc_rows.append(it_copy)

    for s in canc["cancelled_sessions"]:
        canc_rows.append({
            "kind": "session",
            "kind_th": KIND_TH["session"],
            "table_no": s["table_no"],
            "name": "ยกเลิกโต๊ะ",
            "quantity": None,
            "amount": None,
            "amount_fmt": "-",
            "reason": s["reason"] or "-",
            "by": CANCELLED_BY_TH.get(s["cancelled_by"], s["cancelled_by"] or "-"),
            "at": s["at"],
            "at_fmt": fmt_datetime(s["at"]),
        })
    canc_rows.sort(key=lambda r: r["at"] or "", reverse=True)

    bills = checkout_service.list_bills(f, t, BILL_LIMIT)
    for b in bills:
        b["paid_at_fmt"] = fmt_datetime(b["paid_at"])
        if b.get("table_no") == 0 or b.get("table_name") == "สั่งกลับบ้าน":
            b["table_no"] = "สั่งกลับบ้าน"

    notes = []
    if summary["bill_count"] > BILL_LIMIT:
        notes.append(f"แท็บบิลแสดง {BILL_LIMIT} บิลล่าสุด จากทั้งหมด {summary['bill_count']:,} บิล (ส่งออก CSV เพื่อดูครบ)")
    if canc["item_count"]:
        notes.append(f"ยกเลิกรายการรวม {canc['item_count']} รายการ มูลค่า {baht(canc['item_amount'])}")

    f_th = _fmt_iso_to_be(f)
    t_th = _fmt_iso_to_be(t)
    range_label = f"ช่วงวันที่ {f_th} ถึง {t_th}" if f != t else f"วันที่ {f_th}"

    return {
        "date_from": f,
        "date_to": t,
        "date_from_thai": format_thai_date(f, short_month=True),
        "date_to_thai": format_thai_date(t, short_month=True),
        "range_label": range_label,
        "summary": summary,
        "daily": daily,
        "hourly": hourly,
        "top_items": top,
        "cancellations": canc_rows,
        "cancellation_summary": canc,
        "bills": bills,
        "note": "  ·  ".join(notes),
    }


@router.post("/report/export_csv")
def export_sales_csv(body: ExportCsvRequest) -> dict:
    f = parse_date(body.date_from, "วันที่เริ่ม", allow_empty=False)
    t = parse_date(body.date_to, "วันที่สิ้นสุด", allow_empty=False)
    if f > t:
        raise ValueError("วันเริ่มต้องไม่หลังวันสิ้นสุด")
    path = report_service.export_sales_csv(f, t)
    return {
        "filename": path.name,
        "path": str(path),
        "download_url": f"/api/owner/files/exports/{path.name}",
        "message": f"ส่งออกแล้ว: {path}",
    }


@router.get("/files/exports/{filename}")
def download_export_file(filename: str):
    if not filename or Path(filename).name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="ชื่อไฟล์ไม่ถูกต้อง")
    full = (Path(config.EXPORTS_DIR) / filename).resolve()
    root = Path(config.EXPORTS_DIR).resolve()
    if not str(full).startswith(str(root)) or not full.is_file():
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ที่ส่งออก")
    media_type = "text/csv; charset=utf-8" if filename.lower().endswith(".csv") else "application/octet-stream"
    return FileResponse(path=str(full), filename=filename, media_type=media_type)


@router.post("/open_folder")
def open_local_folder(body: OpenFolderRequest, request: Request) -> dict:
    if not server_auth.is_local_request(request):
        raise ValueError("เปิดโฟลเดอร์ได้เฉพาะเมื่อใช้งานบนเครื่องที่รันเซิร์ฟเวอร์เท่านั้น")
    folder_map = {
        "exports": config.EXPORTS_DIR,
        "qr": config.QR_DIR,
        "backups": config.BACKUPS_DIR,
    }
    target_path = folder_map.get(body.target)
    if target_path is None:
        raise ValueError("โฟลเดอร์ที่ระบุไม่ถูกต้อง")
    opened = open_folder(target_path)
    return {
        "opened": opened,
        "path": str(target_path),
        "message": f"เปิดโฟลเดอร์แล้ว: {target_path}" if opened else f"เปิดโฟลเดอร์ไม่ได้ — ไฟล์อยู่ที่ {target_path}",
    }
