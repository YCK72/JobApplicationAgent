from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import secrets
from threading import Lock
import time

from app.applications.single_job import (
    SingleJobApplicationLauncher,
    SingleJobLaunchResult,
)
from app.dashboard.application_preview import (
    ApplicationPreviewResult,
    ApplicationPreviewService,
    ApplicationPreviewStatus,
)
from app.jobs.models import ApplicationStatus


EXTERNAL_BROWSER_CONFIRMATION = "AUTHORIZE_EXTERNAL_BROWSER"


class ApplicationLaunchStatus(str, Enum):
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
    PREVIEW_STALE = "PREVIEW_STALE"
    NOT_FOUND = "NOT_FOUND"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PreparedApplicationPreview:
    preview: ApplicationPreviewResult
    authorization_token: str | None = None
    authorization_expires_in_seconds: int | None = None


@dataclass(frozen=True)
class ApplicationLaunchResult:
    status: ApplicationLaunchStatus
    reason: str
    job_id: int
    completed_actions: int = 0
    application_status: ApplicationStatus | None = None
    export_path: Path | None = None

    @property
    def may_submit(self) -> bool:
        return False


@dataclass(frozen=True)
class _AuthorizationGrant:
    job_id: int
    expires_at: float
    fingerprint: tuple[object, ...]


class DashboardApplicationLaunchService:
    """Authorize one exact, fresh dashboard preview for one launch."""

    def __init__(
        self,
        *,
        preview_service: ApplicationPreviewService,
        launcher: SingleJobApplicationLauncher,
        authorization_ttl_seconds: int = 120,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] = (
            lambda: secrets.token_urlsafe(32)
        ),
    ) -> None:
        if authorization_ttl_seconds <= 0:
            raise ValueError("authorization_ttl_seconds must be positive")
        self.preview_service = preview_service
        self.launcher = launcher
        self.authorization_ttl_seconds = authorization_ttl_seconds
        self._clock = clock
        self._token_factory = token_factory
        self._grants: dict[str, _AuthorizationGrant] = {}
        self._lock = Lock()

    def prepare(self, job_id: int) -> PreparedApplicationPreview:
        preview = self.preview_service.preview(job_id)
        if preview.status != ApplicationPreviewStatus.READY:
            return PreparedApplicationPreview(preview=preview)

        token = self._token_factory()
        now = self._clock()
        grant = _AuthorizationGrant(
            job_id=job_id,
            expires_at=now + self.authorization_ttl_seconds,
            fingerprint=self._fingerprint(preview),
        )
        with self._lock:
            self._remove_expired(now)
            self._grants[token] = grant
        return PreparedApplicationPreview(
            preview=preview,
            authorization_token=token,
            authorization_expires_in_seconds=(
                self.authorization_ttl_seconds
            ),
        )

    def launch(
        self,
        *,
        job_id: int,
        authorization_token: object,
        confirmation: object,
    ) -> ApplicationLaunchResult:
        if (
            confirmation != EXTERNAL_BROWSER_CONFIRMATION
            or not isinstance(authorization_token, str)
            or not authorization_token
        ):
            return self._denied(
                job_id,
                "Exact external-browser authorization is required.",
            )

        now = self._clock()
        with self._lock:
            grant = self._grants.pop(authorization_token, None)
        if grant is None or grant.job_id != job_id:
            return self._denied(
                job_id,
                "Authorization is invalid or has already been used.",
            )
        if now > grant.expires_at:
            return ApplicationLaunchResult(
                status=ApplicationLaunchStatus.AUTHORIZATION_EXPIRED,
                reason="Authorization expired; open a fresh preview.",
                job_id=job_id,
            )

        current_preview = self.preview_service.preview(job_id)
        if (
            current_preview.status != ApplicationPreviewStatus.READY
            or self._fingerprint(current_preview) != grant.fingerprint
        ):
            return ApplicationLaunchResult(
                status=ApplicationLaunchStatus.PREVIEW_STALE,
                reason=(
                    "The persisted job changed after preview; review it "
                    "again before authorizing external execution."
                ),
                job_id=job_id,
            )

        launch_result = self.launcher.run(
            job_id=job_id,
            allow_external=True,
        )
        return self._from_launch_result(launch_result)

    @staticmethod
    def _fingerprint(
        preview: ApplicationPreviewResult,
    ) -> tuple[object, ...]:
        job = preview.job
        return (
            preview.status.value,
            preview.job_id,
            preview.source_url,
            preview.application_url,
            preview.provider.value,
            preview.resume,
            job.company if job else None,
            job.title if job else None,
            job.status.value if job else None,
            job.company_rule.value if job else None,
            job.application_method.value if job else None,
        )

    def _remove_expired(self, now: float) -> None:
        expired = [
            token
            for token, grant in self._grants.items()
            if now > grant.expires_at
        ]
        for token in expired:
            self._grants.pop(token, None)

    @staticmethod
    def _from_launch_result(
        result: SingleJobLaunchResult,
    ) -> ApplicationLaunchResult:
        try:
            status = ApplicationLaunchStatus(result.status.value)
        except ValueError:
            status = ApplicationLaunchStatus.FAILED
        return ApplicationLaunchResult(
            status=status,
            reason=result.reason,
            job_id=result.job_id,
            completed_actions=result.completed_actions,
            application_status=(
                result.job.status if result.job is not None else None
            ),
            export_path=result.export_path,
        )

    @staticmethod
    def _denied(job_id: int, reason: str) -> ApplicationLaunchResult:
        return ApplicationLaunchResult(
            status=ApplicationLaunchStatus.AUTHORIZATION_DENIED,
            reason=reason,
            job_id=job_id,
        )
