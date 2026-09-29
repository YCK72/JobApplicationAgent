from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.applications.target_resolver import (
    ApplicationTargetResolver,
    ApplicationTargetStatus,
)
from app.discovery.composio import LinkedInComposioJobSource
from app.discovery.greenhouse import GreenhouseJobSource
from app.jobs.models import ApplicationStatus, Job
from app.jobs.pipeline import PipelineOutcome
from app.tracking.database import JobDatabase


LINKEDIN_URL = "https://www.linkedin.com/jobs/view/example-role-12345"
TITLE = "Example hiring Software Engineer in Seattle, WA | LinkedIn"
TEXT = (
    "Example hiring Software Engineer in Seattle, WA | LinkedIn\n\n"
    "# Software Engineer\n\nExample Seattle, WA\n\nBuild Python services."
)
GREENHOUSE_URL = (
    "https://job-boards.greenhouse.io/example/jobs/123?gh_src=tracking#apply"
)


def composio_source(page_changes=None):
    page = {"url": LINKEDIN_URL, "title": TITLE, "text": TEXT}
    page.update(page_changes or {})
    client = MagicMock()
    client.search.return_value = {
        "citations": [{"url": LINKEDIN_URL, "title": TITLE}]
    }
    client.fetch.return_value = {"results": [page]}
    return LinkedInComposioJobSource(
        client=client,
        query="software engineer Seattle",
    )


def test_resolver_canonicalizes_explicit_greenhouse_target() -> None:
    result = ApplicationTargetResolver().resolve([GREENHOUSE_URL])

    assert result.status == ApplicationTargetStatus.RESOLVED
    assert result.application_url == (
        "https://job-boards.greenhouse.io/example/jobs/123"
    )
    assert result.provider.value == "GREENHOUSE"


def test_resolver_removes_explicit_default_https_port() -> None:
    result = ApplicationTargetResolver().resolve(
        ["https://boards.greenhouse.io:443/example/jobs/123"]
    )
    assert result.application_url == (
        "https://boards.greenhouse.io/example/jobs/123"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://job-boards.greenhouse.io/example/jobs/123",
        "https://user:pass@job-boards.greenhouse.io/example/jobs/123",
        "https://job-boards.greenhouse.io:444/example/jobs/123",
        "https://job-boards.greenhouse.io.evil.com/example/jobs/123",
        "javascript:alert(1)",
    ],
)
def test_resolver_rejects_unsafe_targets(url: str) -> None:
    result = ApplicationTargetResolver().resolve([url])
    assert result.status == ApplicationTargetStatus.INVALID
    assert result.application_url is None


def test_resolver_rejects_unsupported_ats_by_default() -> None:
    result = ApplicationTargetResolver().resolve(
        ["https://jobs.lever.co/example/abc"]
    )
    assert result.status == ApplicationTargetStatus.UNSUPPORTED
    assert result.application_url is None


def test_resolver_fails_closed_on_multiple_supported_targets() -> None:
    result = ApplicationTargetResolver().resolve(
        [
            "https://boards.greenhouse.io/example/jobs/123",
            "https://boards.greenhouse.io/example/jobs/456",
        ]
    )
    assert result.status == ApplicationTargetStatus.AMBIGUOUS
    assert result.application_url is None


def test_composio_preserves_source_and_resolves_explicit_target() -> None:
    raw = composio_source({"application_url": GREENHOUSE_URL}).discover()[0]
    job = composio_source({"application_url": GREENHOUSE_URL}).normalize(raw)

    assert raw.url == "https://www.linkedin.com/jobs/view/12345"
    assert raw.application_url == (
        "https://job-boards.greenhouse.io/example/jobs/123"
    )
    assert job.url.encoded_string() == (
        "https://www.linkedin.com/jobs/view/12345"
    )
    assert job.application_url.encoded_string() == raw.application_url


def test_composio_does_not_treat_free_text_url_as_application_target() -> None:
    raw = composio_source({"text": TEXT + "\n" + GREENHOUSE_URL}).discover()[0]
    assert raw.application_url is None


def test_composio_accepts_only_explicitly_labeled_apply_link() -> None:
    raw = composio_source({
        "links": [
            {"label": "Company", "href": GREENHOUSE_URL},
            {"label": "Apply now", "href": GREENHOUSE_URL},
        ]
    }).discover()[0]
    assert raw.application_url == (
        "https://job-boards.greenhouse.io/example/jobs/123"
    )


def test_greenhouse_source_uses_absolute_url_as_application_target() -> None:
    raw = GreenhouseJobSource(
        company="Example",
        board_token="example",
    ).normalize_payload({
        "id": 123,
        "title": "Software Engineer",
        "absolute_url": GREENHOUSE_URL,
        "location": {"name": "Seattle, WA"},
        "content": "Build services.",
    })
    job = GreenhouseJobSource(
        company="Example",
        board_token="example",
    ).normalize(raw)

    assert raw.application_url == (
        "https://job-boards.greenhouse.io/example/jobs/123"
    )
    assert job.application_url.encoded_string() == raw.application_url


def test_database_round_trips_application_url(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job = Job(
        company="Example",
        title="Engineer",
        url="https://www.linkedin.com/jobs/view/12345",
        application_url=GREENHOUSE_URL,
        source="test",
    )
    job_id = database.add_job(job)

    stored = database.get_job_by_id(job_id)
    assert stored.application_url.encoded_string() == (
        "https://job-boards.greenhouse.io/example/jobs/123?gh_src=tracking#apply"
    )


def test_database_migrates_existing_schema_with_application_url_column(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs.db"
    database = JobDatabase(path)
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE jobs DROP COLUMN application_url")
    database = JobDatabase(path)

    with sqlite3.connect(path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(jobs)")
        }
    assert "application_url" in columns


def test_unresolved_linkedin_target_routes_to_review_before_scoring(
    tmp_path: Path,
) -> None:
    from scripts.smoke_test_live_discovery_pipeline import build_pipeline

    pipeline = build_pipeline(JobDatabase(tmp_path / "jobs.db"))
    pipeline.fit_scorer = MagicMock()
    pipeline.resume_router = MagicMock()
    job = composio_source().discover_jobs()[0]

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.MANUAL_REVIEW
    assert result.job.status == ApplicationStatus.NEEDS_REVIEW
    assert result.job.application_url is None
    pipeline.fit_scorer.score_job.assert_not_called()
    pipeline.resume_router.route_job.assert_not_called()
