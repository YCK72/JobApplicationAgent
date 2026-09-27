from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import unquote, urlparse


class ExecutionTargetStatus(str, Enum):
    """
    Authorization status for the browser mutation target.
    """

    AUTHORIZED = "AUTHORIZED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ExecutionTargetAuthorization:
    """
    Result of validating whether browser mutation may target a URL.

    This authorization does not permit submission or bypass any
    field-level execution restrictions.
    """

    status: ExecutionTargetStatus
    reason: str

    @property
    def may_mutate(self) -> bool:
        return self.status == ExecutionTargetStatus.AUTHORIZED

    @property
    def may_submit(self) -> bool:
        return False


class ExternalExecutionGuard:
    """
    Fail-closed authorization boundary for browser mutation targets.

    Local mutation is allowed only for one explicitly configured fixture.
    External mutation requires explicit authorization.

    This guard does not fill fields, navigate, upload files, click,
    bypass verification, or submit applications.
    """

    def __init__(
        self,
        allowed_local_fixture: Path,
    ) -> None:
        self._allowed_local_fixture = (
            allowed_local_fixture.resolve()
        )

    def authorize(
        self,
        target_url: str,
        *,
        allow_external: bool = False,
    ) -> ExecutionTargetAuthorization:
        if not isinstance(target_url, str):
            return self._blocked(
                "Execution target URL must be a string."
            )

        target_url = target_url.strip()

        if not target_url:
            return self._blocked(
                "Execution target URL must not be empty."
            )

        try:
            parsed = urlparse(target_url)
        except ValueError:
            return self._blocked(
                "Execution target URL is invalid."
            )

        scheme = parsed.scheme.lower()

        if scheme == "file":
            return self._authorize_local_file(parsed)

        if scheme not in {"http", "https"}:
            return self._blocked(
                "Execution target uses an unsupported URL scheme."
            )

        if not parsed.hostname:
            return self._blocked(
                "External execution target has no hostname."
            )

        if not allow_external:
            return self._blocked(
                "External browser mutation requires explicit authorization."
            )

        return ExecutionTargetAuthorization(
            status=ExecutionTargetStatus.AUTHORIZED,
            reason=(
                "External browser mutation was explicitly authorized. "
                "All downstream execution restrictions still apply."
            ),
        )

    def _authorize_local_file(
        self,
        parsed,
    ) -> ExecutionTargetAuthorization:
        if parsed.netloc not in {"", "localhost"}:
            return self._blocked(
                "Local file execution target contains an unexpected host."
            )

        try:
            target_path = self._file_url_to_path(parsed)
        except (OSError, ValueError):
            return self._blocked(
                "Local file execution target could not be resolved."
            )

        if target_path != self._allowed_local_fixture:
            return self._blocked(
                "Local browser mutation is restricted to the "
                "configured controlled fixture."
            )

        return ExecutionTargetAuthorization(
            status=ExecutionTargetStatus.AUTHORIZED,
            reason=(
                "Controlled local fixture is authorized for "
                "browser mutation."
            ),
        )

    @staticmethod
    def _file_url_to_path(parsed) -> Path:
        path = unquote(parsed.path)

        if (
            len(path) >= 3
            and path[0] == "/"
            and path[2] == ":"
        ):
            path = path[1:]

        return Path(path).resolve()

    @staticmethod
    def _blocked(
        reason: str,
    ) -> ExecutionTargetAuthorization:
        return ExecutionTargetAuthorization(
            status=ExecutionTargetStatus.BLOCKED,
            reason=reason,
        )