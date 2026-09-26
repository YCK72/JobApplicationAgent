from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.browser.manager import (
    BrowserSession,
    BrowserSessionError,
)


def create_mock_playwright_factory() -> tuple[
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    page = MagicMock()
    context = MagicMock()
    browser = MagicMock()
    playwright = MagicMock()
    manager = MagicMock()

    context.new_page.return_value = page
    browser.new_context.return_value = context
    playwright.chromium.launch.return_value = browser
    manager.start.return_value = playwright

    factory = MagicMock(return_value=manager)

    return factory, manager, browser, context, page


def create_fake_brave(tmp_path: Path) -> Path:
    brave = tmp_path / "brave.exe"
    brave.touch()
    return brave


def test_page_before_start_raises() -> None:
    session = BrowserSession(
        brave_executable="unused.exe",
    )

    with pytest.raises(
        BrowserSessionError,
        match="has not been started",
    ):
        _ = session.page


def test_start_launches_brave_and_creates_page(
    tmp_path: Path,
) -> None:
    brave = create_fake_brave(tmp_path)

    (
        factory,
        manager,
        browser,
        context,
        page,
    ) = create_mock_playwright_factory()

    session = BrowserSession(
        brave_executable=brave,
        headless=False,
        playwright_factory=factory,
    )

    returned_page = session.start()

    assert returned_page is page
    assert session.page is page
    assert session.is_started is True

    factory.assert_called_once_with()
    manager.start.assert_called_once_with()

    playwright = manager.start.return_value

    playwright.chromium.launch.assert_called_once_with(
        executable_path=str(brave),
        headless=False,
    )

    browser.new_context.assert_called_once_with()
    context.new_page.assert_called_once_with()

    session.close()


def test_start_rejects_missing_brave_executable(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-brave.exe"

    factory = MagicMock()

    session = BrowserSession(
        brave_executable=missing,
        playwright_factory=factory,
    )

    with pytest.raises(
        BrowserSessionError,
        match="Brave executable does not exist",
    ):
        session.start()

    factory.assert_not_called()
    assert session.is_started is False


def test_start_twice_raises(
    tmp_path: Path,
) -> None:
    brave = create_fake_brave(tmp_path)

    (
        factory,
        _manager,
        _browser,
        _context,
        _page,
    ) = create_mock_playwright_factory()

    session = BrowserSession(
        brave_executable=brave,
        playwright_factory=factory,
    )

    session.start()

    with pytest.raises(
        BrowserSessionError,
        match="already started",
    ):
        session.start()

    session.close()


def test_navigate_uses_active_page(
    tmp_path: Path,
) -> None:
    brave = create_fake_brave(tmp_path)

    (
        factory,
        _manager,
        _browser,
        _context,
        page,
    ) = create_mock_playwright_factory()

    session = BrowserSession(
        brave_executable=brave,
        playwright_factory=factory,
    )

    session.start()

    returned_page = session.navigate(
        "https://example.com/jobs/123",
        wait_until="domcontentloaded",
        timeout_ms=15_000,
    )

    assert returned_page is page

    page.goto.assert_called_once_with(
        "https://example.com/jobs/123",
        wait_until="domcontentloaded",
        timeout=15_000,
    )

    session.close()


def test_navigate_before_start_raises() -> None:
    session = BrowserSession(
        brave_executable="unused.exe",
    )

    with pytest.raises(
        BrowserSessionError,
        match="has not been started",
    ):
        session.navigate("https://example.com")


def test_close_releases_resources(
    tmp_path: Path,
) -> None:
    brave = create_fake_brave(tmp_path)

    (
        factory,
        manager,
        browser,
        context,
        page,
    ) = create_mock_playwright_factory()

    session = BrowserSession(
        brave_executable=brave,
        playwright_factory=factory,
    )

    session.start()
    session.close()

    page.close.assert_called_once_with()
    context.close.assert_called_once_with()
    browser.close.assert_called_once_with()
    manager.stop.assert_called_once_with()

    assert session.is_started is False

    with pytest.raises(BrowserSessionError):
        _ = session.page


def test_close_is_idempotent(
    tmp_path: Path,
) -> None:
    brave = create_fake_brave(tmp_path)

    (
        factory,
        manager,
        browser,
        context,
        page,
    ) = create_mock_playwright_factory()

    session = BrowserSession(
        brave_executable=brave,
        playwright_factory=factory,
    )

    session.start()

    session.close()
    session.close()

    page.close.assert_called_once_with()
    context.close.assert_called_once_with()
    browser.close.assert_called_once_with()
    manager.stop.assert_called_once_with()


def test_context_manager_closes_resources(
    tmp_path: Path,
) -> None:
    brave = create_fake_brave(tmp_path)

    (
        factory,
        manager,
        browser,
        context,
        page,
    ) = create_mock_playwright_factory()

    with BrowserSession(
        brave_executable=brave,
        playwright_factory=factory,
    ) as session:
        assert session.is_started is True
        assert session.page is page

    page.close.assert_called_once_with()
    context.close.assert_called_once_with()
    browser.close.assert_called_once_with()
    manager.stop.assert_called_once_with()