from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from queue import Empty, Queue
from threading import Event, Lock, Thread, get_ident
import time

from app.applications.browser_form_executor import BrowserFormExecutor
from app.browser import BrowserSession
from app.browser.playwright_form_writer import PlaywrightFieldWriter
from app.applications.submission_executor import BrowserSubmissionExecutor


@dataclass(frozen=True)
class ReviewSessionSnapshot:
    job_id: int
    target_url: str
    active: bool
    expires_in_seconds: int


class _ExecutorProxy:
    def __init__(self, session: RetainedApplicationExecutionSession) -> None:
        self._session = session

    def execute(self, plan, *, target_authorization):
        return self._session.execute(
            plan,
            target_authorization=target_authorization,
        )

    def submit_application(self):
        return self._session.submit_application()


class RetainedApplicationExecutionSession:
    """Own a headed execution browser on a dedicated worker thread."""

    def __init__(
        self,
        *,
        target_url: str,
        browser_session_factory: Callable[[], BrowserSession],
        executor_factory: Callable[[object], BrowserFormExecutor],
        review_ttl_seconds: float,
        on_closed: Callable[[RetainedApplicationExecutionSession], None],
    ) -> None:
        self.target_url = target_url
        self.review_ttl_seconds = review_ttl_seconds
        self._browser_session_factory = browser_session_factory
        self._executor_factory = executor_factory
        self._on_closed = on_closed
        self._commands: Queue[tuple[str, object, Queue | None]] = Queue()
        self._ready = Event()
        self._active = Event()
        self._closed = Event()
        self._startup_error: Exception | None = None
        self._last_execution_succeeded = False
        self._submission_attempted = False
        self._expires_at: float | None = None
        self._thread = Thread(
            target=self._run,
            name="application-review-session",
            daemon=True,
        )

    @property
    def active(self) -> bool:
        return self._active.is_set() and not self._closed.is_set()

    def __enter__(self) -> _ExecutorProxy:
        self._thread.start()
        if not self._ready.wait(timeout=30):
            self.close()
            raise TimeoutError("Review browser session did not start in time.")
        if self._startup_error is not None:
            raise self._startup_error
        return _ExecutorProxy(self)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if (
            exc_type is not None
            or not self._last_execution_succeeded
            or self._submission_attempted
        ):
            self.close()
            return
        response: Queue = Queue(maxsize=1)
        self._commands.put(("retain", None, response))
        outcome = response.get(timeout=5)
        if isinstance(outcome, Exception):
            raise outcome

    def execute(self, plan, *, target_authorization):
        response: Queue = Queue(maxsize=1)
        self._commands.put((
            "execute",
            (plan, target_authorization),
            response,
        ))
        outcome = response.get(timeout=120)
        if isinstance(outcome, Exception):
            raise outcome
        self._last_execution_succeeded = bool(outcome.succeeded)
        return outcome

    def submit_application(self):
        response: Queue = Queue(maxsize=1)
        self._commands.put(("submit", None, response))
        outcome = response.get(timeout=45)
        if isinstance(outcome, Exception):
            raise outcome
        self._submission_attempted = True
        return outcome

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._commands.put(("close", None, None))
        if self._thread.is_alive() and get_ident() != self._thread.ident:
            self._thread.join(timeout=10)

    def expires_in_seconds(self) -> int:
        if not self.active or self._expires_at is None:
            return 0
        return max(0, math.ceil(self._expires_at - time.monotonic()))

    def _run(self) -> None:
        browser_session = None
        entered = False
        try:
            browser_session = self._browser_session_factory()
            opened_session = browser_session.__enter__()
            entered = True
            page = opened_session.navigate(self.target_url)
            executor = self._executor_factory(page)
            submission_executor = BrowserSubmissionExecutor(page)
            self._ready.set()
            self._command_loop(executor, submission_executor)
        except Exception as exc:
            if not self._ready.is_set():
                self._startup_error = exc
                self._ready.set()
        finally:
            self._active.clear()
            if entered and browser_session is not None:
                browser_session.__exit__(None, None, None)
            elif browser_session is not None:
                browser_session.close()
            self._closed.set()
            self._on_closed(self)

    def _command_loop(
        self,
        executor: BrowserFormExecutor,
        submission_executor: BrowserSubmissionExecutor,
    ) -> None:
        while True:
            timeout = None
            if self._expires_at is not None:
                timeout = max(0, self._expires_at - time.monotonic())
                if timeout == 0:
                    return
            try:
                command, payload, response = self._commands.get(
                    timeout=timeout
                )
            except Empty:
                return

            if command == "close":
                return
            if command == "retain":
                self._expires_at = (
                    time.monotonic() + self.review_ttl_seconds
                )
                self._active.set()
                if response is not None:
                    response.put(True)
                continue
            if command == "execute" and response is not None:
                plan, target_authorization = payload
                try:
                    result = executor.execute(
                        plan,
                        target_authorization=target_authorization,
                    )
                except Exception as exc:
                    response.put(exc)
                else:
                    response.put(result)
                continue
            if command == "submit" and response is not None:
                try:
                    result = submission_executor.submit(
                        target_url=self.target_url,
                    )
                except Exception as exc:
                    response.put(exc)
                else:
                    response.put(result)


class ApplicationReviewSessionManager:
    """Reserve, retain, inspect, and close one browser session per job."""

    def __init__(
        self,
        *,
        browser_session_factory: Callable[[], BrowserSession] = BrowserSession,
        executor_factory: Callable[[object], BrowserFormExecutor] = (
            lambda page: BrowserFormExecutor(PlaywrightFieldWriter(page))
        ),
        review_ttl_seconds: float = 900,
    ) -> None:
        if review_ttl_seconds <= 0:
            raise ValueError("review_ttl_seconds must be positive")
        self._browser_session_factory = browser_session_factory
        self._executor_factory = executor_factory
        self._review_ttl_seconds = review_ttl_seconds
        self._lock = Lock()
        self._reserved_jobs: set[int] = set()
        self._job_by_owner: dict[int, int] = {}
        self._pending: dict[int, RetainedApplicationExecutionSession] = {}
        self._active: dict[int, RetainedApplicationExecutionSession] = {}

    def reserve(self, job_id: int) -> bool:
        owner = get_ident()
        with self._lock:
            if (
                job_id in self._reserved_jobs
                or job_id in self._active
                or owner in self._job_by_owner
            ):
                return False
            self._reserved_jobs.add(job_id)
            self._job_by_owner[owner] = job_id
            return True

    def create_execution_session(
        self,
        target_url: str,
    ) -> RetainedApplicationExecutionSession:
        owner = get_ident()
        with self._lock:
            job_id = self._job_by_owner.get(owner)
            if job_id is None:
                raise RuntimeError(
                    "Review session execution requires a job reservation."
                )
            if job_id in self._pending:
                raise RuntimeError(
                    "The reserved job already has a pending review session."
                )
            session = RetainedApplicationExecutionSession(
                target_url=target_url,
                browser_session_factory=self._browser_session_factory,
                executor_factory=self._executor_factory,
                review_ttl_seconds=self._review_ttl_seconds,
                on_closed=lambda closed: self._session_closed(
                    job_id,
                    closed,
                ),
            )
            self._pending[job_id] = session
            return session

    def claim(self, job_id: int) -> bool:
        owner = get_ident()
        with self._lock:
            if self._job_by_owner.get(owner) != job_id:
                return False
            session = self._pending.pop(job_id, None)
            self._job_by_owner.pop(owner, None)
            self._reserved_jobs.discard(job_id)
            if session is None or not session.active:
                return False
            self._active[job_id] = session
            return True

    def release(self, job_id: int) -> None:
        owner = get_ident()
        with self._lock:
            session = self._pending.pop(job_id, None)
            if self._job_by_owner.get(owner) == job_id:
                self._job_by_owner.pop(owner, None)
            self._reserved_jobs.discard(job_id)
        if session is not None:
            session.close()

    def snapshot(self, job_id: int) -> ReviewSessionSnapshot | None:
        with self._lock:
            session = self._active.get(job_id)
        if session is None or not session.active:
            return None
        return ReviewSessionSnapshot(
            job_id=job_id,
            target_url=session.target_url,
            active=True,
            expires_in_seconds=session.expires_in_seconds(),
        )

    def close(self, job_id: int) -> bool:
        with self._lock:
            session = self._active.pop(job_id, None)
        if session is None:
            return False
        session.close()
        return True

    def submit_application(self, job_id: int):
        with self._lock:
            session = self._active.get(job_id)
        if session is None or not session.active:
            raise RuntimeError("No active browser session exists for this job.")
        return session.submit_application()

    def close_all(self) -> None:
        with self._lock:
            sessions = list({
                *self._active.values(),
                *self._pending.values(),
            })
            self._active.clear()
            self._pending.clear()
            self._reserved_jobs.clear()
            self._job_by_owner.clear()
        for session in sessions:
            session.close()

    def _session_closed(
        self,
        job_id: int,
        session: RetainedApplicationExecutionSession,
    ) -> None:
        with self._lock:
            if self._active.get(job_id) is session:
                self._active.pop(job_id, None)
            if self._pending.get(job_id) is session:
                self._pending.pop(job_id, None)
