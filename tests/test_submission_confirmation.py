from pathlib import Path

import pytest

from app.applications.submission_confirmation import (
    SubmissionConfirmation,
    SubmissionConfirmationOutcome,
    SubmissionConfirmationService,
)
from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.tracking.database import JobDatabase


@pytest.fixture
def database(tmp_path: Path) -> JobDatabase:
    return JobDatabase(
        tmp_path / "submission_confirmation.db"
    )


@pytest.fixture
def ready_job() -> Job:
    return Job(
        company="Example Company",
        title="Software Engineer I",
        location="Seattle, WA",
        url="https://example.com/jobs/123",
        source="Test",
        status=ApplicationStatus.READY_TO_APPLY,
        resume_used="data/resumes/sde_resume.pdf",
    )


def persist_job(
    database: JobDatabase,
    job: Job,
) -> int:
    return database.add_job(job)


def test_confirmed_submission_marks_job_applied(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=True,
            evidence=(
                "Application portal displayed a submission "
                "confirmation page."
            ),
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.CONFIRMED
    )
    assert result.job.status == ApplicationStatus.APPLIED
    assert result.job.date_applied is not None
    assert result.confirmed is True

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.APPLIED
    assert stored.date_applied is not None
    assert (
        stored.resume_used
        == "data/resumes/sde_resume.pdf"
    )


def test_uncertain_submission_is_not_marked_applied(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=False,
            evidence=(
                "Submit was attempted, but no independent "
                "success confirmation was available."
            ),
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.UNCONFIRMED
    )
    assert (
        result.job.status
        == ApplicationStatus.SUBMISSION_UNCONFIRMED
    )
    assert result.job.date_applied is None
    assert result.confirmed is False

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert (
        stored.status
        == ApplicationStatus.SUBMISSION_UNCONFIRMED
    )
    assert stored.date_applied is None


def test_not_submitted_does_not_advance_lifecycle(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=False,
            success_confirmed=False,
            evidence=None,
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.NOT_SUBMITTED
    )
    assert (
        result.job.status
        == ApplicationStatus.READY_TO_APPLY
    )
    assert result.job.date_applied is None
    assert result.confirmed is False

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.READY_TO_APPLY
    assert stored.date_applied is None


def test_success_cannot_be_confirmed_without_submission(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=False,
            success_confirmed=True,
            evidence="Invalid contradictory evidence.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.BLOCKED
    )
    assert result.confirmed is False
    assert ready_job.status == ApplicationStatus.READY_TO_APPLY
    assert ready_job.date_applied is None

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.READY_TO_APPLY
    assert stored.date_applied is None


def test_confirmed_submission_requires_evidence(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=True,
            evidence=None,
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.BLOCKED
    )
    assert result.confirmed is False

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.READY_TO_APPLY
    assert stored.date_applied is None


def test_blank_confirmation_evidence_is_rejected(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=True,
            evidence="   ",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.BLOCKED
    )

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.READY_TO_APPLY
    assert stored.date_applied is None


def test_missing_job_id_fails_closed(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=None,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=True,
            evidence="Submission confirmation page displayed.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.BLOCKED
    )
    assert result.confirmed is False
    assert ready_job.status == ApplicationStatus.READY_TO_APPLY
    assert ready_job.date_applied is None


def test_unknown_job_id_fails_without_mutating_job(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=999999,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=True,
            evidence="Submission confirmation page displayed.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.FAILED
    )
    assert result.confirmed is False
    assert ready_job.status == ApplicationStatus.READY_TO_APPLY
    assert ready_job.date_applied is None


def test_database_failure_rolls_back_in_memory_state(
    database: JobDatabase,
    ready_job: Job,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    def fail_mark_applied(
        job_id: int,
        resume_used: str | None = None,
    ) -> None:
        raise RuntimeError("Database write failed.")

    monkeypatch.setattr(
        database,
        "mark_applied",
        fail_mark_applied,
    )

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=True,
            evidence="Submission confirmation page displayed.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.FAILED
    )
    assert result.confirmed is False
    assert ready_job.status == ApplicationStatus.READY_TO_APPLY
    assert ready_job.date_applied is None

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.READY_TO_APPLY
    assert stored.date_applied is None


def test_unconfirmed_database_failure_rolls_back_in_memory_state(
    database: JobDatabase,
    ready_job: Job,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    def fail_update_application_state(
        job_id: int,
        status: ApplicationStatus,
        notes: str | None = None,
    ) -> None:
        raise RuntimeError("Database write failed.")

    monkeypatch.setattr(
        database,
        "update_application_state",
        fail_update_application_state,
    )

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=False,
            evidence="Submission outcome could not be confirmed.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.FAILED
    )
    assert result.confirmed is False
    assert ready_job.status == ApplicationStatus.READY_TO_APPLY
    assert ready_job.date_applied is None

@pytest.mark.parametrize(
    "starting_status",
    [
        ApplicationStatus.DISCOVERED,
        ApplicationStatus.FILTERED_OUT,
        ApplicationStatus.QUALIFIED,
        ApplicationStatus.NEEDS_APPLICATION,
        ApplicationStatus.APPLIED,
        ApplicationStatus.OA,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.REJECTED,
        ApplicationStatus.OFFER,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.ERROR,
    ],
)
def test_invalid_starting_status_blocks_confirmed_submission(
    database: JobDatabase,
    ready_job: Job,
    starting_status: ApplicationStatus,
) -> None:
    ready_job.status = starting_status
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=True,
            evidence="Submission confirmation page displayed.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.BLOCKED
    )
    assert result.confirmed is False
    assert ready_job.status == starting_status
    assert ready_job.date_applied is None

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == starting_status
    assert stored.date_applied is None


@pytest.mark.parametrize(
    "starting_status",
    [
        ApplicationStatus.DISCOVERED,
        ApplicationStatus.FILTERED_OUT,
        ApplicationStatus.QUALIFIED,
        ApplicationStatus.NEEDS_APPLICATION,
        ApplicationStatus.APPLIED,
        ApplicationStatus.OA,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.REJECTED,
        ApplicationStatus.OFFER,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.ERROR,
    ],
)
def test_invalid_starting_status_blocks_unconfirmed_submission(
    database: JobDatabase,
    ready_job: Job,
    starting_status: ApplicationStatus,
) -> None:
    ready_job.status = starting_status
    job_id = persist_job(database, ready_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=False,
            evidence="Submission outcome was unclear.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.BLOCKED
    )
    assert ready_job.status == starting_status
    assert ready_job.date_applied is None

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == starting_status
    assert stored.date_applied is None

def test_mismatched_job_id_blocks_confirmed_submission(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    other_job = Job(
        company="Other Company",
        title="Data Scientist",
        location="Seattle, WA",
        url="https://example.com/jobs/other",
        source="Test",
        status=ApplicationStatus.READY_TO_APPLY,
        resume_used="data/resumes/data_science_resume.pdf",
    )

    ready_job_id = persist_job(database, ready_job)
    other_job_id = persist_job(database, other_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=other_job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=True,
            evidence="Submission confirmation page displayed.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.BLOCKED
    )
    assert result.confirmed is False

    stored_ready_job = database.get_job_by_id(ready_job_id)
    stored_other_job = database.get_job_by_id(other_job_id)

    assert stored_ready_job is not None
    assert stored_other_job is not None

    assert (
        stored_ready_job.status
        == ApplicationStatus.READY_TO_APPLY
    )
    assert (
        stored_other_job.status
        == ApplicationStatus.READY_TO_APPLY
    )

    assert stored_ready_job.date_applied is None
    assert stored_other_job.date_applied is None


def test_mismatched_job_id_blocks_unconfirmed_submission(
    database: JobDatabase,
    ready_job: Job,
) -> None:
    other_job = Job(
        company="Other Company",
        title="Data Scientist",
        location="Seattle, WA",
        url="https://example.com/jobs/other",
        source="Test",
        status=ApplicationStatus.READY_TO_APPLY,
        resume_used="data/resumes/data_science_resume.pdf",
    )

    ready_job_id = persist_job(database, ready_job)
    other_job_id = persist_job(database, other_job)

    service = SubmissionConfirmationService(database)

    result = service.record(
        job=ready_job,
        job_id=other_job_id,
        confirmation=SubmissionConfirmation(
            submitted=True,
            success_confirmed=False,
            evidence="Submission outcome was unclear.",
        ),
    )

    assert (
        result.outcome
        == SubmissionConfirmationOutcome.BLOCKED
    )

    stored_ready_job = database.get_job_by_id(ready_job_id)
    stored_other_job = database.get_job_by_id(other_job_id)

    assert stored_ready_job is not None
    assert stored_other_job is not None

    assert (
        stored_ready_job.status
        == ApplicationStatus.READY_TO_APPLY
    )
    assert (
        stored_other_job.status
        == ApplicationStatus.READY_TO_APPLY
    )

    assert stored_ready_job.date_applied is None
    assert stored_other_job.date_applied is None