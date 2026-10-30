"""server/jobs.py — งานเบื้องหลังและงานตอนเริ่มระบบของเซิร์ฟเวอร์"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

import config
from database import db, schema, seed
from services import alert_service, backup_service


def prepare_environment() -> dict:
    for d in (
        config.ASSETS_DIR,
        config.QR_DIR,
        config.FONTS_DIR,
        config.UPLOADS_DIR,
        config.MENU_IMAGE_DIR,
        config.EXPORTS_DIR,
        config.BACKUPS_DIR,
    ):
        Path(d).mkdir(parents=True, exist_ok=True)
    schema.create_all()
    seeded = False
    if db.query_one("SELECT COUNT(*) AS c FROM users")["c"] == 0:
        seed.seed_all()
        seeded = True
    backup = None
    try:
        backup = backup_service.auto_backup()
    except Exception:
        traceback.print_exc()
    return {"seeded": seeded, "backup": backup}


class AlertMonitorJob:
    def __init__(self, interval_seconds: float | None = None):
        self.interval = float(interval_seconds or config.ALERT_CHECK_INTERVAL_SECONDS)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.run_once()
        self._thread = threading.Thread(target=self._loop, name="alert-monitor-job", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    @staticmethod
    def run_once() -> dict | None:
        try:
            return alert_service.check_alerts()
        except Exception:
            traceback.print_exc()
            return None

    def _loop(self) -> None:
        while not self._stop_event.wait(self.interval):
            self.run_once()


alert_monitor = AlertMonitorJob()
