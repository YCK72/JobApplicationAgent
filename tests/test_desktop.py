from pathlib import Path
from unittest.mock import MagicMock

from app import desktop


def test_desktop_starts_loopback_dashboard_in_brave(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_cwd = Path.cwd()
    dashboard = MagicMock(return_value=0)
    monkeypatch.setattr(desktop, "application_root", lambda: tmp_path)
    monkeypatch.setattr(desktop, "load_local_environment", MagicMock())
    tracker = MagicMock()
    monkeypatch.setattr(desktop, "ensure_tracker_exists", tracker)
    monkeypatch.setattr(desktop, "dashboard_main", dashboard)

    try:
        assert desktop.main() == 0
        assert Path.cwd() == tmp_path
    finally:
        desktop.os.chdir(original_cwd)
    dashboard.assert_called_once_with(
        [
            "--host", "127.0.0.1",
            "--port", "8765",
            "--open-browser",
            "--dashboard-browser", "brave",
        ]
    )
    tracker.assert_called_once_with(tmp_path)
    assert (tmp_path / "database").is_dir()
    assert (tmp_path / "data" / "exports").is_dir()


def test_environment_loader_uses_nearest_env(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("COMPOSIO_API_KEY=test-key\n", encoding="utf-8")

    desktop.load_local_environment(tmp_path)

    assert desktop.os.environ["COMPOSIO_API_KEY"] == "test-key"


def test_tracker_creation_preserves_existing_workbook(tmp_path: Path) -> None:
    workbook = tmp_path / "data" / "exports" / "Job_Application_Tracker.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"existing workbook")

    desktop.ensure_tracker_exists(tmp_path)

    assert workbook.read_bytes() == b"existing workbook"
