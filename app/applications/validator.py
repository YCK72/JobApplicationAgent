from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)
from app.applications.target_resolver import (
    ApplicationTargetStatus,
    resolve_job_application_target,
)


@dataclass(frozen=True)
class ValidationResult:
    """
    Result of validating whether a job is ready to enter the
    future browser-application layer.
    """

    ready: bool
    reason: str


class ApplicationValidator:
    """
    Deterministically validates whether a routed job has the
    minimum prerequisites required for application automation.

    This class does not open a browser, fill forms, answer
    application questions, or submit applications.
    """

    def validate(self, job: Job) -> ValidationResult:
        """
        Check whether a job is eligible to become READY_TO_APPLY.
        """

        if job.company_rule != CompanyRule.AUTO:
            return ValidationResult(
                ready=False,
                reason=(
                    "Company routing does not permit automated "
                    "application."
                ),
            )

        if job.application_method != ApplicationMethod.AUTO:
            return ValidationResult(
                ready=False,
                reason=(
                    "Application method is not AUTO."
                ),
            )

        if job.status != ApplicationStatus.NEEDS_APPLICATION:
            return ValidationResult(
                ready=False,
                reason=(
                    "Job is not in NEEDS_APPLICATION status."
                ),
            )

        if not job.resume_used:
            return ValidationResult(
                ready=False,
                reason=(
                    "No resume has been assigned to the job."
                ),
            )

        target = resolve_job_application_target(job)
        if target.status != ApplicationTargetStatus.RESOLVED:
            return ValidationResult(
                ready=False,
                reason=f"Application target is not ready: {target.reason}",
            )
        resume_path = Path(job.resume_used)

        if not resume_path.is_file():
            return ValidationResult(
                ready=False,
                reason=(
                    "Assigned resume file does not exist."
                ),
            )

        return ValidationResult(
            ready=True,
            reason=(
                "Job passed application readiness validation."
            ),
        )

    def prepare(self, job: Job) -> Job:
        """
        Apply readiness validation to a job.

        Only NEEDS_APPLICATION jobs participate in this state
        transition. Existing lifecycle states must never be
        overwritten by application preparation.
        """

        if job.status != ApplicationStatus.NEEDS_APPLICATION:
            return job

        result = self.validate(job)

        if result.ready:
            job.status = ApplicationStatus.READY_TO_APPLY
            return job

        job.status = ApplicationStatus.NEEDS_REVIEW

        note = f"Application validation: {result.reason}"

        if job.notes:
            job.notes = f"{job.notes}\n{note}"
        else:
            job.notes = note

        return job
