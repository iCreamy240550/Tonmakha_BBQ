"""server/app.py — แอปพลิเคชันหลัก FastAPI ของร้านต้นมะค่า"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import config
from server import auth as server_auth
from server import jobs
from server.routes import auth, checkout, customer, dashboard, menu, orders, owner_admin, shop, stock, tables, takeaway, weigh


@asynccontextmanager
async def lifespan(_app: FastAPI):
    jobs.prepare_environment()
    jobs.alert_monitor.start()
    try:
        yield
    finally:
        jobs.alert_monitor.stop()


def _safe_static_file(root_dir: Path, rel_path: str) -> Path:
    if not rel_path or ".." in rel_path or rel_path.startswith(("/", "\\")):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
    try:
        root_resolved = root_dir.resolve()
        target = (root_resolved / rel_path).resolve()
    except OSError:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
    if not str(target).startswith(str(root_resolved)) or not target.is_file():
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
    return target


def create_app(enable_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title=config.APP_NAME,
        lifespan=lifespan if enable_lifespan else None,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        status_code = int(getattr(exc, "status_code", 400) or 400)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    @app.exception_handler(PermissionError)
    async def permission_error_handler(_request: Request, exc: PermissionError):
        return JSONResponse(status_code=403, content={"detail": str(exc) or "คุณไม่มีสิทธิ์ดำเนินการนี้"})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, _exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"detail": "ข้อมูลที่ส่งมาไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง"})

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception):
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"detail": "ระบบเกิดข้อผิดพลาดภายใน กรุณาลองใหม่อีกครั้ง"},
        )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        path = request.url.path or "/"

        if path.startswith("/qr_codes") or path.startswith("/assets/qr_codes"):
            return JSONResponse(status_code=403, content={"detail": "ไม่อนุญาตให้เข้าถึงไฟล์ QR โดยตรง"})

        if (
            path == "/staff"
            or path.startswith("/staff/")
            or path.startswith("/static/staff/")
            or path.startswith("/api/staff")
            or path.startswith("/api/owner")
        ):
            if not server_auth.is_staff_network_allowed(request):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "ไม่อนุญาตให้เข้าหน้าพนักงาน/เจ้าของร้านจากเครือข่ายภายนอก (อนุญาตเฉพาะเครื่องที่รันเซิร์ฟเวอร์)"
                    },
                )

        try:
            server_auth.verify_csrf_origin(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})

        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "script-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        return response

    app.include_router(customer.router)
    app.include_router(auth.router)
    app.include_router(shop.router)
    app.include_router(tables.router)
    app.include_router(takeaway.router)
    app.include_router(weigh.router)
    app.include_router(orders.router)
    app.include_router(checkout.router)
    app.include_router(dashboard.router)
    app.include_router(menu.router)
    app.include_router(stock.router)
    app.include_router(owner_admin.router)

    @app.get("/logo.png")
    @app.get("/favicon.ico")
    def get_logo():
        logo_path = Path(config.LOGO_PATH)
        if not logo_path.is_file():
            fallback = config.BASE_DIR / "assets" / "logo.png"
            if fallback.is_file():
                logo_path = fallback
            else:
                raise HTTPException(status_code=404, detail="ไม่พบไฟล์โลโก้")
        return FileResponse(str(logo_path), media_type="image/png")

    @app.get("/fonts/{file_path:path}")
    def get_font_file(file_path: str):
        target = _safe_static_file(Path(config.FONTS_DIR), file_path)
        return FileResponse(
            str(target),
            media_type="font/ttf",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/uploads/{file_path:path}")
    def get_upload_file(file_path: str):
        target = _safe_static_file(Path(config.UPLOADS_DIR), file_path)
        return FileResponse(str(target))

    @app.get("/static/shared/{file_path:path}")
    def get_shared_asset(file_path: str):
        target = _safe_static_file(Path(config.FRONTEND_DIR) / "shared", file_path)
        return FileResponse(str(target))

    @app.get("/static/customer/{file_path:path}")
    def get_customer_asset(file_path: str):
        target = _safe_static_file(Path(config.FRONTEND_DIR) / "customer", file_path)
        return FileResponse(str(target))

    @app.get("/static/staff/{file_path:path}")
    def get_staff_asset(file_path: str):
        target = _safe_static_file(Path(config.FRONTEND_DIR) / "staff", file_path)
        return FileResponse(str(target))

    def _serve_html(html_path: Path):
        if not html_path.is_file():
            return HTMLResponse(
                f"<!doctype html><html lang='th'><head><meta charset='utf-8'><title>{config.APP_NAME}</title></head>"
                f"<body><h1>{config.APP_NAME}</h1></body></html>"
            )
        return FileResponse(str(html_path), media_type="text/html; charset=utf-8")

    @app.get("/", response_class=HTMLResponse)
    def customer_root_page():
        return _serve_html(Path(config.FRONTEND_DIR) / "customer" / "index.html")

    @app.get("/t/{table_no}", response_class=HTMLResponse)
    def customer_enter_page(table_no: int):
        _ = table_no
        return _serve_html(Path(config.FRONTEND_DIR) / "customer" / "index.html")

    @app.get("/s", response_class=HTMLResponse)
    def customer_session_page():
        return _serve_html(Path(config.FRONTEND_DIR) / "customer" / "index.html")

    @app.get("/staff", response_class=HTMLResponse)
    def staff_app_page(request: Request):
        server_auth.enforce_staff_network(request)
        return _serve_html(Path(config.FRONTEND_DIR) / "staff" / "index.html")

    return app


app = create_app()
