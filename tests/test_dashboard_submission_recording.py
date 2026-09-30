from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.applications.submission_confirmation import (
    SubmissionConfirmationOutcome,
)
from app.applications.submission_recording import SubmissionRecordingResult
from app.dashboard.submission_recording import (
    DashboardSubmissionRecordingService,
    DashboardSubmissionStatus,
    SubmissionReviewStatus,
)
from app.jobs.models import ApplicationStatus, Job
from app.tracking.database import JobDatabase


def persist_job(
    database: JobDatabase,
    *,
    status: ApplicationStatus = ApplicationStatus.FORM_STARTED,
) -> int:
    return database.add_job(Job(
        company="Example",
        title="Software Engineer I",
        location="Seattle, WA",
        url="https://example.com/jobs/123",
        source="test",
        status=status,
        resume_used="data/resumes/sde_resume.pdf",
    ))


def make_service(
    database: JobDatabase,
    *,
    active_session_lookup=lambda job_id: None,
):
    runner = MagicMock(database=database)
    service = DashboardSubmissionRecordingService(
        runner=runner,
        active_session_lookup=active_session_lookup,
        token_factory=lambda: "submission-token",
        authorization_ttl_seconds=120,
    )
    return service, runner


def test_prepare_issues_one_time_authorization_for_exact_saved_job(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    service, runner = make_service(database)

    prepared = service.prepare(job_id)

    assert prepared.status == SubmissionReviewStatus.READY
    assert prepared.authorization_token == "submission-token"
    assert prepared.authorization_expires_in_seconds == 120
    assert prepared.job.status == ApplicationStatus.FORM_STARTED
    assert prepared.may_submit is False
    runner.record.assert_not_called()


def test_prepare_rejects_ineligible_lifecycle(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database, status=ApplicationStatus.DISCOVERED)
    service, _ = make_service(database)

    prepared = service.prepare(job_id)

    assert prepared.status == SubmissionReviewStatus.NOT_ELIGIBLE
    assert prepared.authorization_token is None


def test_active_review_browser_blocks_preparation(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    service, _ = make_service(
        database,
        active_session_lookup=lambda candidate: object(),
    )

    prepared = service.prepare(job_id)

    assert prepared.status == SubmissionReviewStatus.SESSION_ACTIVE
    assert prepared.authorization_token is None


def test_confirmed_recording_requires_exact_confirmation_and_evidence(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    service, runner = make_service(database)
    token = service.prepare(job_id).authorization_token

    denied = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="CONFIRMED",
        confirmation="wrong",
        evidence="Portal confirmation 123",
    )
    missing_evidence = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="CONFIRMED",
        confirmation="RECORD_CONFIRMED_SUBMISSION",
        evidence="  ",
    )

    assert denied.status == DashboardSubmissionStatus.AUTHORIZATION_DENIED
    assert missing_evidence.status == DashboardSubmissionStatus.INVALID_EVIDENCE
    runner.record.assert_not_called()


def test_confirmed_recording_forwards_explicit_facts_once(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    service, runner = make_service(database)
    job = database.get_job_by_id(job_id)
    runner.record.return_value = SubmissionRecordingResult(
        job_id=job_id,
        job=job,
        outcome=SubmissionConfirmationOutcome.CONFIRMED,
        reason="Confirmed.",
        export_path=Path("tracker.xlsx"),
    )
    token = service.prepare(job_id).authorization_token

    result = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="CONFIRMED",
        confirmation="RECORD_CONFIRMED_SUBMISSION",
        evidence="Portal displayed confirmation 123",
    )
    replay = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="CONFIRMED",
        confirmation="RECORD_CONFIRMED_SUBMISSION",
        evidence="Portal displayed confirmation 123",
    )

    assert result.status == DashboardSubmissionStatus.CONFIRMED
    assert result.may_submit is False
    runner.record.assert_called_once_with(
        job_id=job_id,
        submitted=True,
        success_confirmed=True,
        evidence="Portal displayed confirmation 123",
    )
    assert replay.status == DashboardSubmissionStatus.AUTHORIZATION_DENIED


def test_unconfirmed_and_not_submitted_map_to_safe_runner_inputs(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    service, runner = make_service(database)
    job = database.get_job_by_id(job_id)
    runner.record.return_value = SubmissionRecordingResult(
        job_id=job_id,
        job=job,
        outcome=SubmissionConfirmationOutcome.UNCONFIRMED,
        reason="Unconfirmed.",
    )

    token = service.prepare(job_id).authorization_token
    result = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="UNCONFIRMED",
        confirmation="RECORD_UNCONFIRMED_SUBMISSION",
        evidence="No confirmation page appeared",
    )

    assert result.status == DashboardSubmissionStatus.UNCONFIRMED
    runner.record.assert_called_once_with(
        job_id=job_id,
        submitted=True,
        success_confirmed=False,
        evidence="No confirmation page appeared",
    )

    runner.reset_mock()
    runner.record.return_value = SubmissionRecordingResult(
        job_id=job_id,
        job=job,
        outcome=SubmissionConfirmationOutcome.NOT_SUBMITTED,
        reason="Not submitted.",
    )
    token = service.prepare(job_id).authorization_token
    result = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="NOT_SUBMITTED",
        confirmation="RECORD_NOT_SUBMITTED",
        evidence=None,
    )

    assert result.status == DashboardSubmissionStatus.NOT_SUBMITTED
    runner.record.assert_called_once_with(
        job_id=job_id,
        submitted=False,
        success_confirmed=False,
        evidence=None,
    )


def test_changed_persisted_job_invalidates_prepared_recording(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    service, runner = make_service(database)
    token = service.prepare(job_id).authorization_token
    database.update_application_state(
        job_id,
        ApplicationStatus.SUBMISSION_UNCONFIRMED,
        "Changed after preview.",
    )

    result = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="NOT_SUBMITTED",
        confirmation="RECORD_NOT_SUBMITTED",
        evidence=None,
    )

    assert result.status == DashboardSubmissionStatus.PREVIEW_STALE
    runner.record.assert_not_called()


def test_expired_recording_authorization_fails_closed(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    now = [100.0]
    runner = MagicMock(database=database)
    service = DashboardSubmissionRecordingService(
        runner=runner,
        clock=lambda: now[0],
        token_factory=lambda: "expiring-token",
        authorization_ttl_seconds=10,
    )
    token = service.prepare(job_id).authorization_token
    now[0] = 111.0

    result = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="NOT_SUBMITTED",
        confirmation="RECORD_NOT_SUBMITTED",
        evidence=None,
    )

    assert result.status == DashboardSubmissionStatus.AUTHORIZATION_EXPIRED
    runner.record.assert_not_called()


def test_browser_session_started_after_preview_blocks_recording(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = persist_job(database)
    active = [False]
    service, runner = make_service(
        database,
        active_session_lookup=(
            lambda candidate: object() if active[0] else None
        ),
    )
    token = service.prepare(job_id).authorization_token
    active[0] = True

    result = service.record(
        job_id=job_id,
        authorization_token=token,
        outcome="NOT_SUBMITTED",
        confirmation="RECORD_NOT_SUBMITTED",
        evidence=None,
    )

    assert result.status == DashboardSubmissionStatus.SESSION_ACTIVE
    runner.record.assert_not_called()


def test_service_has_no_browser_or_submission_capability(tmp_path: Path) -> None:
    service, _ = make_service(JobDatabase(tmp_path / "jobs.db"))

    assert service.may_submit is False
    assert not hasattr(service, "browser")
    assert not hasattr(service, "submit")
    assert not hasattr(service, "click_submit")
