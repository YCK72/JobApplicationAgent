from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.applications.run_coordinator import ApplicationRunCoordinator
from app.applications.workflow import (
    ApplicationWorkflowResult,
    ApplicationWorkflowStatus,
)
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)
from app.jobs.pipeline import PipelineOutcome, PipelineResult
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker
from app.applications.target_resolver import (
    ApplicationTargetStatus,
    resolve_job_application_target,
)


class SingleJobLaunchStatus(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SingleJobLaunchResult:
    status: SingleJobLaunchStatus
    reason: str
    job_id: int
    job: Job | None = None
    completed_actions: int = 0
    export_path: Path | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == SingleJobLaunchStatus.READY_FOR_REVIEW

    @property
    def may_submit(self) -> bool:
        return False


@dataclass(frozen=True)
class SingleJobCandidate:
    job_id: int
    job: Job


class SingleJobApplicationLauncher:
    """Launch one exact persisted job through the controlled workflow.

    The launcher reconstructs an AUTO_READY pipeline result only for a
    persisted AUTO job still waiting in NEEDS_APPLICATION. External execution
    must be explicitly authorized before the workflow is called. Successful
    field filling is recorded as FORM_STARTED for later human review.

    This class does not submit applications or confirm submissions.
    """

    _WORKFLOW_STATUS_MAP = {
        ApplicationWorkflowStatus.READY_FOR_REVIEW:
            SingleJobLaunchStatus.READY_FOR_REVIEW,
        ApplicationWorkflowStatus.NEEDS_REVIEW:
            SingleJobLaunchStatus.NEEDS_REVIEW,
        ApplicationWorkflowStatus.NOT_ELIGIBLE:
            SingleJobLaunchStatus.NOT_ELIGIBLE,
        ApplicationWorkflowStatus.BLOCKED:
            SingleJobLaunchStatus.BLOCKED,
        ApplicationWorkflowStatus.FAILED:
            SingleJobLaunchStatus.FAILED,
    }

    def __init__(
        self,
        *,
        database: JobDatabase,
        coordinator: ApplicationRunCoordinator,
        tracker: ExcelTracker,
    ) -> None:
        self.database = database
        self.coordinator = coordinator
        self.tracker = tracker

    def run(
        self,
        *,
        job_id: int,
        allow_external: bool = False,
    ) -> SingleJobLaunchResult:
        if (
            isinstance(job_id, bool)
            or not isinstance(job_id, int)
            or job_id <= 0
        ):
            raise ValueError("job_id must be a positive integer")

        try:
            job = self.database.get_job_by_id(job_id)
        except Exception as exc:
            return self._result(
                status=SingleJobLaunchStatus.FAILED,
                reason=f"Persisted job could not be loaded: {exc}",
                job_id=job_id,
            )

        if job is None:
            return self._result(
                status=SingleJobLaunchStatus.NOT_FOUND,
                reason=f"Job ID {job_id} does not exist.",
                job_id=job_id,
            )

        eligibility_reason = self.eligibility_failure(job)
        if eligibility_reason is not None:
            return self._result(
                status=SingleJobLaunchStatus.NOT_ELIGIBLE,
                reason=eligibility_reason,
                job_id=job_id,
                job=job,
            )

        if not allow_external:
            return self._result(
                status=SingleJobLaunchStatus.AUTHORIZATION_REQUIRED,
                reason=(
                    "External browser inspection and mutation require "
                    "explicit authorization for this exact job."
                ),
                job_id=job_id,
                job=job,
            )

        pipeline_result = PipelineResult(
            job=job,
            outcome=PipelineOutcome.AUTO_READY,
            reason=(
                "Exact persisted NEEDS_APPLICATION job selected by ID for "
                "the controlled application workflow."
            ),
            job_id=job_id,
        )
        original_status = job.status
        original_notes = job.notes

        try:
            workflow_result = self.coordinator.run(
                pipeline_result,
                allow_external=True,
            )
        except Exception as exc:
            workflow_result = ApplicationWorkflowResult(
                status=ApplicationWorkflowStatus.FAILED,
                reason=f"Unexpected application launch failure: {exc}",
                completed_actions=0,
            )

        if workflow_result.status == ApplicationWorkflowStatus.READY_FOR_REVIEW:
            persistence_failure = self._record_form_started(
                job=job,
                job_id=job_id,
                original_status=original_status,
                original_notes=original_notes,
            )
            if persistence_failure is not None:
                workflow_result = persistence_failure

        result = self._from_workflow_result(
            workflow_result=workflow_result,
            job=job,
            job_id=job_id,
        )
        return self._refresh_tracker(result)

    def list_eligible(self) -> list[SingleJobCandidate]:
        """List exact persisted identities that pass launcher preflight."""

        return [
            SingleJobCandidate(job_id=job_id, job=job)
            for job_id, job in self.database.get_jobs_with_ids()
            if self.eligibility_failure(job) is None
        ]

    @staticmethod
    def eligibility_failure(job: Job) -> str | None:
        """Return the deterministic reason a persisted job cannot run."""

        if job.status != ApplicationStatus.NEEDS_APPLICATION:
            return (
                "Job must be in NEEDS_APPLICATION status; current status is "
                f"{job.status.value}."
            )
        if job.company_rule != CompanyRule.AUTO:
            return (
                "Job company routing does not permit automatic application."
            )
        if job.application_method != ApplicationMethod.AUTO:
            return "Job application method is not AUTO."
        target = resolve_job_application_target(job)
        if target.status != ApplicationTargetStatus.RESOLVED:
            return f"Job has no verified supported application target: {target.reason}"
        return None

    def _record_form_started(
        self,
        *,
        job: Job,
        job_id: int,
        original_status: ApplicationStatus,
        original_notes: str | None,
    ) -> ApplicationWorkflowResult | None:
        note = (
            "Application workflow: authorized fields were populated; human "
            "review and manual submission are required."
        )
        notes = f"{job.notes.rstrip()}\n{note}" if job.notes else note

        try:
            self.database.update_application_state(
                job_id=job_id,
                status=ApplicationStatus.FORM_STARTED,
                notes=notes,
            )
        except Exception as exc:
            job.status = original_status
            job.notes = original_notes
            return ApplicationWorkflowResult(
                status=ApplicationWorkflowStatus.FAILED,
                reason=(
                    "Authorized fields were populated, but FORM_STARTED "
                    f"could not be persisted: {exc}"
                ),
                completed_actions=0,
            )

        job.status = ApplicationStatus.FORM_STARTED
        job.notes = notes
        return None

    def _from_workflow_result(
        self,
        *,
        workflow_result: ApplicationWorkflowResult,
        job: Job,
        job_id: int,
    ) -> SingleJobLaunchResult:
        status = self._WORKFLOW_STATUS_MAP.get(
            workflow_result.status,
            SingleJobLaunchStatus.FAILED,
        )
        return self._result(
            status=status,
            reason=workflow_result.reason,
            job_id=job_id,
            job=job,
            completed_actions=workflow_result.completed_actions,
        )

    def _refresh_tracker(
        self,
        result: SingleJobLaunchResult,
    ) -> SingleJobLaunchResult:
        try:
            export_path = self.tracker.generate()
        except Exception as exc:
            return self._result(
                status=SingleJobLaunchStatus.FAILED,
                reason=(
                    f"{result.reason} Tracker refresh failed: {exc}"
                ),
                job_id=result.job_id,
                job=result.job,
                completed_actions=result.completed_actions,
            )

        return self._result(
            status=result.status,
            reason=result.reason,
            job_id=result.job_id,
            job=result.job,
            completed_actions=result.completed_actions,
            export_path=export_path,
        )

    @staticmethod
    def _result(
        *,
        status: SingleJobLaunchStatus,
        reason: str,
        job_id: int,
        job: Job | None = None,
        completed_actions: int = 0,
        export_path: Path | None = None,
    ) -> SingleJobLaunchResult:
        return SingleJobLaunchResult(
            status=status,
            reason=reason,
            job_id=job_id,
            job=job,
            completed_actions=completed_actions,
            export_path=export_path,
        )
