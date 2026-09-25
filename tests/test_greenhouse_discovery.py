from __future__ import annotations

from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.discovery.base import RawJobPosting
from app.discovery.greenhouse import (
    GreenhouseDiscoveryError,
    GreenhouseJobSource,
)
from app.jobs.models import Job


# ============================================================
# Test helpers
# ============================================================


def make_source() -> GreenhouseJobSource:
    """
    Create a standard Greenhouse source used throughout the tests.
    """

    return GreenhouseJobSource(
        company="Example Tech",
        board_token="exampletech",
    )


def make_payload() -> dict:
    """
    Return a representative Greenhouse job payload.

    This payload is intentionally deterministic so tests do not depend
    on any real external Greenhouse job board.
    """

    return {
        "id": 123456,
        "title": "Software Engineer I",
        "absolute_url": (
            "https://boards.greenhouse.io/example/jobs/123456"
        ),
        "location": {
            "name": "Seattle, WA",
        },
        "content": "Build scalable Python backend services.",
        "updated_at": "2026-09-25T10:30:00-07:00",
    }


class FakeHTTPResponse:
    """
    Minimal context-manager HTTP response used to test network retrieval
    without making real internet requests.
    """

    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False


# ============================================================
# Constructor and source configuration tests
# ============================================================


def test_source_name_is_greenhouse():
    source = make_source()

    assert source.source_name == "greenhouse"


def test_constructor_strips_values():
    source = GreenhouseJobSource(
        company="  Example Tech  ",
        board_token="  exampletech  ",
    )

    assert source.company == "Example Tech"
    assert source.board_token == "exampletech"


def test_empty_company_is_rejected():
    with pytest.raises(
        ValueError,
        match="company must not be empty",
    ):
        GreenhouseJobSource(
            company="   ",
            board_token="exampletech",
        )


def test_empty_board_token_is_rejected():
    with pytest.raises(
        ValueError,
        match="board_token must not be empty",
    ):
        GreenhouseJobSource(
            company="Example Tech",
            board_token="   ",
        )


def test_invalid_timeout_is_rejected():
    with pytest.raises(
        ValueError,
        match="timeout_seconds must be greater than zero",
    ):
        GreenhouseJobSource(
            company="Example Tech",
            board_token="exampletech",
            timeout_seconds=0,
        )


def test_jobs_url_uses_board_token_and_requests_content():
    source = make_source()

    assert source.jobs_url == (
        "https://boards-api.greenhouse.io/v1/boards/"
        "exampletech/jobs?content=true"
    )


# ============================================================
# Greenhouse payload normalization tests
# ============================================================


def test_normalize_payload_creates_raw_job_posting():
    source = make_source()

    raw_job = source.normalize_payload(make_payload())

    assert isinstance(raw_job, RawJobPosting)
    assert raw_job.source == "greenhouse"
    assert raw_job.company == "Example Tech"
    assert raw_job.title == "Software Engineer I"
    assert raw_job.location == "Seattle, WA"

    assert raw_job.url == (
        "https://boards.greenhouse.io/example/jobs/123456"
    )

    assert (
        raw_job.description
        == "Build scalable Python backend services."
    )

    assert raw_job.external_job_id == "123456"
    assert raw_job.date_posted == "2026-09-25"

    assert raw_job.metadata == {
        "board_token": "exampletech",
    }


def test_normalize_payload_allows_missing_location():
    source = make_source()

    payload = make_payload()
    payload["location"] = None

    raw_job = source.normalize_payload(payload)

    assert raw_job.location is None


def test_normalize_payload_allows_missing_description():
    source = make_source()

    payload = make_payload()
    payload["content"] = None

    raw_job = source.normalize_payload(payload)

    assert raw_job.description is None


def test_normalize_payload_allows_missing_updated_at():
    source = make_source()

    payload = make_payload()
    payload["updated_at"] = None

    raw_job = source.normalize_payload(payload)

    assert raw_job.date_posted is None


def test_missing_job_id_is_rejected():
    source = make_source()

    payload = make_payload()
    payload.pop("id")

    with pytest.raises(
        ValueError,
        match="Greenhouse job payload is missing id",
    ):
        source.normalize_payload(payload)


def test_missing_title_is_rejected():
    source = make_source()

    payload = make_payload()
    payload["title"] = ""

    with pytest.raises(
        ValueError,
        match="Greenhouse job payload is missing a valid title",
    ):
        source.normalize_payload(payload)


def test_missing_absolute_url_is_rejected():
    source = make_source()

    payload = make_payload()
    payload["absolute_url"] = None

    with pytest.raises(
        ValueError,
        match=(
            "Greenhouse job payload is missing "
            "a valid absolute_url"
        ),
    ):
        source.normalize_payload(payload)


# ============================================================
# Common Job normalization tests
# ============================================================


def test_normalize_creates_common_job_model():
    source = make_source()

    raw_job = source.normalize_payload(make_payload())

    job = source.normalize(raw_job)

    assert isinstance(job, Job)
    assert job.company == "Example Tech"
    assert job.title == "Software Engineer I"
    assert job.location == "Seattle, WA"

    assert str(job.url) == (
        "https://boards.greenhouse.io/example/jobs/123456"
    )

    assert job.source == "greenhouse"

    assert (
        job.description
        == "Build scalable Python backend services."
    )

    assert job.external_job_id == "123456"
    assert job.date_posted == date(2026, 9, 25)


def test_greenhouse_metadata_does_not_leak_into_job():
    source = make_source()

    raw_job = source.normalize_payload(make_payload())

    assert raw_job.metadata["board_token"] == "exampletech"

    job = source.normalize(raw_job)

    assert not hasattr(job, "metadata")


def test_normalization_does_not_run_pipeline_logic():
    source = make_source()

    job = source.normalize(
        source.normalize_payload(make_payload())
    )

    assert job.fit_score is None
    assert job.resume_used is None


# ============================================================
# Successful mocked network discovery tests
# ============================================================


def test_discover_retrieves_and_normalizes_job():
    source = make_source()

    response_body = b"""
    {
        "jobs": [
            {
                "id": 123456,
                "title": "Software Engineer I",
                "absolute_url":
                    "https://boards.greenhouse.io/example/jobs/123456",
                "location": {
                    "name": "Seattle, WA"
                },
                "content":
                    "Build scalable Python backend services.",
                "updated_at":
                    "2026-09-25T10:30:00-07:00"
            }
        ]
    }
    """

    with patch(
        "app.discovery.greenhouse.urlopen",
        return_value=FakeHTTPResponse(response_body),
    ) as mocked_urlopen:
        jobs = source.discover()

    assert len(jobs) == 1

    raw_job = jobs[0]

    assert isinstance(raw_job, RawJobPosting)
    assert raw_job.company == "Example Tech"
    assert raw_job.title == "Software Engineer I"
    assert raw_job.location == "Seattle, WA"
    assert raw_job.external_job_id == "123456"
    assert raw_job.date_posted == "2026-09-25"

    mocked_urlopen.assert_called_once()

    request = mocked_urlopen.call_args.args[0]

    timeout = mocked_urlopen.call_args.kwargs[
        "timeout"
    ]

    assert request.full_url == source.jobs_url
    assert timeout == source.timeout_seconds


def test_discover_returns_multiple_jobs():
    source = make_source()

    response_body = b"""
    {
        "jobs": [
            {
                "id": 1,
                "title": "Software Engineer I",
                "absolute_url":
                    "https://example.com/jobs/1",
                "location": {
                    "name": "Seattle, WA"
                }
            },
            {
                "id": 2,
                "title": "Machine Learning Engineer",
                "absolute_url":
                    "https://example.com/jobs/2",
                "location": {
                    "name": "Remote"
                }
            }
        ]
    }
    """

    with patch(
        "app.discovery.greenhouse.urlopen",
        return_value=FakeHTTPResponse(response_body),
    ):
        jobs = source.discover()

    assert len(jobs) == 2

    assert jobs[0].external_job_id == "1"
    assert jobs[1].external_job_id == "2"

    assert jobs[0].title == "Software Engineer I"
    assert jobs[1].title == "Machine Learning Engineer"


def test_discover_allows_empty_job_board():
    source = make_source()

    with patch(
        "app.discovery.greenhouse.urlopen",
        return_value=FakeHTTPResponse(
            b'{"jobs": []}'
        ),
    ):
        jobs = source.discover()

    assert jobs == []


# ============================================================
# Network error handling tests
# ============================================================


def test_http_error_becomes_discovery_error():
    source = make_source()

    http_error = HTTPError(
        url=source.jobs_url,
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )

    with patch(
        "app.discovery.greenhouse.urlopen",
        side_effect=http_error,
    ):
        with pytest.raises(
            GreenhouseDiscoveryError,
            match="HTTP status 404",
        ):
            source.discover()


def test_url_error_becomes_discovery_error():
    source = make_source()

    with patch(
        "app.discovery.greenhouse.urlopen",
        side_effect=URLError(
            "connection refused"
        ),
    ):
        with pytest.raises(
            GreenhouseDiscoveryError,
            match="connection refused",
        ):
            source.discover()


def test_timeout_becomes_discovery_error():
    source = make_source()

    with patch(
        "app.discovery.greenhouse.urlopen",
        side_effect=TimeoutError(),
    ):
        with pytest.raises(
            GreenhouseDiscoveryError,
            match="timed out",
        ):
            source.discover()


# ============================================================
# Invalid response handling tests
# ============================================================


def test_invalid_json_becomes_discovery_error():
    source = make_source()

    with patch(
        "app.discovery.greenhouse.urlopen",
        return_value=FakeHTTPResponse(
            b"not valid json"
        ),
    ):
        with pytest.raises(
            GreenhouseDiscoveryError,
            match="invalid JSON",
        ):
            source.discover()


def test_top_level_json_array_is_rejected():
    source = make_source()

    with patch(
        "app.discovery.greenhouse.urlopen",
        return_value=FakeHTTPResponse(
            b"[]"
        ),
    ):
        with pytest.raises(
            GreenhouseDiscoveryError,
            match="JSON object",
        ):
            source.discover()


def test_missing_jobs_list_is_rejected():
    source = make_source()

    with patch(
        "app.discovery.greenhouse.urlopen",
        return_value=FakeHTTPResponse(
            b'{"message": "hello"}'
        ),
    ):
        with pytest.raises(
            GreenhouseDiscoveryError,
            match="valid jobs list",
        ):
            source.discover()


def test_non_list_jobs_value_is_rejected():
    source = make_source()

    with patch(
        "app.discovery.greenhouse.urlopen",
        return_value=FakeHTTPResponse(
            b'{"jobs": {}}'
        ),
    ):
        with pytest.raises(
            GreenhouseDiscoveryError,
            match="valid jobs list",
        ):
            source.discover()


def test_invalid_job_entry_is_rejected():
    source = make_source()

    with patch(
        "app.discovery.greenhouse.urlopen",
        return_value=FakeHTTPResponse(
            b'{"jobs": ["not-a-job-object"]}'
        ),
    ):
        with pytest.raises(
            GreenhouseDiscoveryError,
            match="invalid job payload",
        ):
            source.discover()