from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.applications.submission_confirmation import (
    SubmissionConfirmation,
    SubmissionConfirmationOutcome,
    SubmissionConfirmationService,
)
from app.jobs.models import Job
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker


@dataclass(frozen=True)
class SubmissionRecordingResult:
    """Exact-ID post-review recording result plus tracker status."""

    job_id: int
    job: Job | None
    outcome: SubmissionConfirmationOutcome
    reason: str
    export_path: Path | None = None
    tracker_error: str | None = None

    @property
    def confirmed(self) -> bool:
        return self.outcome == SubmissionConfirmationOutcome.CONFIRMED

    @property
    def may_submit(self) -> bool:
        return False


class SubmissionRecordingRunner:
    """Record supplied post-review evidence for one persisted job.

    This boundary loads the exact job, delegates lifecycle decisions to the
    independent confirmation service, and refreshes the Excel report. It has
    no browser, form-filling, or submission capability.
    """

    def __init__(
        self,
        *,
        database: JobDatabase,
        confirmation_service: SubmissionConfirmationService,
        tracker: ExcelTracker,
    ) -> None:
        self.database = database
        self.confirmation_service = confirmation_service
        self.tracker = tracker

    def record(
        self,
        *,
        job_id: int,
        submitted: bool,
        success_confirmed: bool,
        evidence: str | None,
    ) -> SubmissionRecordingResult:
        if (
            isinstance(job_id, bool)
            or not isinstance(job_id, int)
            or job_id <= 0
        ):
            raise ValueError("job_id must be a positive integer")

        try:
            job = self.database.get_job_by_id(job_id)
        except Exception as exc:
            return SubmissionRecordingResult(
                job_id=job_id,
                job=None,
                outcome=SubmissionConfirmationOutcome.FAILED,
                reason=f"Persisted job could not be loaded: {exc}",
            )

        if job is None:
            return SubmissionRecordingResult(
                job_id=job_id,
                job=None,
                outcome=SubmissionConfirmationOutcome.FAILED,
                reason=f"Job ID {job_id} does not exist.",
            )

        confirmation_result = self.confirmation_service.record(
            job=job,
            job_id=job_id,
            confirmation=SubmissionConfirmation(
                submitted=submitted,
                success_confirmed=success_confirmed,
                evidence=evidence,
            ),
        )

        try:
            export_path = self.tracker.generate()
        except Exception as exc:
            return SubmissionRecordingResult(
                job_id=job_id,
                job=confirmation_result.job,
                outcome=confirmation_result.outcome,
                reason=confirmation_result.reason,
                tracker_error=str(exc),
            )

        return SubmissionRecordingResult(
            job_id=job_id,
            job=confirmation_result.job,
            outcome=confirmation_result.outcome,
            reason=confirmation_result.reason,
            export_path=export_path,
        )
