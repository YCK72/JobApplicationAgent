from pathlib import Path

import pytest

from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.tracking.database import JobDatabase


@pytest.fixture
def database(tmp_path: Path) -> JobDatabase:
    """
    Create an isolated temporary database for each test.
    """

    db_path = tmp_path / "test_jobs.db"

    return JobDatabase(db_path)


@pytest.fixture
def sample_job() -> Job:
    return Job(
        company="Example Company",
        title="Software Engineer I",
        location="Tempe, AZ",
        url="https://example.com/jobs/123",
        source="Test",
    )


def test_database_creation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test_jobs.db"

    JobDatabase(db_path)

    assert db_path.exists()


def test_add_and_retrieve_job(
    database: JobDatabase,
    sample_job: Job,
) -> None:
    job_id = database.add_job(sample_job)

    retrieved = database.get_job_by_id(job_id)

    assert retrieved is not None
    assert retrieved.company == "Example Company"
    assert retrieved.title == "Software Engineer I"
    assert retrieved.status == ApplicationStatus.DISCOVERED


def test_duplicate_url_rejected(
    database: JobDatabase,
    sample_job: Job,
) -> None:
    database.add_job(sample_job)

    with pytest.raises(ValueError):
        database.add_job(sample_job)


def test_job_exists(
    database: JobDatabase,
    sample_job: Job,
) -> None:
    assert database.job_exists(
        sample_job.url.encoded_string()
    ) is False

    database.add_job(sample_job)

    assert database.job_exists(
        sample_job.url.encoded_string()
    ) is True


def test_update_status(
    database: JobDatabase,
    sample_job: Job,
) -> None:
    job_id = database.add_job(sample_job)

    database.update_status(
        job_id,
        ApplicationStatus.NEEDS_REVIEW,
    )

    retrieved = database.get_job_by_id(job_id)

    assert retrieved is not None
    assert (
        retrieved.status
        == ApplicationStatus.NEEDS_REVIEW
    )


def test_update_fit_score(
    database: JobDatabase,
    sample_job: Job,
) -> None:
    job_id = database.add_job(sample_job)

    database.update_fit_score(
        job_id,
        87.5,
        "Strong Python and backend match.",
    )

    retrieved = database.get_job_by_id(job_id)

    assert retrieved is not None
    assert retrieved.fit_score == 87.5
    assert (
        retrieved.fit_explanation
        == "Strong Python and backend match."
    )


def test_invalid_fit_score_rejected(
    database: JobDatabase,
    sample_job: Job,
) -> None:
    job_id = database.add_job(sample_job)

    with pytest.raises(ValueError):
        database.update_fit_score(
            job_id,
            150,
        )


def test_mark_applied(
    database: JobDatabase,
    sample_job: Job,
) -> None:
    job_id = database.add_job(sample_job)

    database.mark_applied(
        job_id,
        "data/resumes/sde_resume.pdf",
    )

    retrieved = database.get_job_by_id(job_id)

    assert retrieved is not None
    assert retrieved.status == ApplicationStatus.APPLIED
    assert retrieved.date_applied is not None
    assert (
        retrieved.resume_used
        == "data/resumes/sde_resume.pdf"
    )


def test_get_all_jobs(
    database: JobDatabase,
) -> None:
    first = Job(
        company="Company One",
        title="Software Engineer",
        url="https://example.com/jobs/1",
        source="Test",
    )

    second = Job(
        company="Company Two",
        title="ML Engineer",
        url="https://example.com/jobs/2",
        source="Test",
    )

    database.add_job(first)
    database.add_job(second)

    jobs = database.get_all_jobs()

    assert len(jobs) == 2