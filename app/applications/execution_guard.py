from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import (
    unquote,
    urlparse,
    urlunparse,
)


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

    Authorized results are bound to one exact normalized target URL.

    This authorization does not permit submission or bypass any
    field-level execution restrictions.
    """

    status: ExecutionTargetStatus
    reason: str
    target_url: str | None = None

    @property
    def may_mutate(self) -> bool:
        return (
            self.status == ExecutionTargetStatus.AUTHORIZED
            and self.target_url is not None
        )

    @property
    def may_submit(self) -> bool:
        return False


class ExternalExecutionGuard:
    """
    Fail-closed authorization boundary for browser mutation targets.

    Local mutation is allowed only for one explicitly configured fixture.
    External mutation requires explicit authorization.

    Every successful authorization is bound to one exact normalized URL.

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
        try:
            normalized_url = self.normalize_target_url(
                target_url
            )
        except (TypeError, ValueError, OSError):
            return self._blocked(
                "Execution target URL is invalid."
            )

        parsed = urlparse(normalized_url)
        scheme = parsed.scheme.lower()

        if scheme == "file":
            return self._authorize_local_file(
                parsed=parsed,
                normalized_url=normalized_url,
            )

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
            target_url=normalized_url,
        )

    def _authorize_local_file(
        self,
        *,
        parsed,
        normalized_url: str,
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
            target_url=normalized_url,
        )

    @classmethod
    def normalize_target_url(
        cls,
        target_url: str,
    ) -> str:
        """
        Normalize a browser mutation target for exact identity comparison.

        The normalization is intentionally conservative. It does not treat
        different paths, queries, or fragments as equivalent.
        """
        if not isinstance(target_url, str):
            raise TypeError(
                "Execution target URL must be a string."
            )

        target_url = target_url.strip()

        if not target_url:
            raise ValueError(
                "Execution target URL must not be empty."
            )

        try:
            parsed = urlparse(target_url)
        except ValueError as exc:
            raise ValueError(
                "Execution target URL is invalid."
            ) from exc

        scheme = parsed.scheme.lower()

        if scheme == "file":
            if parsed.netloc not in {"", "localhost"}:
                raise ValueError(
                    "Local file target contains an unexpected host."
                )

            target_path = cls._file_url_to_path(parsed)

            return target_path.as_uri()

        if scheme not in {"http", "https"}:
            raise ValueError(
                "Execution target uses an unsupported URL scheme."
            )

        if not parsed.hostname:
            raise ValueError(
                "External execution target has no hostname."
            )

        hostname = parsed.hostname.lower()

        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(
                "External execution target contains an invalid port."
            ) from exc

        if (
            (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            port = None

        host = hostname

        if ":" in hostname and not hostname.startswith("["):
            host = f"[{hostname}]"

        if port is not None:
            host = f"{host}:{port}"

        if parsed.username is not None or parsed.password is not None:
            raise ValueError(
                "Execution target must not contain URL credentials."
            )

        path = parsed.path or "/"

        return urlunparse(
            (
                scheme,
                host,
                path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
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
            target_url=None,
        )