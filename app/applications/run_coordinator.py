from __future__ import annotations

from app.applications.workflow import (
    ApplicationWorkflow,
    ApplicationWorkflowResult,
    ApplicationWorkflowStatus,
)
from app.jobs.pipeline import (
    PipelineOutcome,
    PipelineResult,
)


class ApplicationRunCoordinator:
    """
    Safely bridge deterministic pipeline output into ApplicationWorkflow.

    This coordinator owns only the transition from an eligible,
    persisted AUTO_READY PipelineResult into the existing controlled
    application workflow.

    It does not:

    - discover jobs,
    - classify or score jobs,
    - choose resumes,
    - manipulate browser controls directly,
    - bypass ApplicationWorkflow safety layers,
    - authorize external execution by default,
    - submit applications,
    - confirm submission,
    - mark jobs APPLIED.
    """

    def __init__(
        self,
        *,
        workflow: ApplicationWorkflow,
    ) -> None:
        self.workflow = workflow

    def run(
        self,
        pipeline_result: PipelineResult,
        *,
        allow_external: bool = False,
    ) -> ApplicationWorkflowResult:
        """
        Run one eligible persisted pipeline result through the
        controlled application workflow.
        """

        if (
            pipeline_result.outcome
            != PipelineOutcome.AUTO_READY
        ):
            return self._blocked(
                "Pipeline result is not AUTO_READY; "
                "application workflow was not started."
            )

        if pipeline_result.job_id is None:
            return self._blocked(
                "AUTO_READY pipeline result has no persisted job ID; "
                "application workflow was not started."
            )

        return self.workflow.run(
            pipeline_result,
            allow_external=allow_external,
        )

    @staticmethod
    def _blocked(
        reason: str,
    ) -> ApplicationWorkflowResult:
        return ApplicationWorkflowResult(
            status=ApplicationWorkflowStatus.BLOCKED,
            reason=reason,
            completed_actions=0,
        )