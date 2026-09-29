from unittest.mock import MagicMock

import pytest

from app.applications.execution_session import (
    ApplicationExecutionSession,
)
from app.applications.browser_form_executor import (
    BrowserFormExecutor,
)
from app.browser.playwright_form_writer import (
    PlaywrightFieldWriter,
)


def make_browser_session():
    session = MagicMock()
    page = MagicMock()

    session.__enter__.return_value = session
    session.navigate.return_value = page

    return session, page


def test_execution_session_opens_browser_and_navigates_exact_target():
    browser_session, page = make_browser_session()
    browser_session_factory = MagicMock(
        return_value=browser_session
    )

    execution_session = ApplicationExecutionSession(
        target_url="https://example.com/jobs/123",
        browser_session_factory=browser_session_factory,
    )

    with execution_session as executor:
        assert isinstance(
            executor,
            BrowserFormExecutor,
        )

    browser_session_factory.assert_called_once_with()
    browser_session.__enter__.assert_called_once_with()
    browser_session.navigate.assert_called_once_with(
        "https://example.com/jobs/123"
    )
    browser_session.__exit__.assert_called_once_with(
        None,
        None,
        None,
    )


def test_execution_session_binds_writer_to_navigated_page(
    monkeypatch,
):
    browser_session, page = make_browser_session()

    captured_pages = []

    class CapturingWriter:
        def __init__(self, bound_page):
            captured_pages.append(bound_page)

    monkeypatch.setattr(
        "app.applications.execution_session.PlaywrightFieldWriter",
        CapturingWriter,
    )

    execution_session = ApplicationExecutionSession(
        target_url="https://example.com/jobs/123",
        browser_session_factory=MagicMock(
            return_value=browser_session
        ),
    )

    with execution_session as executor:
        assert isinstance(
            executor,
            BrowserFormExecutor,
        )

    assert captured_pages == [page]


def test_execution_session_closes_browser_when_body_raises():
    browser_session, _page = make_browser_session()

    execution_session = ApplicationExecutionSession(
        target_url="https://example.com/jobs/123",
        browser_session_factory=MagicMock(
            return_value=browser_session
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="simulated execution failure",
    ):
        with execution_session:
            raise RuntimeError(
                "simulated execution failure"
            )

    browser_session.__exit__.assert_called_once()

    exit_args = browser_session.__exit__.call_args.args

    assert exit_args[0] is RuntimeError
    assert isinstance(exit_args[1], RuntimeError)


def test_execution_session_propagates_browser_startup_failure():
    browser_session = MagicMock()

    browser_session.__enter__.side_effect = RuntimeError(
        "simulated browser startup failure"
    )

    execution_session = ApplicationExecutionSession(
        target_url="https://example.com/jobs/123",
        browser_session_factory=MagicMock(
            return_value=browser_session
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="simulated browser startup failure",
    ):
        with execution_session:
            pass


def test_execution_session_propagates_navigation_failure_and_closes():
    browser_session, _page = make_browser_session()

    browser_session.navigate.side_effect = RuntimeError(
        "simulated navigation failure"
    )

    execution_session = ApplicationExecutionSession(
        target_url="https://example.com/jobs/123",
        browser_session_factory=MagicMock(
            return_value=browser_session
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="simulated navigation failure",
    ):
        with execution_session:
            pass

    browser_session.close.assert_called_once_with()
    browser_session.__exit__.assert_not_called()


def test_execution_session_exposes_no_submission_capability():
    execution_session = ApplicationExecutionSession(
        target_url="https://example.com/jobs/123",
        browser_session_factory=MagicMock(),
    )

    assert not hasattr(
        execution_session,
        "submit",
    )
    assert not hasattr(
        execution_session,
        "confirm_submission",
    )
    assert not hasattr(
        execution_session,
        "mark_applied",
    )