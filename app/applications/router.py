from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.applications.validator import (
    ApplicationValidator,
)
from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.jobs.pipeline import (
    PipelineOutcome,
    PipelineResult,
)
from app.tracking.database import JobDatabase


class PreparationOutcome(str, Enum):
    """
    Outcome of preparing a pipeline-approved job for the
    future browser-application layer.
    """

    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


@dataclass(frozen=True)
class PreparationResult:
    """Structured result of application preparation."""

    job: Job
    outcome: PreparationOutcome
    reason: str
    job_id: Optional[int] = None

    @property
    def should_continue(self) -> bool:
        """
        Whether the future browser layer may inspect the
        application form.
        """

        return self.outcome == PreparationOutcome.READY


class ApplicationPreparationService:
    """
    Prepares a pipeline-approved job for the future browser
    application layer.

    SQLite remains the authoritative source of truth. Any
    preparation state transition is persisted before a
    successful preparation result is returned.

    This service does not open a browser, inspect forms,
    generate answers, fill fields, or submit applications.
    """

    def __init__(
        self,
        validator: ApplicationValidator,
        database: JobDatabase,
    ) -> None:
        self.validator = validator
        self.database = database

    def prepare(
        self,
        pipeline_result: PipelineResult,
    ) -> PreparationResult:
        """
        Prepare one pipeline result for the future application
        workflow.

        Only persisted AUTO_READY pipeline results may enter
        application readiness validation.
        """

        job = pipeline_result.job

        if pipeline_result.outcome != PipelineOutcome.AUTO_READY:
            return PreparationResult(
                job=job,
                outcome=PreparationOutcome.NOT_ELIGIBLE,
                reason=(
                    "Pipeline result is not AUTO_READY; "
                    "application preparation was not attempted."
                ),
                job_id=pipeline_result.job_id,
            )

        if pipeline_result.job_id is None:
            return PreparationResult(
                job=job,
                outcome=PreparationOutcome.NOT_ELIGIBLE,
                reason=(
                    "AUTO_READY job has no persisted job ID; "
                    "application preparation was not attempted."
                ),
                job_id=None,
            )

        original_status = job.status

        self.validator.prepare(job)

        if job.status == original_status:
            return PreparationResult(
                job=job,
                outcome=PreparationOutcome.NOT_ELIGIBLE,
                reason=(
                    "Application validator did not produce a "
                    "preparation state transition."
                ),
                job_id=pipeline_result.job_id,
            )

        try:
            self.database.update_status(
                pipeline_result.job_id,
                job.status,
            )
        except Exception:
            # SQLite is authoritative. If persistence fails,
            # restore the in-memory lifecycle state.
            job.status = original_status
            raise

        if job.status == ApplicationStatus.READY_TO_APPLY:
            return PreparationResult(
                job=job,
                outcome=PreparationOutcome.READY,
                reason=(
                    "Job passed application preparation, was "
                    "persisted, and is ready for future form "
                    "inspection."
                ),
                job_id=pipeline_result.job_id,
            )

        if job.status == ApplicationStatus.NEEDS_REVIEW:
            return PreparationResult(
                job=job,
                outcome=PreparationOutcome.NEEDS_REVIEW,
                reason=(
                    "Application readiness validation requires "
                    "human review; review state was persisted."
                ),
                job_id=pipeline_result.job_id,
            )

        return PreparationResult(
            job=job,
            outcome=PreparationOutcome.NOT_ELIGIBLE,
            reason=(
                "Job did not reach a recognized application "
                "preparation state."
            ),
            job_id=pipeline_result.job_id,
        )