from pathlib import Path

import pytest

from app.applications.router import (
    ApplicationPreparationService,
    PreparationOutcome,
)
from app.applications.validator import ApplicationValidator
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)
from app.jobs.pipeline import (
    PipelineOutcome,
    PipelineResult,
)
from app.tracking.database import JobDatabase


@pytest.fixture
def resume_file(tmp_path: Path) -> Path:
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"test resume")
    return path


@pytest.fixture
def database(tmp_path: Path) -> JobDatabase:
    return JobDatabase(
        tmp_path / "preparation_test.db"
    )


@pytest.fixture
def service(
    database: JobDatabase,
) -> ApplicationPreparationService:
    return ApplicationPreparationService(
        validator=ApplicationValidator(),
        database=database,
    )


def make_job(
    resume_file: Path,
    *,
    status: ApplicationStatus = (
        ApplicationStatus.NEEDS_APPLICATION
    ),
) -> Job:
    return Job(
        company="Example Company",
        title="Software Engineer",
        location="Seattle, WA",
        url="https://example.com/jobs/123",
        source="test",
        company_rule=CompanyRule.AUTO,
        application_method=ApplicationMethod.AUTO,
        status=status,
        resume_used=str(resume_file),
    )


def persist_pipeline_result(
    database: JobDatabase,
    job: Job,
    outcome: PipelineOutcome = PipelineOutcome.AUTO_READY,
) -> PipelineResult:
    job_id = database.add_job(job)

    return PipelineResult(
        job=job,
        outcome=outcome,
        reason="Test pipeline result.",
        job_id=job_id,
    )


def test_auto_ready_job_becomes_ready_and_is_persisted(
    service,
    database,
    resume_file,
):
    job = make_job(resume_file)

    pipeline_result = persist_pipeline_result(
        database,
        job,
    )

    result = service.prepare(pipeline_result)

    assert result.outcome == PreparationOutcome.READY
    assert result.should_continue is True
    assert job.status == ApplicationStatus.READY_TO_APPLY

    stored = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored is not None
    assert stored.status == ApplicationStatus.READY_TO_APPLY


def test_missing_resume_review_state_is_persisted(
    service,
    database,
    tmp_path,
):
    missing_resume = tmp_path / "missing.pdf"

    job = make_job(missing_resume)

    pipeline_result = persist_pipeline_result(
        database,
        job,
    )

    result = service.prepare(pipeline_result)

    assert result.outcome == PreparationOutcome.NEEDS_REVIEW
    assert result.should_continue is False
    assert job.status == ApplicationStatus.NEEDS_REVIEW

    stored = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW


def test_manual_company_review_state_is_persisted(
    service,
    database,
    resume_file,
):
    job = make_job(resume_file)
    job.company_rule = CompanyRule.MANUAL

    pipeline_result = persist_pipeline_result(
        database,
        job,
    )

    result = service.prepare(pipeline_result)

    assert result.outcome == PreparationOutcome.NEEDS_REVIEW

    stored = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW


def test_missing_job_id_fails_closed(
    service,
    resume_file,
):
    job = make_job(resume_file)

    pipeline_result = PipelineResult(
        job=job,
        outcome=PipelineOutcome.AUTO_READY,
        reason="Test result.",
        job_id=None,
    )

    result = service.prepare(pipeline_result)

    assert result.outcome == PreparationOutcome.NOT_ELIGIBLE
    assert result.should_continue is False

    # Validation was never attempted.
    assert job.status == ApplicationStatus.NEEDS_APPLICATION


@pytest.mark.parametrize(
    "outcome",
    [
        PipelineOutcome.DUPLICATE,
        PipelineOutcome.FILTERED_OUT,
        PipelineOutcome.BLOCKED,
        PipelineOutcome.MANUAL_REVIEW,
    ],
)
def test_non_auto_ready_result_does_not_mutate_database(
    service,
    database,
    resume_file,
    outcome,
):
    job = make_job(resume_file)

    pipeline_result = persist_pipeline_result(
        database,
        job,
        outcome=outcome,
    )

    result = service.prepare(pipeline_result)

    assert result.outcome == PreparationOutcome.NOT_ELIGIBLE
    assert result.should_continue is False

    assert job.status == ApplicationStatus.NEEDS_APPLICATION

    stored = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_APPLICATION


def test_missing_database_row_rolls_back_memory_state(
    service,
    resume_file,
):
    job = make_job(resume_file)

    pipeline_result = PipelineResult(
        job=job,
        outcome=PipelineOutcome.AUTO_READY,
        reason="Test result.",
        job_id=999999,
    )

    with pytest.raises(ValueError):
        service.prepare(pipeline_result)

    # Validator temporarily changed this to READY_TO_APPLY,
    # but persistence failed. Memory must match SQLite reality.
    assert job.status == ApplicationStatus.NEEDS_APPLICATION


def test_wrong_starting_status_is_not_persisted(
    service,
    database,
    resume_file,
):
    job = make_job(
        resume_file,
        status=ApplicationStatus.APPLIED,
    )

    pipeline_result = persist_pipeline_result(
        database,
        job,
    )

    result = service.prepare(pipeline_result)

    assert result.outcome == PreparationOutcome.NOT_ELIGIBLE
    assert job.status == ApplicationStatus.APPLIED

    stored = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored is not None
    assert stored.status == ApplicationStatus.APPLIED