from pathlib import Path

import pytest

from app.browser.brave import (
    BraveNotFoundError,
    find_brave_executable,
    get_default_brave_paths,
)


def test_get_default_brave_paths_uses_windows_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Test\AppData\Local")

    paths = get_default_brave_paths()

    assert paths == (
        Path(
            r"C:\Program Files"
        )
        / "BraveSoftware"
        / "Brave-Browser"
        / "Application"
        / "brave.exe",
        Path(
            r"C:\Program Files (x86)"
        )
        / "BraveSoftware"
        / "Brave-Browser"
        / "Application"
        / "brave.exe",
        Path(
            r"C:\Users\Test\AppData\Local"
        )
        / "BraveSoftware"
        / "Brave-Browser"
        / "Application"
        / "brave.exe",
    )


def test_find_brave_executable_returns_first_existing_file(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing" / "brave.exe"
    existing = tmp_path / "existing" / "brave.exe"

    existing.parent.mkdir(parents=True)
    existing.touch()

    result = find_brave_executable(
        candidate_paths=[missing, existing]
    )

    assert result == existing.resolve()


def test_find_brave_executable_raises_when_not_found(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first" / "brave.exe"
    second = tmp_path / "second" / "brave.exe"

    with pytest.raises(BraveNotFoundError) as exc_info:
        find_brave_executable(
            candidate_paths=[first, second]
        )

    message = str(exc_info.value)

    assert "Brave executable was not found" in message
    assert str(first) in message
    assert str(second) in message


def test_find_brave_executable_handles_empty_candidate_list() -> None:
    with pytest.raises(BraveNotFoundError) as exc_info:
        find_brave_executable(candidate_paths=[])

    assert "No candidate paths were available" in str(
        exc_info.value
    )