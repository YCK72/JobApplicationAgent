import pytest

from app.applications.adapters.detector import (
    ATSDetector,
    ATSProvider,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://boards.greenhouse.io/example/jobs/123",
            ATSProvider.GREENHOUSE,
        ),
        (
            "https://job-boards.greenhouse.io/example/jobs/123",
            ATSProvider.GREENHOUSE,
        ),
        (
            "https://jobs.lever.co/example/123",
            ATSProvider.LEVER,
        ),
        (
            "https://jobs.ashbyhq.com/example/123",
            ATSProvider.ASHBY,
        ),
        (
            "https://company.wd1.myworkdayjobs.com/en-US/jobs/job/123",
            ATSProvider.WORKDAY,
        ),
        (
            "https://company.wd5.myworkdayjobs.com/jobs/job/123",
            ATSProvider.WORKDAY,
        ),
        (
            "https://careers.tiktok.com/resume/7668557209047894325/apply",
            ATSProvider.TIKTOK,
        ),
    ],
)
def test_known_ats_urls_are_detected(
    url,
    expected,
):
    assert ATSDetector.detect(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/jobs/123",
        "https://careers.example.com/jobs/123",
        "https://greenhouse.example.com/jobs/123",
        "https://lever.example.com/jobs/123",
        "https://ashby.example.com/jobs/123",
    ],
)
def test_unknown_hosts_fail_closed(url):
    assert (
        ATSDetector.detect(url)
        == ATSProvider.UNKNOWN
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.lever.co.evil.example/job/123",
        "https://boards.greenhouse.io.evil.example/job/123",
        "https://jobs.ashbyhq.com.evil.example/job/123",
        "https://company.wd1.myworkdayjobs.com.evil.example/job/123",
        "https://careers.tiktok.com.evil.example/resume/123/apply",
    ],
)
def test_spoofed_hosts_fail_closed(url):
    assert (
        ATSDetector.detect(url)
        == ATSProvider.UNKNOWN
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not-a-url",
        "/jobs/123",
        "jobs.lever.co/example/123",
    ],
)
def test_invalid_or_relative_urls_fail_closed(url):
    assert (
        ATSDetector.detect(url)
        == ATSProvider.UNKNOWN
    )


def test_detection_is_case_insensitive():
    assert (
        ATSDetector.detect(
            "https://JOBS.LEVER.CO/example/123"
        )
        == ATSProvider.LEVER
    )


def test_trailing_dot_hostname_is_supported():
    assert (
        ATSDetector.detect(
            "https://jobs.lever.co./example/123"
        )
        == ATSProvider.LEVER
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://myworkdayjobs.com/jobs/123",
        "https://company.myworkdayjobs.com/jobs/123",
        "https://wd1.myworkdayjobs.com/jobs/123",
        "https://company.wdx.myworkdayjobs.com/jobs/123",
    ],
)
def test_malformed_workday_hosts_fail_closed(url):
    assert ATSDetector.detect(url) == ATSProvider.UNKNOWN


def test_non_string_input_fails_closed():
    assert (
        ATSDetector.detect(None)
        == ATSProvider.UNKNOWN
    )
