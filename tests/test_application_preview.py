from __future__ import annotations

from pathlib import Path

import pytest

from app.applications.adapters.detector import ATSProvider
from app.dashboard.application_preview import (
    ApplicationPreviewService,
    ApplicationPreviewStatus,
)
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)
from app.tracking.database import JobDatabase


def add_job(
    database: JobDatabase,
    *,
    status: ApplicationStatus = ApplicationStatus.NEEDS_APPLICATION,
    company_rule: CompanyRule = CompanyRule.AUTO,
    application_method: ApplicationMethod = ApplicationMethod.AUTO,
    application_url: str | None = (
        "https://job-boards.greenhouse.io/example/jobs/123"
    ),
) -> int:
    return database.add_job(Job(
        company="Example",
        title="Software Engineer I",
        location="Seattle, WA",
        url="https://www.linkedin.com/jobs/view/123",
        application_url=application_url,
        source="test",
        status=status,
        company_rule=company_rule,
        application_method=application_method,
        resume_used="data/resumes/sde_resume.pdf",
        fit_score=92,
    ))


def test_preview_exposes_exact_browser_free_application_plan(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(database)
    service = ApplicationPreviewService(database=database)

    result = service.preview(job_id)

    assert result.status == ApplicationPreviewStatus.READY
    assert result.job_id == job_id
    assert result.job is not None
    assert result.job.company == "Example"
    assert result.source_url == "https://www.linkedin.com/jobs/view/123"
    assert result.application_url == (
        "https://job-boards.greenhouse.io/example/jobs/123"
    )
    assert result.provider == ATSProvider.GREENHOUSE
    assert result.resume == "data/resumes/sde_resume.pdf"
    assert result.browser_started is False
    assert result.workflow_ran is False
    assert result.may_submit is False
    assert database.get_job_by_id(job_id).status == (
        ApplicationStatus.NEEDS_APPLICATION
    )


def test_preview_reports_missing_job_without_side_effects(tmp_path: Path) -> None:
    service = ApplicationPreviewService(
        database=JobDatabase(tmp_path / "jobs.db")
    )

    result = service.preview(999)

    assert result.status == ApplicationPreviewStatus.NOT_FOUND
    assert result.job is None
    assert result.browser_started is False
    assert result.workflow_ran is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"status": ApplicationStatus.NEEDS_REVIEW},
            "NEEDS_APPLICATION",
        ),
        (
            {"company_rule": CompanyRule.MANUAL},
            "routing",
        ),
        (
            {"application_method": ApplicationMethod.MANUAL},
            "not AUTO",
        ),
        (
            {"application_url": None},
            "verified supported application target",
        ),
    ],
)
def test_preview_fails_closed_with_a_specific_reason(
    tmp_path: Path,
    overrides: dict[str, object],
    reason: str,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(database, **overrides)

    result = ApplicationPreviewService(database=database).preview(job_id)

    assert result.status == ApplicationPreviewStatus.BLOCKED
    assert reason in result.reason
    assert result.browser_started is False
    assert result.workflow_ran is False
    assert result.may_submit is False


def test_preview_service_exposes_no_execution_or_submission_capability(
    tmp_path: Path,
) -> None:
    service = ApplicationPreviewService(
        database=JobDatabase(tmp_path / "jobs.db")
    )

    assert not hasattr(service, "coordinator")
    assert not hasattr(service, "browser")
    assert not hasattr(service, "run")
    assert not hasattr(service, "submit")
    assert not hasattr(service, "confirm_submission")
