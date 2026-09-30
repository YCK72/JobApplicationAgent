from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import secrets
from threading import Lock
import time

from app.applications.submission_confirmation import (
    SubmissionConfirmationOutcome,
)
from app.applications.submission_recording import SubmissionRecordingRunner
from app.jobs.models import ApplicationStatus, Job


class SubmissionReviewStatus(str, Enum):
    READY = "READY"
    SESSION_ACTIVE = "SESSION_ACTIVE"
    NOT_FOUND = "NOT_FOUND"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    FAILED = "FAILED"


class DashboardSubmissionStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    NOT_SUBMITTED = "NOT_SUBMITTED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
    PREVIEW_STALE = "PREVIEW_STALE"
    SESSION_ACTIVE = "SESSION_ACTIVE"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"


OUTCOME_CONFIRMATIONS = {
    "CONFIRMED": "RECORD_CONFIRMED_SUBMISSION",
    "UNCONFIRMED": "RECORD_UNCONFIRMED_SUBMISSION",
    "NOT_SUBMITTED": "RECORD_NOT_SUBMITTED",
}


@dataclass(frozen=True)
class PreparedSubmissionRecording:
    status: SubmissionReviewStatus
    reason: str
    job_id: int
    job: Job | None = None
    authorization_token: str | None = None
    authorization_expires_in_seconds: int | None = None

    @property
    def may_submit(self) -> bool:
        return False


@dataclass(frozen=True)
class DashboardSubmissionResult:
    status: DashboardSubmissionStatus
    reason: str
    job_id: int
    job: Job | None = None
    export_path: Path | None = None
    tracker_error: str | None = None

    @property
    def may_submit(self) -> bool:
        return False


@dataclass(frozen=True)
class _RecordingGrant:
    job_id: int
    expires_at: float
    fingerprint: tuple[object, ...]


class DashboardSubmissionRecordingService:
    """Authorize and record supplied post-review outcomes for one job."""

    _ALLOWED_STATUSES = frozenset({
        ApplicationStatus.READY_TO_APPLY,
        ApplicationStatus.FORM_STARTED,
        ApplicationStatus.NEEDS_REVIEW,
        ApplicationStatus.SUBMISSION_UNCONFIRMED,
    })

    def __init__(
        self,
        *,
        runner: SubmissionRecordingRunner,
        active_session_lookup: Callable[[int], object | None] = (
            lambda job_id: None
        ),
        authorization_ttl_seconds: int = 300,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] = (
            lambda: secrets.token_urlsafe(32)
        ),
    ) -> None:
        if authorization_ttl_seconds <= 0:
            raise ValueError("authorization_ttl_seconds must be positive")
        self.runner = runner
        self._active_session_lookup = active_session_lookup
        self.authorization_ttl_seconds = authorization_ttl_seconds
        self._clock = clock
        self._token_factory = token_factory
        self._grants: dict[str, _RecordingGrant] = {}
        self._lock = Lock()

    @property
    def may_submit(self) -> bool:
        return False

    def is_eligible(self, job: Job) -> bool:
        return job.status in self._ALLOWED_STATUSES

    def prepare(self, job_id: int) -> PreparedSubmissionRecording:
        try:
            job = self.runner.database.get_job_by_id(job_id)
        except Exception:
            return PreparedSubmissionRecording(
                status=SubmissionReviewStatus.FAILED,
                reason="Saved application state could not be loaded.",
                job_id=job_id,
            )
        if job is None:
            return PreparedSubmissionRecording(
                status=SubmissionReviewStatus.NOT_FOUND,
                reason=f"Job ID {job_id} does not exist.",
                job_id=job_id,
            )
        if not self.is_eligible(job):
            return PreparedSubmissionRecording(
                status=SubmissionReviewStatus.NOT_ELIGIBLE,
                reason=(
                    "Submission outcome cannot be recorded from application "
                    f"status {job.status.value}."
                ),
                job_id=job_id,
                job=job,
            )
        if self._active_session_lookup(job_id) is not None:
            return PreparedSubmissionRecording(
                status=SubmissionReviewStatus.SESSION_ACTIVE,
                reason=(
                    "Close the active browser review session before recording "
                    "the post-review outcome."
                ),
                job_id=job_id,
                job=job,
            )

        now = self._clock()
        token = self._token_factory()
        with self._lock:
            self._remove_expired(now)
            self._grants[token] = _RecordingGrant(
                job_id=job_id,
                expires_at=now + self.authorization_ttl_seconds,
                fingerprint=self._fingerprint(job),
            )
        return PreparedSubmissionRecording(
            status=SubmissionReviewStatus.READY,
            reason=(
                "Record only the outcome you independently observed after "
                "manual review."
            ),
            job_id=job_id,
            job=job,
            authorization_token=token,
            authorization_expires_in_seconds=(
                self.authorization_ttl_seconds
            ),
        )

    def record(
        self,
        *,
        job_id: int,
        authorization_token: object,
        outcome: object,
        confirmation: object,
        evidence: object,
    ) -> DashboardSubmissionResult:
        expected_confirmation = (
            OUTCOME_CONFIRMATIONS.get(outcome)
            if isinstance(outcome, str)
            else None
        )
        if (
            expected_confirmation is None
            or confirmation != expected_confirmation
            or not isinstance(authorization_token, str)
            or not authorization_token
        ):
            return self._result(
                DashboardSubmissionStatus.AUTHORIZATION_DENIED,
                job_id,
                "Exact post-review outcome authorization is required.",
            )

        normalized_evidence = None
        if evidence is not None:
            if not isinstance(evidence, str):
                return self._invalid_evidence(job_id)
            normalized_evidence = evidence.strip() or None
        if outcome == "CONFIRMED" and normalized_evidence is None:
            return self._invalid_evidence(job_id)
        if outcome == "NOT_SUBMITTED" and normalized_evidence is not None:
            return self._invalid_evidence(job_id)

        now = self._clock()
        with self._lock:
            grant = self._grants.pop(authorization_token, None)
        if grant is None or grant.job_id != job_id:
            return self._result(
                DashboardSubmissionStatus.AUTHORIZATION_DENIED,
                job_id,
                "Authorization is invalid or has already been used.",
            )
        if now > grant.expires_at:
            return self._result(
                DashboardSubmissionStatus.AUTHORIZATION_EXPIRED,
                job_id,
                "Authorization expired; open a fresh submission review.",
            )
        if self._active_session_lookup(job_id) is not None:
            return self._result(
                DashboardSubmissionStatus.SESSION_ACTIVE,
                job_id,
                "Close the active browser review session before recording.",
            )

        try:
            current = self.runner.database.get_job_by_id(job_id)
        except Exception:
            current = None
        if (
            current is None
            or not self.is_eligible(current)
            or self._fingerprint(current) != grant.fingerprint
        ):
            return self._result(
                DashboardSubmissionStatus.PREVIEW_STALE,
                job_id,
                "The saved job changed; review it again before recording.",
            )

        submitted = outcome != "NOT_SUBMITTED"
        result = self.runner.record(
            job_id=job_id,
            submitted=submitted,
            success_confirmed=outcome == "CONFIRMED",
            evidence=normalized_evidence,
        )
        try:
            status = DashboardSubmissionStatus(result.outcome.value)
        except ValueError:
            status = DashboardSubmissionStatus.FAILED
        return DashboardSubmissionResult(
            status=status,
            reason=result.reason,
            job_id=result.job_id,
            job=result.job,
            export_path=result.export_path,
            tracker_error=result.tracker_error,
        )

    @staticmethod
    def _fingerprint(job: Job) -> tuple[object, ...]:
        return (
            job.url.encoded_string(),
            job.status.value,
            job.resume_used,
            job.notes,
            str(job.date_applied) if job.date_applied is not None else None,
        )

    def _remove_expired(self, now: float) -> None:
        for token in [
            token
            for token, grant in self._grants.items()
            if now > grant.expires_at
        ]:
            self._grants.pop(token, None)

    @staticmethod
    def _result(
        status: DashboardSubmissionStatus,
        job_id: int,
        reason: str,
    ) -> DashboardSubmissionResult:
        return DashboardSubmissionResult(
            status=status,
            reason=reason,
            job_id=job_id,
        )

    @staticmethod
    def _invalid_evidence(job_id: int) -> DashboardSubmissionResult:
        return DashboardSubmissionRecordingService._result(
            DashboardSubmissionStatus.INVALID_EVIDENCE,
            job_id,
            (
                "Confirmed submission requires nonblank independent evidence; "
                "not-submitted outcomes cannot include submission evidence."
            ),
        )
