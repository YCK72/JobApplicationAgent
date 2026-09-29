from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.applications.submission_confirmation import (
    SubmissionConfirmationOutcome,
    SubmissionConfirmationService,
)
from app.applications.submission_recording import (
    SubmissionRecordingResult,
    SubmissionRecordingRunner,
)
from app.applications.composition import (
    build_submission_recording_runner,
)
from app.jobs.models import ApplicationStatus, Job
from app.tracking.database import JobDatabase
from scripts.record_submission import main


def persist_job(
    database: JobDatabase,
    *,
    status: ApplicationStatus = ApplicationStatus.FORM_STARTED,
) -> int:
    return database.add_job(
        Job(
            company="Example",
            title="Software Engineer I",
            location="Seattle, WA",
            url="https://example.com/jobs/123",
            source="test",
            status=status,
            resume_used="data/resumes/sde_resume.pdf",
        )
    )


def make_runner(database: JobDatabase):
    tracker = MagicMock()
    tracker.generate.return_value = Path("tracker.xlsx")
    runner = SubmissionRecordingRunner(
        database=database,
        confirmation_service=SubmissionConfirmationService(database),
        tracker=tracker,
    )
    return runner, tracker


def test_confirmed_evidence_marks_exact_job_applied_and_refreshes_tracker(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    runner, tracker = make_runner(database)

    result = runner.record(
        job_id=job_id,
        submitted=True,
        success_confirmed=True,
        evidence="Portal displayed a confirmation number.",
    )

    assert result.outcome == SubmissionConfirmationOutcome.CONFIRMED
    assert result.confirmed is True
    assert result.may_submit is False
    assert result.export_path == Path("tracker.xlsx")
    assert result.tracker_error is None
    stored = database.get_job_by_id(job_id)
    assert stored.status == ApplicationStatus.APPLIED
    assert stored.date_applied is not None
    assert "confirmation number" in stored.notes.lower()
    tracker.generate.assert_called_once_with()


def test_uncertain_submission_records_unconfirmed_and_refreshes_tracker(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    runner, tracker = make_runner(database)

    result = runner.record(
        job_id=job_id,
        submitted=True,
        success_confirmed=False,
        evidence="Submit was clicked but no confirmation appeared.",
    )

    assert result.outcome == SubmissionConfirmationOutcome.UNCONFIRMED
    assert result.confirmed is False
    assert database.get_job_by_id(job_id).status == (
        ApplicationStatus.SUBMISSION_UNCONFIRMED
    )
    tracker.generate.assert_called_once_with()


def test_not_submitted_keeps_lifecycle_unchanged(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    runner, tracker = make_runner(database)

    result = runner.record(
        job_id=job_id,
        submitted=False,
        success_confirmed=False,
        evidence=None,
    )

    assert result.outcome == SubmissionConfirmationOutcome.NOT_SUBMITTED
    assert database.get_job_by_id(job_id).status == ApplicationStatus.FORM_STARTED
    tracker.generate.assert_called_once_with()


def test_confirmed_submission_without_evidence_is_blocked(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    runner, tracker = make_runner(database)

    result = runner.record(
        job_id=job_id,
        submitted=True,
        success_confirmed=True,
        evidence="  ",
    )

    assert result.outcome == SubmissionConfirmationOutcome.BLOCKED
    assert result.confirmed is False
    assert database.get_job_by_id(job_id).status == ApplicationStatus.FORM_STARTED
    tracker.generate.assert_called_once_with()


def test_ineligible_lifecycle_is_blocked(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(
        database,
        status=ApplicationStatus.NEEDS_APPLICATION,
    )
    runner, _ = make_runner(database)

    result = runner.record(
        job_id=job_id,
        submitted=True,
        success_confirmed=True,
        evidence="Confirmation page.",
    )

    assert result.outcome == SubmissionConfirmationOutcome.BLOCKED
    assert database.get_job_by_id(job_id).status == (
        ApplicationStatus.NEEDS_APPLICATION
    )


def test_missing_job_fails_without_refreshing_tracker(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    runner, tracker = make_runner(database)

    result = runner.record(
        job_id=999,
        submitted=True,
        success_confirmed=True,
        evidence="Confirmation page.",
    )

    assert result.outcome == SubmissionConfirmationOutcome.FAILED
    assert result.job is None
    assert result.may_submit is False
    tracker.generate.assert_not_called()


def test_tracker_failure_does_not_hide_confirmed_database_transition(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    runner, tracker = make_runner(database)
    tracker.generate.side_effect = OSError("workbook locked")

    result = runner.record(
        job_id=job_id,
        submitted=True,
        success_confirmed=True,
        evidence="Confirmation page.",
    )

    assert result.outcome == SubmissionConfirmationOutcome.CONFIRMED
    assert result.confirmed is True
    assert result.export_path is None
    assert "workbook locked" in result.tracker_error
    assert database.get_job_by_id(job_id).status == ApplicationStatus.APPLIED


def test_runner_has_no_browser_or_submission_capability(tmp_path: Path) -> None:
    runner, _ = make_runner(JobDatabase(tmp_path / "jobs.db"))

    assert not hasattr(runner, "browser")
    assert not hasattr(runner, "submit")
    assert not hasattr(runner, "click_submit")


def test_production_composition_shares_database_and_has_no_browser(
    tmp_path: Path,
) -> None:
    runner = build_submission_recording_runner(
        database_path=tmp_path / "jobs.db",
        export_path=tmp_path / "tracker.xlsx",
    )

    assert runner.confirmation_service.database is runner.database
    assert runner.tracker.database is runner.database
    assert not hasattr(runner, "workflow")
    assert not hasattr(runner, "browser_session_factory")


def test_cli_forwards_explicit_confirmed_evidence(capsys) -> None:
    job = MagicMock(
        company="Example",
        title="Engineer",
        status=ApplicationStatus.APPLIED,
        date_applied="2026-09-29T12:00:00",
    )
    result = SubmissionRecordingResult(
        job_id=7,
        job=job,
        outcome=SubmissionConfirmationOutcome.CONFIRMED,
        reason="Confirmed.",
        export_path=Path("tracker.xlsx"),
    )
    runner = MagicMock()
    runner.record.return_value = result
    builder = MagicMock(return_value=runner)

    exit_code = main(
        [
            "--job-id", "7",
            "--submitted",
            "--confirmed",
            "--evidence", "Confirmation number 123",
        ],
        runner_builder=builder,
    )

    assert exit_code == 0
    runner.record.assert_called_once_with(
        job_id=7,
        submitted=True,
        success_confirmed=True,
        evidence="Confirmation number 123",
    )
    output = capsys.readouterr().out
    assert '"outcome": "CONFIRMED"' in output
    assert '"may_submit": false' in output


def test_cli_submitted_without_confirmed_records_uncertain_outcome() -> None:
    runner = MagicMock()
    runner.record.return_value = SubmissionRecordingResult(
        job_id=7,
        job=MagicMock(
            company="Example",
            title="Engineer",
            status=ApplicationStatus.SUBMISSION_UNCONFIRMED,
            date_applied=None,
        ),
        outcome=SubmissionConfirmationOutcome.UNCONFIRMED,
        reason="Unconfirmed.",
    )

    exit_code = main(
        ["--job-id", "7", "--submitted"],
        runner_builder=MagicMock(return_value=runner),
    )

    assert exit_code == 0
    runner.record.assert_called_once_with(
        job_id=7,
        submitted=True,
        success_confirmed=False,
        evidence=None,
    )


@pytest.mark.parametrize("job_id", ["0", "-2"])
def test_cli_rejects_non_positive_job_id(job_id: str) -> None:
    with pytest.raises(SystemExit):
        main(["--job-id", job_id], runner_builder=MagicMock())


def test_cli_rejects_confirmed_without_submitted() -> None:
    with pytest.raises(SystemExit):
        main(
            ["--job-id", "7", "--confirmed", "--evidence", "Page"],
            runner_builder=MagicMock(),
        )


def test_cli_rejects_evidence_when_no_submission_occurred() -> None:
    with pytest.raises(SystemExit):
        main(
            ["--job-id", "7", "--evidence", "Nothing submitted"],
            runner_builder=MagicMock(),
        )
