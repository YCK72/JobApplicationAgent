from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.tracking.database import JobDatabase


class SubmissionConfirmationOutcome(str, Enum):
    """
    Outcome of recording a post-review submission result.

    CONFIRMED means successful submission was independently confirmed.

    UNCONFIRMED means a submission was attempted, but successful
    submission could not be independently established.

    NOT_SUBMITTED means no submission attempt occurred.

    BLOCKED means the supplied confirmation data was internally
    inconsistent or insufficient to authorize a lifecycle transition.

    FAILED means persistence failed.
    """

    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    NOT_SUBMITTED = "NOT_SUBMITTED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SubmissionConfirmation:
    """
    Evidence supplied after human review of the application.

    This object does not submit an application. It only describes
    what happened outside this service.
    """

    submitted: bool
    success_confirmed: bool
    evidence: Optional[str] = None


@dataclass(frozen=True)
class SubmissionConfirmationResult:
    """
    Result of evaluating and recording submission confirmation.

    confirmed is True only when successful submission was independently
    confirmed and the APPLIED lifecycle state was persisted.
    """

    job: Job
    outcome: SubmissionConfirmationOutcome
    reason: str

    @property
    def confirmed(self) -> bool:
        return (
            self.outcome
            == SubmissionConfirmationOutcome.CONFIRMED
        )

    @property
    def may_submit(self) -> bool:
        return False


class SubmissionConfirmationService:
    """
    Record post-review application submission results.

    This service intentionally does not:

    - click or activate a submit control,
    - manipulate a browser,
    - infer that field filling means submission,
    - infer successful submission from navigation alone,
    - bypass human review,
    - authorize submission.

    APPLIED is recorded only when the caller explicitly reports that
    submission occurred, successful submission was independently
    confirmed, and nonblank confirmation evidence is supplied.
    """
    _ALLOWED_STARTING_STATUSES = frozenset(
        {
            ApplicationStatus.READY_TO_APPLY,
            ApplicationStatus.FORM_STARTED,
            ApplicationStatus.NEEDS_REVIEW,
            ApplicationStatus.SUBMISSION_UNCONFIRMED,
        }
    )

    def __init__(
        self,
        database: JobDatabase,
    ) -> None:
        self.database = database

    def record(
        self,
        *,
        job: Job,
        job_id: int | None,
        confirmation: SubmissionConfirmation,
    ) -> SubmissionConfirmationResult:
        """
        Evaluate and persist one post-review submission result.

        Persistence is deliberately performed before mutating the
        supplied in-memory Job. If persistence fails, the in-memory
        lifecycle state remains unchanged.
        """

        if job_id is None:
            return self._blocked(
                job,
                "Submission confirmation requires a persisted job ID.",
            )
        try:
            stored_job = self.database.get_job_by_id(job_id)
        except Exception as exc:
            return self._failed(
                job,
                (
                    "Failed to verify persisted job identity: "
                    f"{exc}"
                ),
            )

        if stored_job is None:
            return self._failed(
                job,
                f"Job ID {job_id} does not exist.",
            )

        if (
            stored_job.url.encoded_string()
            != job.url.encoded_string()
        ):
            return self._blocked(
                job,
                (
                    "Submission confirmation job does not match "
                    "the persisted job ID."
                ),
            )
        if job.status not in self._ALLOWED_STARTING_STATUSES:
            return self._blocked(
                job,
                (
                    "Submission confirmation cannot be recorded from "
                    f"application status {job.status.value}."
                ),
            )

        if (
            confirmation.success_confirmed
            and not confirmation.submitted
        ):
            return self._blocked(
                job,
                (
                    "Successful submission cannot be confirmed when "
                    "no submission was reported."
                ),
            )

        evidence = self._normalize_evidence(
            confirmation.evidence
        )

        if confirmation.success_confirmed and evidence is None:
            return self._blocked(
                job,
                (
                    "Confirmed submission requires nonblank "
                    "independent confirmation evidence."
                ),
            )

        if not confirmation.submitted:
            return SubmissionConfirmationResult(
                job=job,
                outcome=(
                    SubmissionConfirmationOutcome.NOT_SUBMITTED
                ),
                reason=(
                    "No submission was reported. "
                    "Application lifecycle was not advanced."
                ),
            )

        if not confirmation.success_confirmed:
            return self._record_unconfirmed(
                job=job,
                job_id=job_id,
                evidence=evidence,
            )

        return self._record_confirmed(
            job=job,
            job_id=job_id,
            evidence=evidence,
        )

    def _record_confirmed(
        self,
        *,
        job: Job,
        job_id: int,
        evidence: str,
    ) -> SubmissionConfirmationResult:
        reason = (
            "Successful submission was independently confirmed. "
            f"Evidence: {evidence}"
        )
        notes = self._append_note(job.notes, reason)

        try:
            self.database.mark_applied(
                job_id,
                job.resume_used,
                notes=notes,
            )
        except Exception as exc:
            return self._failed(
                job,
                (
                    "Failed to persist independently confirmed "
                    f"submission: {exc}"
                ),
            )

        stored = self.database.get_job_by_id(job_id)

        if stored is None:
            return self._failed(
                job,
                (
                    "Confirmed submission was persisted, but the "
                    "updated job could not be retrieved."
                ),
            )

        job.status = stored.status
        job.date_applied = stored.date_applied
        job.resume_used = stored.resume_used
        job.notes = stored.notes

        return SubmissionConfirmationResult(
            job=job,
            outcome=SubmissionConfirmationOutcome.CONFIRMED,
            reason=reason,
        )

    def _record_unconfirmed(
        self,
        *,
        job: Job,
        job_id: int,
        evidence: str | None,
    ) -> SubmissionConfirmationResult:
        reason = (
            "Submission was reported, but successful submission "
            "could not be independently confirmed."
        )

        if evidence is not None:
            reason = f"{reason} Evidence: {evidence}"

        try:
            self.database.update_application_state(
                job_id,
                ApplicationStatus.SUBMISSION_UNCONFIRMED,
                reason,
            )
        except Exception as exc:
            return self._failed(
                job,
                (
                    "Failed to persist unconfirmed submission "
                    f"state: {exc}"
                ),
            )

        job.status = ApplicationStatus.SUBMISSION_UNCONFIRMED
        job.notes = reason
        job.date_applied = None

        return SubmissionConfirmationResult(
            job=job,
            outcome=SubmissionConfirmationOutcome.UNCONFIRMED,
            reason=reason,
        )

    @staticmethod
    def _normalize_evidence(
        evidence: str | None,
    ) -> str | None:
        if evidence is None:
            return None

        normalized = evidence.strip()

        if not normalized:
            return None

        return normalized

    @staticmethod
    def _append_note(
        existing: str | None,
        message: str,
    ) -> str:
        if existing and existing.strip():
            return f"{existing.rstrip()}\n{message}"
        return message

    @staticmethod
    def _blocked(
        job: Job,
        reason: str,
    ) -> SubmissionConfirmationResult:
        return SubmissionConfirmationResult(
            job=job,
            outcome=SubmissionConfirmationOutcome.BLOCKED,
            reason=reason,
        )

    @staticmethod
    def _failed(
        job: Job,
        reason: str,
    ) -> SubmissionConfirmationResult:
        return SubmissionConfirmationResult(
            job=job,
            outcome=SubmissionConfirmationOutcome.FAILED,
            reason=reason,
        )
