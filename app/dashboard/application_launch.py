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
from app.applications.submission_confirmation import (
    SubmissionConfirmation,
    SubmissionConfirmationOutcome,
    SubmissionConfirmationService,
)
from app.dashboard.review_sessions import (
    ApplicationReviewSessionManager,
    ReviewSessionSnapshot,
)


EXTERNAL_BROWSER_CONFIRMATION = "AUTHORIZE_EXTERNAL_BROWSER"
AUTOMATIC_SUBMISSION_CONFIRMATION = (
    "AUTHORIZE_EXTERNAL_BROWSER_AND_AUTOMATIC_SUBMISSION"
)


class ApplicationLaunchStatus(str, Enum):
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
    PREVIEW_STALE = "PREVIEW_STALE"
    SESSION_ACTIVE = "SESSION_ACTIVE"
    SESSION_UNAVAILABLE = "SESSION_UNAVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPLIED = "APPLIED"
    SUBMISSION_UNCONFIRMED = "SUBMISSION_UNCONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PreparedApplicationPreview:
    preview: ApplicationPreviewResult
    authorization_token: str | None = None
    authorization_expires_in_seconds: int | None = None
    review_session: ReviewSessionSnapshot | None = None


@dataclass(frozen=True)
class ApplicationLaunchResult:
    status: ApplicationLaunchStatus
    reason: str
    job_id: int
    completed_actions: int = 0
    application_status: ApplicationStatus | None = None
    export_path: Path | None = None
    review_session: ReviewSessionSnapshot | None = None

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
        review_session_manager: ApplicationReviewSessionManager | None = None,
        submission_confirmation_service: (
            SubmissionConfirmationService | None
        ) = None,
    ) -> None:
        if authorization_ttl_seconds <= 0:
            raise ValueError("authorization_ttl_seconds must be positive")
        self.preview_service = preview_service
        self.launcher = launcher
        self.authorization_ttl_seconds = authorization_ttl_seconds
        self._clock = clock
        self._token_factory = token_factory
        self.review_session_manager = review_session_manager
        self.submission_confirmation_service = (
            submission_confirmation_service
            if submission_confirmation_service is not None
            else SubmissionConfirmationService(launcher.database)
        )
        self._grants: dict[str, _AuthorizationGrant] = {}
        self._lock = Lock()

    def prepare(self, job_id: int) -> PreparedApplicationPreview:
        preview = self.preview_service.preview(job_id)
        review_session = self.current_review_session(job_id)
        if preview.status != ApplicationPreviewStatus.READY:
            return PreparedApplicationPreview(
                preview=preview,
                review_session=review_session,
            )
        if review_session is not None:
            return PreparedApplicationPreview(
                preview=preview,
                review_session=review_session,
            )

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
            review_session=review_session,
        )

    def launch(
        self,
        *,
        job_id: int,
        authorization_token: object,
        confirmation: object,
    ) -> ApplicationLaunchResult:
        automatic_submission = (
            confirmation == AUTOMATIC_SUBMISSION_CONFIRMATION
        )
        if (
            confirmation not in {
                EXTERNAL_BROWSER_CONFIRMATION,
                AUTOMATIC_SUBMISSION_CONFIRMATION,
            }
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

        sessions = self.review_session_manager
        if sessions is not None and not sessions.reserve(job_id):
            return ApplicationLaunchResult(
                status=ApplicationLaunchStatus.SESSION_ACTIVE,
                reason=(
                    "This job already has an active or pending browser "
                    "review session."
                ),
                job_id=job_id,
                review_session=sessions.snapshot(job_id),
            )

        try:
            launch_result = self.launcher.run(
                job_id=job_id,
                allow_external=True,
            )
        except Exception:
            if sessions is not None:
                sessions.release(job_id)
            raise

        if sessions is None:
            return self._from_launch_result(launch_result)
        if launch_result.succeeded:
            if not sessions.claim(job_id):
                sessions.release(job_id)
                return ApplicationLaunchResult(
                    status=ApplicationLaunchStatus.SESSION_UNAVAILABLE,
                    reason=(
                        "Authorized fields were populated, but the browser "
                        "review session could not be retained."
                    ),
                    job_id=job_id,
                    completed_actions=launch_result.completed_actions,
                    application_status=(
                        launch_result.job.status
                        if launch_result.job is not None
                        else None
                    ),
                    export_path=launch_result.export_path,
                )
            if automatic_submission:
                return self._submit_and_record(
                    job_id=job_id,
                    launch_result=launch_result,
                )
            return self._from_launch_result(
                launch_result,
                review_session=sessions.snapshot(job_id),
            )

        sessions.release(job_id)
        return self._from_launch_result(launch_result)

    def _submit_and_record(
        self,
        *,
        job_id: int,
        launch_result: SingleJobLaunchResult,
    ) -> ApplicationLaunchResult:
        sessions = self.review_session_manager
        if sessions is None or launch_result.job is None:
            return ApplicationLaunchResult(
                status=ApplicationLaunchStatus.BLOCKED,
                reason="Automatic submission requires an active browser session.",
                job_id=job_id,
                completed_actions=launch_result.completed_actions,
            )
        try:
            browser_result = sessions.submit_application(job_id)
            confirmation_result = self.submission_confirmation_service.record(
                job=launch_result.job,
                job_id=job_id,
                confirmation=SubmissionConfirmation(
                    submitted=browser_result.submitted,
                    success_confirmed=browser_result.success_confirmed,
                    evidence=browser_result.evidence,
                ),
            )
        except Exception as exc:
            return ApplicationLaunchResult(
                status=ApplicationLaunchStatus.FAILED,
                reason=f"Automatic submission failed unexpectedly: {exc}",
                job_id=job_id,
                completed_actions=launch_result.completed_actions,
            )
        finally:
            sessions.close(job_id)

        try:
            export_path = self.launcher.tracker.generate()
        except Exception:
            export_path = launch_result.export_path

        if confirmation_result.outcome == SubmissionConfirmationOutcome.CONFIRMED:
            status = ApplicationLaunchStatus.APPLIED
        elif confirmation_result.outcome == SubmissionConfirmationOutcome.UNCONFIRMED:
            status = ApplicationLaunchStatus.SUBMISSION_UNCONFIRMED
        elif confirmation_result.outcome == SubmissionConfirmationOutcome.NOT_SUBMITTED:
            status = ApplicationLaunchStatus.BLOCKED
        elif confirmation_result.outcome == SubmissionConfirmationOutcome.BLOCKED:
            status = ApplicationLaunchStatus.BLOCKED
        else:
            status = ApplicationLaunchStatus.FAILED
        return ApplicationLaunchResult(
            status=status,
            reason=confirmation_result.reason,
            job_id=job_id,
            completed_actions=launch_result.completed_actions,
            application_status=confirmation_result.job.status,
            export_path=export_path,
        )

    def current_review_session(
        self,
        job_id: int,
    ) -> ReviewSessionSnapshot | None:
        if self.review_session_manager is None:
            return None
        return self.review_session_manager.snapshot(job_id)

    def close_review_session(self, job_id: int) -> bool:
        if self.review_session_manager is None:
            return False
        return self.review_session_manager.close(job_id)

    def close_all_review_sessions(self) -> None:
        if self.review_session_manager is not None:
            self.review_session_manager.close_all()

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
        *,
        review_session: ReviewSessionSnapshot | None = None,
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
            review_session=review_session,
        )

    @staticmethod
    def _denied(job_id: int, reason: str) -> ApplicationLaunchResult:
        return ApplicationLaunchResult(
            status=ApplicationLaunchStatus.AUTHORIZATION_DENIED,
            reason=reason,
            job_id=job_id,
        )
