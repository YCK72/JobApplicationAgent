from __future__ import annotations

from threading import get_ident
import time
from unittest.mock import MagicMock

from app.applications.browser_form_executor import (
    BrowserExecutionResult,
    BrowserExecutionStatus,
)
from app.dashboard.review_sessions import ApplicationReviewSessionManager


def completed_result() -> BrowserExecutionResult:
    return BrowserExecutionResult(
        status=BrowserExecutionStatus.COMPLETED,
        completed_actions=3,
        reason="Authorized fields populated.",
    )


def make_manager(*, ttl: float = 30.0):
    browser = MagicMock()
    page = MagicMock()
    browser.__enter__.return_value = browser
    browser.navigate.return_value = page
    browser_threads: list[int] = []
    browser_exit_threads: list[int] = []
    browser.__exit__.side_effect = (
        lambda *args: browser_exit_threads.append(get_ident())
    )
    browser.exit_threads = browser_exit_threads
    executor = MagicMock()

    def execute(*args, **kwargs):
        browser_threads.append(get_ident())
        return completed_result()

    executor.execute.side_effect = execute
    manager = ApplicationReviewSessionManager(
        browser_session_factory=lambda: browser,
        executor_factory=lambda bound_page: executor,
        review_ttl_seconds=ttl,
    )
    return manager, browser, page, executor, browser_threads


def test_successful_execution_is_retained_on_one_owner_thread() -> None:
    manager, browser, page, executor, browser_threads = make_manager()
    caller_thread = get_ident()
    assert manager.reserve(7) is True

    with manager.create_execution_session(
        "https://job-boards.greenhouse.io/example/jobs/123"
    ) as proxy:
        result = proxy.execute(MagicMock(), target_authorization=MagicMock())

    assert result.succeeded is True
    assert manager.claim(7) is True
    snapshot = manager.snapshot(7)
    assert snapshot is not None
    assert snapshot.active is True
    assert snapshot.job_id == 7
    assert snapshot.target_url.endswith("/jobs/123")
    assert browser_threads and browser_threads[0] != caller_thread
    browser.__exit__.assert_not_called()

    assert manager.close(7) is True
    browser.__enter__.assert_called_once_with()
    browser.navigate.assert_called_once_with(
        "https://job-boards.greenhouse.io/example/jobs/123"
    )
    browser.__exit__.assert_called_once_with(None, None, None)
    assert browser.exit_threads == browser_threads
    assert manager.snapshot(7) is None


def test_failed_execution_closes_instead_of_retaining() -> None:
    manager, browser, _, executor, _ = make_manager()
    executor.execute.side_effect = lambda *args, **kwargs: (
        BrowserExecutionResult(
            status=BrowserExecutionStatus.BLOCKED,
            completed_actions=0,
            reason="Blocked.",
        )
    )
    assert manager.reserve(7) is True

    with manager.create_execution_session("https://example.com/jobs/7") as proxy:
        result = proxy.execute(MagicMock(), target_authorization=MagicMock())

    assert result.succeeded is False
    assert manager.claim(7) is False
    manager.release(7)
    browser.__exit__.assert_called_once_with(None, None, None)
    assert manager.snapshot(7) is None


def test_retained_session_closes_automatically_after_timeout() -> None:
    manager, browser, _, _, _ = make_manager(ttl=0.05)
    assert manager.reserve(7) is True
    with manager.create_execution_session("https://example.com/jobs/7") as proxy:
        proxy.execute(MagicMock(), target_authorization=MagicMock())
    assert manager.claim(7) is True

    deadline = time.monotonic() + 2
    while manager.snapshot(7) is not None and time.monotonic() < deadline:
        time.sleep(0.01)

    assert manager.snapshot(7) is None
    browser.__exit__.assert_called_once_with(None, None, None)


def test_only_one_session_can_be_reserved_for_a_job() -> None:
    manager, _, _, _, _ = make_manager()

    assert manager.reserve(7) is True
    assert manager.reserve(7) is False
    manager.release(7)
    assert manager.reserve(7) is True
    manager.release(7)


def test_close_all_releases_every_active_session() -> None:
    manager, browser, _, _, _ = make_manager()
    assert manager.reserve(7) is True
    with manager.create_execution_session("https://example.com/jobs/7") as proxy:
        proxy.execute(MagicMock(), target_authorization=MagicMock())
    assert manager.claim(7) is True

    manager.close_all()

    assert manager.snapshot(7) is None
    browser.__exit__.assert_called_once_with(None, None, None)


def test_review_session_manager_has_no_submit_capability() -> None:
    manager, _, _, _, _ = make_manager()

    assert not hasattr(manager, "submit")
    assert not hasattr(manager, "confirm_submission")
    assert not hasattr(manager, "mark_applied")
