from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from app.dashboard.server import create_dashboard_server
from app.dashboard.tracker_reader import (
    DashboardDataError,
    TrackerWorkbookReader,
)
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
    JobCategory,
)
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker


def make_workbook(tmp_path: Path) -> Path:
    database = JobDatabase(tmp_path / "jobs.db")
    database.add_job(
        Job(
            company="Example Labs",
            title="Software Engineer I",
            location="Seattle, WA",
            url="https://example.com/jobs/1",
            source="linkedin_composio",
            category=JobCategory.SDE,
            fit_score=84.5,
            status=ApplicationStatus.NEEDS_APPLICATION,
            application_method=ApplicationMethod.AUTO,
            notes="Ready for the controlled workflow.",
        )
    )
    database.add_job(
        Job(
            company="Microsoft",
            title="Machine Learning Engineer",
            location="Redmond, WA",
            url="https://example.com/jobs/2",
            source="greenhouse",
            category=JobCategory.AI_ML,
            company_rule=CompanyRule.MANUAL,
            application_method=ApplicationMethod.MANUAL,
            status=ApplicationStatus.NEEDS_REVIEW,
            notes="Manual tailoring required.",
        )
    )
    database.add_job(
        Job(
            company="Applied Company",
            title="Data Scientist I",
            location="Remote, US",
            url="https://example.com/jobs/3",
            source="greenhouse",
            category=JobCategory.DATA_SCIENCE,
            application_method=ApplicationMethod.MANUAL,
            status=ApplicationStatus.APPLIED,
        )
    )
    path = tmp_path / "Job_Application_Tracker.xlsx"
    ExcelTracker(database, path).generate()
    return path


def test_reader_returns_dashboard_snapshot(tmp_path: Path) -> None:
    snapshot = TrackerWorkbookReader(make_workbook(tmp_path)).snapshot()

    assert snapshot["source"]["stale"] is False
    assert snapshot["source"]["warning"] is None
    assert snapshot["metrics"] == {
        "total_jobs": 3,
        "applied": 1,
        "manual_queue": 2,
        "needs_review": 1,
        "in_progress": 0,
        "offers": 0,
        "rejected": 0,
    }
    assert snapshot["facets"]["statuses"] == [
        "APPLIED",
        "NEEDS_APPLICATION",
        "NEEDS_REVIEW",
    ]
    example_job = next(
        job
        for job in snapshot["jobs"]
        if job["company"] == "Example Labs"
    )
    assert example_job["fit_score"] == 84.5
    assert example_job["job_url"] == (
        "https://example.com/jobs/1"
    )
    json.dumps(snapshot)


def test_reader_reuses_snapshot_until_file_changes(tmp_path: Path) -> None:
    reader = TrackerWorkbookReader(make_workbook(tmp_path))
    first = reader.snapshot()
    second = reader.snapshot()

    assert first is second


def test_reader_serves_last_good_snapshot_when_reload_fails(
    tmp_path: Path,
) -> None:
    path = make_workbook(tmp_path)
    reader = TrackerWorkbookReader(path)
    first = reader.snapshot()

    path.write_bytes(b"not an xlsx workbook")
    stale = reader.snapshot()

    assert stale is not first
    assert stale["jobs"] == first["jobs"]
    assert stale["source"]["stale"] is True
    assert "last successful" in stale["source"]["warning"].lower()


def test_missing_workbook_is_actionable(tmp_path: Path) -> None:
    reader = TrackerWorkbookReader(tmp_path / "missing.xlsx")

    with pytest.raises(DashboardDataError, match="does not exist"):
        reader.snapshot()


def test_reader_rejects_missing_all_jobs_sheet(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "invalid.xlsx"
    Workbook().save(path)

    with pytest.raises(DashboardDataError, match="All Jobs"):
        TrackerWorkbookReader(path).snapshot()


def test_reader_rejects_unexpected_headers(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "invalid.xlsx"
    workbook = Workbook()
    workbook.active.title = "All Jobs"
    workbook.active.append(["Company", "Unexpected"])
    workbook.save(path)

    with pytest.raises(DashboardDataError, match="headers"):
        TrackerWorkbookReader(path).snapshot()


def test_non_web_job_url_is_not_exposed_as_link(tmp_path: Path) -> None:
    path = make_workbook(tmp_path)
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    workbook["All Jobs"]["L2"] = "javascript:alert(1)"
    workbook.save(path)

    snapshot = TrackerWorkbookReader(path).snapshot()
    applied_job = next(
        job
        for job in snapshot["jobs"]
        if job["company"] == "Applied Company"
    )
    assert applied_job["job_url"] is None


def test_http_server_exposes_ui_api_and_health(tmp_path: Path) -> None:
    reader = TrackerWorkbookReader(make_workbook(tmp_path))
    server = create_dashboard_server(
        reader=reader,
        host="127.0.0.1",
        port=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(base_url + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "Job Application Dashboard" in html

        with urlopen(base_url + "/api/jobs", timeout=5) as response:
            payload = json.load(response)
            assert response.status == 200
            assert payload["metrics"]["total_jobs"] == 3
            assert response.headers["Cache-Control"] == "no-store"

        with urlopen(base_url + "/api/health", timeout=5) as response:
            payload = json.load(response)
            assert payload["status"] == "ok"
            assert payload["workbook_available"] is True

        with urlopen(base_url + "/static/app.js", timeout=5) as response:
            script = response.read().decode("utf-8")
            assert "setInterval" in script
            assert "innerHTML" not in script
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_server_reports_missing_workbook(tmp_path: Path) -> None:
    server = create_dashboard_server(
        reader=TrackerWorkbookReader(tmp_path / "missing.xlsx"),
        host="127.0.0.1",
        port=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/jobs"
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=5)
        assert error.value.code == 503
        payload = json.loads(error.value.read().decode("utf-8"))
        assert "does not exist" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_server_rejects_writes(tmp_path: Path) -> None:
    server = create_dashboard_server(
        reader=TrackerWorkbookReader(make_workbook(tmp_path)),
        host="127.0.0.1",
        port=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/jobs",
            method="POST",
            data=b"{}",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=5)
        assert error.value.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
