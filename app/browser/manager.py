from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Callable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

from app.browser.brave import find_brave_executable


class BrowserSessionError(RuntimeError):
    """Raised when the browser session is used in an invalid state."""


class BrowserSession:
    """
    Manage a read-only Playwright session backed by Brave.

    This abstraction intentionally exposes only browser lifecycle,
    navigation, and page access needed for inspection.

    It does not provide form-filling, file-upload, clicking,
    or submission helpers.
    """

    def __init__(
        self,
        *,
        brave_executable: Path | str | None = None,
        headless: bool = False,
        playwright_factory: Callable[[], object] = sync_playwright,
    ) -> None:
        self._brave_executable = (
            Path(brave_executable)
            if brave_executable is not None
            else None
        )
        self._headless = headless
        self._playwright_factory = playwright_factory

        self._playwright_manager: object | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def is_started(self) -> bool:
        return self._browser is not None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise BrowserSessionError(
                "BrowserSession has not been started."
            )

        return self._page

    def start(self) -> Page:
        """
        Start Playwright, launch Brave, create an isolated context,
        and return a blank page.
        """
        if self.is_started:
            raise BrowserSessionError(
                "BrowserSession is already started."
            )

        executable = (
            self._brave_executable
            if self._brave_executable is not None
            else find_brave_executable()
        )

        if not executable.is_file():
            raise BrowserSessionError(
                f"Brave executable does not exist: {executable}"
            )

        try:
            self._playwright_manager = self._playwright_factory()
            self._playwright = self._playwright_manager.start()

            self._browser = self._playwright.chromium.launch(
                executable_path=str(executable),
                headless=self._headless,
            )

            self._context = self._browser.new_context()
            self._page = self._context.new_page()

            return self._page

        except Exception:
            self.close()
            raise

    def navigate(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout_ms: float = 30_000,
    ) -> Page:
        """
        Navigate the active page to a URL.

        Navigation is intentionally the only page-changing operation
        exposed by this abstraction during the read-only milestone.
        """
        page = self.page

        page.goto(
            url,
            wait_until=wait_until,
            timeout=timeout_ms,
        )

        return page

    def close(self) -> None:
        """
        Close all browser resources owned by this session.

        The method is idempotent so cleanup can safely run after
        partial startup failures.
        """
        page = self._page
        context = self._context
        browser = self._browser
        playwright_manager = self._playwright_manager

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._playwright_manager = None

        if page is not None:
            try:
                page.close()
            except Exception:
                pass

        if context is not None:
            try:
                context.close()
            except Exception:
                pass

        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

        if playwright_manager is not None:
            try:
                playwright_manager.stop()
            except Exception:
                pass

    def __enter__(self) -> BrowserSession:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()