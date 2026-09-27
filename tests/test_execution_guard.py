from pathlib import Path

import pytest

from app.applications.execution_guard import (
    ExecutionTargetStatus,
    ExternalExecutionGuard,
)


@pytest.fixture
def fixture_path(tmp_path: Path) -> Path:
    path = tmp_path / "safe_application_form.html"
    path.write_text(
        "<html><body>safe fixture</body></html>",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def guard(
    fixture_path: Path,
) -> ExternalExecutionGuard:
    return ExternalExecutionGuard(
        allowed_local_fixture=fixture_path,
    )


def test_configured_local_fixture_is_authorized(
    guard: ExternalExecutionGuard,
    fixture_path: Path,
):
    expected_url = fixture_path.resolve().as_uri()

    result = guard.authorize(expected_url)

    assert result.status == ExecutionTargetStatus.AUTHORIZED
    assert result.may_mutate is True
    assert result.may_submit is False
    assert result.target_url == expected_url


def test_different_local_file_is_blocked(
    guard: ExternalExecutionGuard,
    tmp_path: Path,
):
    other_file = tmp_path / "other.html"
    other_file.write_text(
        "<html></html>",
        encoding="utf-8",
    )

    result = guard.authorize(
        other_file.resolve().as_uri()
    )

    assert result.status == ExecutionTargetStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False
    assert result.target_url is None


@pytest.mark.parametrize(
    "url",
    [
        "https://job-boards.greenhouse.io/example/jobs/123",
        "https://jobs.lever.co/example/123",
        "https://jobs.ashbyhq.com/example/123",
        "https://example.com/application",
    ],
)
def test_external_target_is_blocked_by_default(
    guard: ExternalExecutionGuard,
    url: str,
):
    result = guard.authorize(url)

    assert result.status == ExecutionTargetStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False
    assert result.target_url is None


def test_external_target_requires_explicit_authorization(
    guard: ExternalExecutionGuard,
):
    url = "https://job-boards.greenhouse.io/example/jobs/123"

    result = guard.authorize(
        url,
        allow_external=True,
    )

    assert result.status == ExecutionTargetStatus.AUTHORIZED
    assert result.may_mutate is True
    assert result.may_submit is False
    assert result.target_url == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not-a-url",
        "/relative/path",
        "javascript:alert(1)",
        "data:text/html,test",
    ],
)
def test_invalid_or_unsupported_targets_fail_closed(
    guard: ExternalExecutionGuard,
    url: str,
):
    result = guard.authorize(url)

    assert result.status == ExecutionTargetStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False
    assert result.target_url is None


def test_non_string_target_fails_closed(
    guard: ExternalExecutionGuard,
):
    result = guard.authorize(None)  # type: ignore[arg-type]

    assert result.status == ExecutionTargetStatus.BLOCKED
    assert result.may_mutate is False
    assert result.target_url is None


def test_authorization_never_allows_submission(
    guard: ExternalExecutionGuard,
):
    result = guard.authorize(
        "https://job-boards.greenhouse.io/example/jobs/123",
        allow_external=True,
    )

    assert result.may_submit is False


def test_external_url_normalization_is_bound_to_authorization(
    guard: ExternalExecutionGuard,
):
    result = guard.authorize(
        " HTTPS://EXAMPLE.COM:443/application ",
        allow_external=True,
    )

    assert result.status == ExecutionTargetStatus.AUTHORIZED
    assert result.target_url == "https://example.com/application"


def test_default_https_port_normalizes_to_same_target():
    first = ExternalExecutionGuard.normalize_target_url(
        "https://example.com:443/application"
    )
    second = ExternalExecutionGuard.normalize_target_url(
        "https://EXAMPLE.com/application"
    )

    assert first == second
    assert first == "https://example.com/application"


def test_default_http_port_normalizes_to_same_target():
    first = ExternalExecutionGuard.normalize_target_url(
        "http://example.com:80/application"
    )
    second = ExternalExecutionGuard.normalize_target_url(
        "http://EXAMPLE.com/application"
    )

    assert first == second
    assert first == "http://example.com/application"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            "https://example.com/jobs/123",
            "https://example.com/jobs/456",
        ),
        (
            "https://example.com/jobs/123?source=a",
            "https://example.com/jobs/123?source=b",
        ),
        (
            "https://example.com/jobs/123#one",
            "https://example.com/jobs/123#two",
        ),
        (
            "http://example.com/jobs/123",
            "https://example.com/jobs/123",
        ),
    ],
)
def test_meaningfully_different_targets_remain_distinct(
    first: str,
    second: str,
):
    assert (
        ExternalExecutionGuard.normalize_target_url(first)
        != ExternalExecutionGuard.normalize_target_url(second)
    )


def test_url_credentials_are_rejected():
    with pytest.raises(ValueError):
        ExternalExecutionGuard.normalize_target_url(
            "https://user:password@example.com/application"
        )


def test_invalid_port_is_rejected():
    with pytest.raises(ValueError):
        ExternalExecutionGuard.normalize_target_url(
            "https://example.com:not-a-port/application"
        )