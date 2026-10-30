"""run_web.py — ทางลัดเรียก main.py --no-browser เพื่อความเข้ากันได้ย้อนหลัง"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as main_mod  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    passed = list(argv if argv is not None else sys.argv[1:])
    if "--no-browser" not in passed and "--check" not in passed:
        passed.insert(0, "--no-browser")
    return main_mod.main(passed)


if __name__ == "__main__":
    sys.exit(main())
