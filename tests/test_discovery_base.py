from __future__ import annotations

from datetime import date

import pytest

from app.discovery.base import JobSource, RawJobPosting
from app.jobs.models import Job


class FakeJobSource(JobSource):
    """
    Small deterministic discovery source used only for testing the
    JobSource contract.
    """

    @property
    def source_name(self) -> str:
        return "fake_source"

    def discover(self) -> list[RawJobPosting]:
        return [
            RawJobPosting(
                source=self.source_name,
                company="Example Company",
                title="Software Engineer I",
                location="Seattle, WA",
                url="https://example.com/jobs/123",
                description="Build Python backend services.",
                external_job_id="123",
                date_posted="2026-09-25",
                metadata={
                    "department": "Engineering",
                },
            )
        ]

    def normalize(self, raw_job: RawJobPosting) -> Job:
        return Job(
            company=raw_job.company,
            title=raw_job.title,
            location=raw_job.location,
            url=raw_job.url,
            source=raw_job.source,
            description=raw_job.description,
            external_job_id=raw_job.external_job_id,
            date_posted=raw_job.date_posted,
        )


def test_raw_job_posting_stores_discovered_values():
    raw_job = RawJobPosting(
        source="test_source",
        company="Example Company",
        title="Machine Learning Engineer",
        location="Remote",
        url="https://example.com/jobs/ml-1",
        description="Build machine learning systems.",
        external_job_id="ml-1",
        date_posted="2026-09-25",
        metadata={
            "department": "AI",
        },
    )

    assert raw_job.source == "test_source"
    assert raw_job.company == "Example Company"
    assert raw_job.title == "Machine Learning Engineer"
    assert raw_job.location == "Remote"
    assert raw_job.url == "https://example.com/jobs/ml-1"
    assert raw_job.description == "Build machine learning systems."
    assert raw_job.external_job_id == "ml-1"
    assert raw_job.date_posted == "2026-09-25"
    assert raw_job.metadata == {"department": "AI"}


def test_raw_job_posting_optional_values_default_to_none():
    raw_job = RawJobPosting(
        source="test_source",
        company="Example Company",
        title="Software Engineer",
        url="https://example.com/jobs/1",
    )

    assert raw_job.location is None
    assert raw_job.description is None
    assert raw_job.external_job_id is None
    assert raw_job.date_posted is None
    assert raw_job.metadata == {}


def test_raw_job_posting_metadata_is_not_shared_between_instances():
    first = RawJobPosting(
        source="test_source",
        company="Company One",
        title="Software Engineer",
        url="https://example.com/jobs/1",
    )

    second = RawJobPosting(
        source="test_source",
        company="Company Two",
        title="Software Engineer",
        url="https://example.com/jobs/2",
    )

    first.metadata["department"] = "Engineering"

    assert second.metadata == {}


def test_job_source_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        JobSource()


def test_fake_source_name():
    source = FakeJobSource()

    assert source.source_name == "fake_source"


def test_discover_returns_raw_job_postings():
    source = FakeJobSource()

    discovered = source.discover()

    assert len(discovered) == 1
    assert isinstance(discovered[0], RawJobPosting)
    assert discovered[0].company == "Example Company"
    assert discovered[0].title == "Software Engineer I"


def test_normalize_returns_common_job_model():
    source = FakeJobSource()
    raw_job = source.discover()[0]

    job = source.normalize(raw_job)

    assert isinstance(job, Job)
    assert job.company == "Example Company"
    assert job.title == "Software Engineer I"
    assert job.location == "Seattle, WA"
    assert str(job.url) == "https://example.com/jobs/123"
    assert job.source == "fake_source"
    assert job.description == "Build Python backend services."
    assert job.external_job_id == "123"
    assert job.date_posted == date(2026, 9, 25)

def test_discover_jobs_discovers_and_normalizes():
    source = FakeJobSource()

    jobs = source.discover_jobs()

    assert len(jobs) == 1

    job = jobs[0]

    assert isinstance(job, Job)
    assert job.company == "Example Company"
    assert job.title == "Software Engineer I"
    assert job.source == "fake_source"


def test_discovery_does_not_classify_job():
    source = FakeJobSource()

    job = source.discover_jobs()[0]

    # Discovery normalization must not take over responsibilities that belong
    # to the downstream JobPipeline.
    assert job.fit_score is None
    assert job.resume_used is None


def test_metadata_does_not_leak_into_common_job_model():
    source = FakeJobSource()
    raw_job = source.discover()[0]

    assert raw_job.metadata["department"] == "Engineering"

    job = source.normalize(raw_job)

    assert isinstance(job, Job)
    assert not hasattr(job, "metadata")