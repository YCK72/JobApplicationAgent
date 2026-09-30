from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from app.dashboard.server import main as dashboard_main
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def load_local_environment(root: Path) -> None:
    candidates = (
        root / ".env",
        root.parent / ".env",
        root.parent.parent / ".env",
    )
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return


def show_startup_error(message: str) -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            "Job Application Agent",
            0x10,
        )
    else:
        print(message, file=sys.stderr)


def ensure_tracker_exists(root: Path) -> None:
    workbook = root / "data" / "exports" / "Job_Application_Tracker.xlsx"
    if workbook.exists():
        return
    database = JobDatabase(root / "database" / "jobs.db")
    ExcelTracker(database, workbook).generate()


def main() -> int:
    root = application_root()
    os.chdir(root)
    for relative in ("database", "data/exports", "logs"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    load_local_environment(root)
    try:
        ensure_tracker_exists(root)
        return dashboard_main(
            [
                "--host", "127.0.0.1",
                "--port", "8765",
                "--open-browser",
                "--dashboard-browser", "brave",
            ]
        )
    except Exception as exc:
        show_startup_error(
            "Job Application Agent could not start.\n\n"
            f"{exc}\n\n"
            "Close any existing copy and try again."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
