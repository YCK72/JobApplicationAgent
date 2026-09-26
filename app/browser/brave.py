from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


class BraveNotFoundError(RuntimeError):
    """Raised when a usable Brave executable cannot be found."""


def get_default_brave_paths() -> tuple[Path, ...]:
    """
    Return the common Brave executable locations on Windows.

    Environment variables are read at call time so the function remains
    deterministic and easy to test with patched environments.
    """
    candidate_paths: list[Path] = []

    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    local_app_data = os.environ.get("LOCALAPPDATA")

    if program_files:
        candidate_paths.append(
            Path(program_files)
            / "BraveSoftware"
            / "Brave-Browser"
            / "Application"
            / "brave.exe"
        )

    if program_files_x86:
        candidate_paths.append(
            Path(program_files_x86)
            / "BraveSoftware"
            / "Brave-Browser"
            / "Application"
            / "brave.exe"
        )

    if local_app_data:
        candidate_paths.append(
            Path(local_app_data)
            / "BraveSoftware"
            / "Brave-Browser"
            / "Application"
            / "brave.exe"
        )

    return tuple(candidate_paths)


def find_brave_executable(
    candidate_paths: Iterable[Path | str] | None = None,
) -> Path:
    """
    Return the first existing Brave executable.

    Custom candidate paths may be injected by tests or future configuration.
    """
    paths = (
        tuple(Path(path) for path in candidate_paths)
        if candidate_paths is not None
        else get_default_brave_paths()
    )

    for path in paths:
        if path.is_file():
            return path.resolve()

    searched = "\n".join(f"  - {path}" for path in paths)

    if not searched:
        searched = "  - No candidate paths were available."

    raise BraveNotFoundError(
        "Brave executable was not found.\n"
        "Searched:\n"
        f"{searched}"
    )