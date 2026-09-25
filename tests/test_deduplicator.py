from app.jobs.deduplicator import (
    DuplicateReason,
    JobDeduplicator,
)
from app.jobs.models import Job


def make_job(
    company: str = "Example Company",
    title: str = "Software Engineer",
    location: str | None = "Seattle, WA",
    url: str = "https://example.com/jobs/123",
    source: str = "Test",
    external_job_id: str | None = None,
) -> Job:
    return Job(
        company=company,
        title=title,
        location=location,
        url=url,
        source=source,
        external_job_id=external_job_id,
    )


def test_exact_url_is_duplicate():
    first = make_job()

    second = make_job(
        source="Different Source",
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is True
    assert result.reason == DuplicateReason.URL
    assert result.matched_job == first


def test_trailing_slash_url_is_duplicate():
    first = make_job(
        url="https://example.com/jobs/123/"
    )

    second = make_job(
        url="https://example.com/jobs/123"
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is True
    assert result.reason == DuplicateReason.URL


def test_tracking_parameter_is_ignored():
    first = make_job(
        url="https://example.com/jobs/123"
    )

    second = make_job(
        url=(
            "https://example.com/jobs/123"
            "?utm_source=linkedin&utm_campaign=jobs"
        )
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is True
    assert result.reason == DuplicateReason.URL


def test_different_meaningful_query_parameter_is_not_same_url():
    first = make_job(
        url="https://example.com/job?id=123",
        title="Software Engineer",
        location="Seattle, WA",
    )

    second = make_job(
        url="https://example.com/job?id=456",
        title="Data Scientist",
        location="Boston, MA",
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is False


def test_same_company_and_external_job_id_is_duplicate():
    first = make_job(
        url="https://linkedin.com/jobs/view/123",
        external_job_id="ABC-123",
    )

    second = make_job(
        url="https://company.com/careers/abc-123",
        source="Company Careers",
        external_job_id="abc-123",
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is True
    assert result.reason == DuplicateReason.EXTERNAL_JOB_ID


def test_same_external_id_different_company_is_not_duplicate():
    first = make_job(
        company="Company A",
        title="Software Engineer",
        location="Seattle, WA",
        url="https://companya.com/jobs/123",
        external_job_id="123",
    )

    second = make_job(
        company="Company B",
        title="Data Scientist",
        location="Boston, MA",
        url="https://companyb.com/jobs/123",
        external_job_id="123",
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is False


def test_same_company_title_location_is_duplicate():
    first = make_job(
        company="Example Company",
        title="Software Engineer",
        location="Seattle, WA",
        url="https://linkedin.com/jobs/111",
    )

    second = make_job(
        company="example company",
        title=" software   engineer ",
        location="Seattle, WA",
        url="https://company.com/jobs/222",
        source="Company Careers",
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is True
    assert (
        result.reason
        == DuplicateReason.COMPANY_TITLE_LOCATION
    )


def test_different_title_is_not_duplicate():
    first = make_job(
        title="Software Engineer",
        url="https://example.com/jobs/1",
    )

    second = make_job(
        title="Software Engineer I",
        url="https://example.com/jobs/2",
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is False


def test_different_location_is_not_duplicate():
    first = make_job(
        location="Seattle, WA",
        url="https://example.com/jobs/1",
    )

    second = make_job(
        location="New York, NY",
        url="https://example.com/jobs/2",
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is False


def test_missing_locations_do_not_trigger_fallback_duplicate():
    first = make_job(
        location=None,
        url="https://example.com/jobs/1",
    )

    second = make_job(
        location=None,
        url="https://example.com/jobs/2",
    )

    result = JobDeduplicator.compare(
        second,
        first,
    )

    assert result.is_duplicate is False


def test_find_duplicate_in_collection():
    existing_jobs = [
        make_job(
            company="Company A",
            title="Data Scientist",
            location="Boston, MA",
            url="https://example.com/jobs/1",
        ),
        make_job(
            company="Company B",
            title="Software Engineer",
            location="Seattle, WA",
            url="https://example.com/jobs/2",
            external_job_id="JOB-200",
        ),
    ]

    incoming = make_job(
        company="Company B",
        title="Software Engineer",
        location="Seattle, WA",
        url="https://different-source.com/jobs/200",
        external_job_id="JOB-200",
    )

    result = JobDeduplicator.find_duplicate(
        incoming,
        existing_jobs,
    )

    assert result.is_duplicate is True
    assert result.reason == DuplicateReason.EXTERNAL_JOB_ID
    assert result.matched_job == existing_jobs[1]


def test_find_duplicate_returns_false_for_unique_job():
    existing_jobs = [
        make_job(
            company="Company A",
            title="Software Engineer",
            location="Seattle, WA",
            url="https://example.com/jobs/1",
        )
    ]

    incoming = make_job(
        company="Company B",
        title="Data Scientist",
        location="Boston, MA",
        url="https://example.com/jobs/2",
    )

    result = JobDeduplicator.find_duplicate(
        incoming,
        existing_jobs,
    )

    assert result.is_duplicate is False
    assert result.reason is None
    assert result.matched_job is None