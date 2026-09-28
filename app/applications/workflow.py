from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.applications.browser_form_executor import (
    BrowserExecutionStatus,
    BrowserFormExecutor,
)
from app.applications.execution_guard import (
    ExecutionTargetStatus,
    ExternalExecutionGuard,
)
from app.applications.form_executor import (
    ApplicationFormExecutor,
    ExecutionPlanStatus,
)
from app.applications.inspection_service import (
    ApplicationInspectionService,
    InspectionOutcome,
)
from app.applications.router import (
    ApplicationPreparationService,
    PreparationOutcome,
)
from app.jobs.pipeline import PipelineResult


class ApplicationWorkflowStatus(str, Enum):
    """
    Outcome of one controlled application-preparation workflow.

    READY_FOR_REVIEW means safe authorized field mutations completed,
    but the application has not been submitted.

    Every non-success state stops the workflow before later mutation
    boundaries are reached.
    """

    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ApplicationWorkflowResult:
    """
    Result of coordinating the existing application safety layers.

    This result never authorizes or represents final submission.
    """

    status: ApplicationWorkflowStatus
    reason: str
    completed_actions: int = 0

    @property
    def succeeded(self) -> bool:
        return (
            self.status
            == ApplicationWorkflowStatus.READY_FOR_REVIEW
        )

    @property
    def may_submit(self) -> bool:
        return False


class ApplicationWorkflow:
    """
    Coordinate the existing application preparation and execution layers.

    This class intentionally does not:

    - inspect application controls directly,
    - resolve answers,
    - authorize individual fields itself,
    - manipulate Playwright directly,
    - bypass target authorization,
    - submit an application.

    Each existing service remains responsible for its own safety
    boundary.
    """

    def __init__(
        self,
        *,
        preparation_service: ApplicationPreparationService,
        inspection_service: ApplicationInspectionService,
        form_executor: ApplicationFormExecutor,
        execution_guard: ExternalExecutionGuard,
        browser_executor: BrowserFormExecutor,
    ) -> None:
        self._preparation_service = preparation_service
        self._inspection_service = inspection_service
        self._form_executor = form_executor
        self._execution_guard = execution_guard
        self._browser_executor = browser_executor

    def run(
        self,
        pipeline_result: PipelineResult,
        *,
        allow_external: bool = False,
    ) -> ApplicationWorkflowResult:
        """
        Run one controlled application workflow.

        Successful completion means that all authorized browser field
        mutations completed and the form is ready for human review.

        It never means that the application was submitted.
        """

        preparation = self._preparation_service.prepare(
            pipeline_result
        )

        if preparation.outcome != PreparationOutcome.READY:
            return self._from_preparation_failure(
                preparation.outcome,
                preparation.reason,
            )

        job = preparation.job
        job_id = preparation.job_id

        inspection = self._inspection_service.inspect(
            job,
            job_id,
        )

        if inspection.outcome != InspectionOutcome.INSPECTED:
            return self._from_inspection_failure(
                inspection.outcome,
                inspection.reason,
            )

        if inspection.plan is None:
            return self._blocked(
                "Inspection succeeded without a form plan."
            )

        execution_plan = self._form_executor.authorize(
            inspection.plan,
            authorized_resume_path=job.resume_used,
        )

        if (
            execution_plan.status
            != ExecutionPlanStatus.AUTHORIZED
            or not execution_plan.may_execute
        ):
            return self._blocked(
                execution_plan.reason
            )

        target_authorization = self._execution_guard.authorize(
            str(job.url),
            allow_external=allow_external,
        )

        if (
            target_authorization.status
            != ExecutionTargetStatus.AUTHORIZED
            or not target_authorization.may_mutate
        ):
            return self._blocked(
                target_authorization.reason
            )

        browser_result = self._browser_executor.execute(
            execution_plan,
            target_authorization=target_authorization,
        )

        if (
            browser_result.status
            != BrowserExecutionStatus.COMPLETED
            or not browser_result.succeeded
        ):
            return ApplicationWorkflowResult(
                status=self._browser_failure_status(
                    browser_result.status
                ),
                reason=browser_result.reason,
                completed_actions=(
                    browser_result.completed_actions
                ),
            )

        return ApplicationWorkflowResult(
            status=(
                ApplicationWorkflowStatus.READY_FOR_REVIEW
            ),
            reason=(
                "Authorized application fields were populated. "
                "Final submission requires human review."
            ),
            completed_actions=(
                browser_result.completed_actions
            ),
        )

    @staticmethod
    def _from_preparation_failure(
        outcome: PreparationOutcome,
        reason: str,
    ) -> ApplicationWorkflowResult:
        if outcome == PreparationOutcome.NEEDS_REVIEW:
            status = ApplicationWorkflowStatus.NEEDS_REVIEW
        else:
            status = ApplicationWorkflowStatus.NOT_ELIGIBLE

        return ApplicationWorkflowResult(
            status=status,
            reason=reason,
        )

    @staticmethod
    def _from_inspection_failure(
        outcome: InspectionOutcome,
        reason: str,
    ) -> ApplicationWorkflowResult:
        if outcome == InspectionOutcome.NEEDS_REVIEW:
            status = ApplicationWorkflowStatus.NEEDS_REVIEW
        else:
            status = ApplicationWorkflowStatus.NOT_ELIGIBLE

        return ApplicationWorkflowResult(
            status=status,
            reason=reason,
        )

    @staticmethod
    def _browser_failure_status(
        status: BrowserExecutionStatus,
    ) -> ApplicationWorkflowStatus:
        if status == BrowserExecutionStatus.FAILED:
            return ApplicationWorkflowStatus.FAILED

        return ApplicationWorkflowStatus.BLOCKED

    @staticmethod
    def _blocked(
        reason: str,
    ) -> ApplicationWorkflowResult:
        return ApplicationWorkflowResult(
            status=ApplicationWorkflowStatus.BLOCKED,
            reason=reason,
        )