from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Lock

from app.applications.target_resolver import (
    ApplicationTargetResolver,
    ApplicationTargetStatus,
)
from app.jobs.models import ApplicationStatus, Job
from app.jobs.pipeline import JobPipeline, PipelineOutcome
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker


class TargetReviewStatus(str, Enum):
    UPDATED = "UPDATED"
    NOT_FOUND = "NOT_FOUND"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    INVALID_TARGET = "INVALID_TARGET"
    REPROCESS_BLOCKED = "REPROCESS_BLOCKED"


@dataclass(frozen=True)
class TargetReviewResult:
    status: TargetReviewStatus
    reason: str
    job_id: int
    application_url: str | None = None
    pipeline_outcome: PipelineOutcome | None = None
    export_path: Path | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == TargetReviewStatus.UPDATED


class ApplicationTargetReviewService:
    """Assign one reviewed target, reprocess its job, and refresh Excel."""

    def __init__(
        self,
        *,
        database: JobDatabase,
        pipeline: JobPipeline,
        tracker: ExcelTracker,
    ) -> None:
        self.database = database
        self.pipeline = pipeline
        self.tracker = tracker
        self.resolver = ApplicationTargetResolver()
        self._assignment_lock = Lock()

    @staticmethod
    def is_eligible(job: Job) -> bool:
        return (
            job.source == "linkedin_composio"
            and job.status == ApplicationStatus.NEEDS_REVIEW
            and job.application_url is None
        )

    def assign(self, *, job_id: int, application_url: object) -> TargetReviewResult:
        with self._assignment_lock:
            return self._assign(
                job_id=job_id,
                application_url=application_url,
            )

    def _assign(
        self,
        *,
        job_id: int,
        application_url: object,
    ) -> TargetReviewResult:
        if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
            raise ValueError("job_id must be a positive integer")

        job = self.database.get_job_by_id(job_id)
        if job is None:
            return TargetReviewResult(
                status=TargetReviewStatus.NOT_FOUND,
                reason=f"Job ID {job_id} does not exist.",
                job_id=job_id,
            )
        if not self.is_eligible(job):
            return TargetReviewResult(
                status=TargetReviewStatus.NOT_ELIGIBLE,
                reason=(
                    "Only unresolved NEEDS_REVIEW LinkedIn jobs may receive "
                    "a reviewed application target."
                ),
                job_id=job_id,
            )

        target = self.resolver.resolve([application_url])
        if target.status != ApplicationTargetStatus.RESOLVED:
            return TargetReviewResult(
                status=TargetReviewStatus.INVALID_TARGET,
                reason=target.reason,
                job_id=job_id,
            )

        data = job.model_dump()
        data["application_url"] = target.application_url
        job = Job.model_validate(data)
        note = (
            "Application target: reviewed application target assigned: "
            f"{target.application_url}"
        )
        job.notes = f"{job.notes.rstrip()}\n{note}" if job.notes else note

        pipeline_result = self.pipeline.reprocess(job_id, job)
        if pipeline_result.job_id != job_id:
            return TargetReviewResult(
                status=TargetReviewStatus.REPROCESS_BLOCKED,
                reason=(
                    "The reviewed target was valid, but pipeline reprocessing "
                    "did not update the selected record."
                ),
                job_id=job_id,
                application_url=target.application_url,
                pipeline_outcome=pipeline_result.outcome,
            )
        try:
            export_path = self.tracker.generate()
        except Exception:
            export_path = None
            refresh_note = (
                " The database was updated, but the Excel tracker could not "
                "be refreshed."
            )
        else:
            refresh_note = ""
        return TargetReviewResult(
            status=TargetReviewStatus.UPDATED,
            reason=pipeline_result.reason + refresh_note,
            job_id=job_id,
            application_url=target.application_url,
            pipeline_outcome=pipeline_result.outcome,
            export_path=export_path,
        )
