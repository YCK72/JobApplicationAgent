from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.applications.adapters.detector import ATSProvider
from app.applications.single_job import SingleJobApplicationLauncher
from app.applications.target_resolver import resolve_job_application_target
from app.jobs.models import Job
from app.tracking.database import JobDatabase


class ApplicationPreviewStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ApplicationPreviewResult:
    status: ApplicationPreviewStatus
    reason: str
    job_id: int
    job: Job | None = None
    source_url: str | None = None
    application_url: str | None = None
    provider: ATSProvider = ATSProvider.UNKNOWN
    resume: str | None = None

    @property
    def browser_started(self) -> bool:
        return False

    @property
    def workflow_ran(self) -> bool:
        return False

    @property
    def may_submit(self) -> bool:
        return False


class ApplicationPreviewService:
    """Build a read-only application plan from one persisted job."""

    def __init__(self, *, database: JobDatabase) -> None:
        self.database = database

    def preview(self, job_id: int) -> ApplicationPreviewResult:
        if (
            isinstance(job_id, bool)
            or not isinstance(job_id, int)
            or job_id <= 0
        ):
            raise ValueError("job_id must be a positive integer")

        try:
            job = self.database.get_job_by_id(job_id)
        except Exception as exc:
            return ApplicationPreviewResult(
                status=ApplicationPreviewStatus.FAILED,
                reason=f"Persisted job could not be loaded: {exc}",
                job_id=job_id,
            )

        if job is None:
            return ApplicationPreviewResult(
                status=ApplicationPreviewStatus.NOT_FOUND,
                reason=f"Job ID {job_id} does not exist.",
                job_id=job_id,
            )

        target = resolve_job_application_target(job)
        eligibility_reason = (
            SingleJobApplicationLauncher.eligibility_failure(job)
        )
        return ApplicationPreviewResult(
            status=(
                ApplicationPreviewStatus.READY
                if eligibility_reason is None
                else ApplicationPreviewStatus.BLOCKED
            ),
            reason=(
                "Job passed browser-free application preflight. External "
                "authorization is required before the workflow can run."
                if eligibility_reason is None
                else eligibility_reason
            ),
            job_id=job_id,
            job=job,
            source_url=job.url.encoded_string(),
            application_url=target.application_url,
            provider=target.provider,
            resume=job.resume_used,
        )
