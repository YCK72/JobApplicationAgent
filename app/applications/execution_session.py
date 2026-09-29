from __future__ import annotations

from types import TracebackType
from typing import Callable

from app.applications.browser_form_executor import (
    BrowserFormExecutor,
)
from app.browser import BrowserSession
from app.browser.playwright_form_writer import (
    PlaywrightFieldWriter,
)


BrowserSessionFactory = Callable[[], BrowserSession]


class ApplicationExecutionSession:
    """
    Own the browser lifecycle for one controlled application execution.

    Entering this context:

    1. creates and starts one BrowserSession,
    2. navigates that session to the exact supplied target URL,
    3. binds a PlaywrightFieldWriter to that navigated page,
    4. exposes a BrowserFormExecutor for controlled field mutation.

    Leaving the context always delegates cleanup to BrowserSession.

    This boundary does not:

    - inspect application forms,
    - resolve or authorize answers,
    - authorize execution targets,
    - submit applications,
    - confirm submissions,
    - update application lifecycle state,
    - mark jobs APPLIED.

    Target authorization remains the responsibility of
    ExternalExecutionGuard and BrowserFormExecutor.
    """

    def __init__(
        self,
        *,
        target_url: str,
        browser_session_factory: BrowserSessionFactory = BrowserSession,
    ) -> None:
        if not isinstance(target_url, str):
            raise TypeError(
                "Execution target URL must be a string."
            )

        normalized_target = target_url.strip()

        if not normalized_target:
            raise ValueError(
                "Execution target URL must not be empty."
            )

        self._target_url = normalized_target
        self._browser_session_factory = browser_session_factory

        self._browser_session: BrowserSession | None = None
        self._executor: BrowserFormExecutor | None = None

    def __enter__(self) -> BrowserFormExecutor:
        session = self._browser_session_factory()

        self._browser_session = session

        try:
            session.__enter__()

            page = session.navigate(
                self._target_url
            )

            writer = PlaywrightFieldWriter(page)

            executor = BrowserFormExecutor(writer)

            self._executor = executor

            return executor

        except Exception:
            self._executor = None

            # If BrowserSession.__enter__ completed, this closes the
            # active session. If startup failed partway through,
            # BrowserSession.start() already performs its own cleanup,
            # and close() is intentionally idempotent.
            session.close()

            self._browser_session = None

            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._browser_session

        self._executor = None
        self._browser_session = None

        if session is None:
            return

        session.__exit__(
            exc_type,
            exc_value,
            traceback,
        )