import pytest
from pydantic import ValidationError

from app.jobs.models import (
    ApplicationStatus,
    Job,
    JobCategory,
)


def test_create_basic_job() -> None:
    job = Job(
        company="Example Company",
        title="Software Engineer I",
        location="Tempe, AZ",
        url="https://example.com/jobs/123",
        source="Test",
    )

    assert job.company == "Example Company"
    assert job.title == "Software Engineer I"

    assert job.category == JobCategory.OTHER
    assert job.status == ApplicationStatus.DISCOVERED

    assert job.fit_score is None
    assert job.priority_company is False


def test_fit_score_validation() -> None:
    with pytest.raises(ValidationError):
        Job(
            company="Example Company",
            title="Software Engineer",
            url="https://example.com/jobs/123",
            source="Test",
            fit_score=120,
        )


def test_company_required() -> None:
    with pytest.raises(ValidationError):
        Job(
            company="",
            title="Software Engineer",
            url="https://example.com/jobs/123",
            source="Test",
        )


def test_invalid_url_rejected() -> None:
    with pytest.raises(ValidationError):
        Job(
            company="Example Company",
            title="Software Engineer",
            url="not-a-valid-url",
            source="Test",
        )