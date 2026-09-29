from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
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
from app.applications.target_resolver import (
    ApplicationTargetStatus,
    resolve_job_application_target,
)
from app.jobs.pipeline import PipelineResult

ExecutionSessionFactory = Callable[
    [str],
    AbstractContextManager[BrowserFormExecutor],
]
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

    Unexpected exceptions crossing those service boundaries are converted
    into FAILED workflow results. This prevents an unexpected runtime
    failure from being mistaken for successful application preparation.
    """

    def __init__(
            self,
            *,
            preparation_service: ApplicationPreparationService,
            inspection_service: ApplicationInspectionService,
            form_executor: ApplicationFormExecutor,
            execution_guard: ExternalExecutionGuard,
            browser_executor: BrowserFormExecutor | None = None,
            execution_session_factory: ExecutionSessionFactory | None = None,
    ) -> None:
        if (
                browser_executor is None
                and execution_session_factory is None
        ):
            raise ValueError(
                "ApplicationWorkflow requires either a browser executor "
                "or an execution-session factory."
            )

        if (
                browser_executor is not None
                and execution_session_factory is not None
        ):
            raise ValueError(
                "ApplicationWorkflow cannot use both a browser executor "
                "and an execution-session factory."
            )

        self._preparation_service = preparation_service
        self._inspection_service = inspection_service
        self._form_executor = form_executor
        self._execution_guard = execution_guard
        self._browser_executor = browser_executor
        self._execution_session_factory = execution_session_factory

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

        Unexpected lower-layer exceptions fail closed as FAILED workflow
        results. Individual services retain responsibility for rollback
        of any state they mutate before raising.
        """

        try:
            return self._run_controlled(
                pipeline_result,
                allow_external=allow_external,
            )
        except Exception as exc:
            return ApplicationWorkflowResult(
                status=ApplicationWorkflowStatus.FAILED,
                reason=(
                    "Unexpected application workflow failure: "
                    f"{exc}"
                ),
                completed_actions=0,
            )

    def _run_controlled(
        self,
        pipeline_result: PipelineResult,
        *,
        allow_external: bool,
    ) -> ApplicationWorkflowResult:
        """
        Execute the existing controlled workflow stages.

        This method assumes exception containment is owned by run().
        Normal typed failure results continue to be handled at the
        specific boundary that produced them.
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

        target = resolve_job_application_target(job)
        if target.status != ApplicationTargetStatus.RESOLVED:
            return self._blocked(target.reason)

        target_authorization = self._execution_guard.authorize(
            target.application_url,
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

        if self._execution_session_factory is not None:
            with self._execution_session_factory(
                    target.application_url
            ) as browser_executor:
                browser_result = browser_executor.execute(
                    execution_plan,
                    target_authorization=target_authorization,
                )
        else:
            if self._browser_executor is None:
                raise RuntimeError(
                    "Application workflow has no browser execution boundary."
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
