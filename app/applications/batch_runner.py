from __future__ import annotations

from dataclasses import dataclass

from app.applications.run_coordinator import (
    ApplicationRunCoordinator,
)
from app.applications.workflow import (
    ApplicationWorkflowResult,
    ApplicationWorkflowStatus,
)
from app.jobs.pipeline import (
    PipelineOutcome,
    PipelineResult,
)


@dataclass(frozen=True)
class ApplicationBatchItem:
    """
    Preserve the pipeline input together with its application result.
    """

    pipeline_result: PipelineResult
    workflow_result: ApplicationWorkflowResult

    @property
    def attempted(self) -> bool:
        return (
            self.pipeline_result.outcome
            == PipelineOutcome.AUTO_READY
        )

    @property
    def skipped(self) -> bool:
        return not self.attempted


@dataclass(frozen=True)
class ApplicationBatchResult:
    """
    Structured summary of processing multiple pipeline results.

    A skipped item is a pipeline result that was not AUTO_READY.
    It is distinct from an AUTO_READY application attempt that
    later became BLOCKED inside the controlled workflow.
    """

    results: list[ApplicationBatchItem]

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def attempted_count(self) -> int:
        return sum(
            item.attempted
            for item in self.results
        )

    @property
    def skipped_count(self) -> int:
        return sum(
            item.skipped
            for item in self.results
        )

    def _attempted_status_count(
        self,
        status: ApplicationWorkflowStatus,
    ) -> int:
        return sum(
            item.attempted
            and item.workflow_result.status == status
            for item in self.results
        )

    @property
    def ready_for_review_count(self) -> int:
        return self._attempted_status_count(
            ApplicationWorkflowStatus.READY_FOR_REVIEW
        )

    @property
    def needs_review_count(self) -> int:
        return self._attempted_status_count(
            ApplicationWorkflowStatus.NEEDS_REVIEW
        )

    @property
    def blocked_count(self) -> int:
        return self._attempted_status_count(
            ApplicationWorkflowStatus.BLOCKED
        )

    @property
    def failed_count(self) -> int:
        return self._attempted_status_count(
            ApplicationWorkflowStatus.FAILED
        )


class ApplicationBatchRunner:
    """
    Coordinate multiple PipelineResult objects through the existing
    single-result ApplicationRunCoordinator.

    Eligibility remains owned by ApplicationRunCoordinator. This
    layer only preserves results and summarizes batch outcomes.

    It does not submit applications, confirm submissions, or mark
    jobs APPLIED.
    """

    def __init__(
        self,
        *,
        coordinator: ApplicationRunCoordinator,
    ) -> None:
        self.coordinator = coordinator

    def run(
        self,
        pipeline_results: list[PipelineResult],
        *,
        allow_external: bool = False,
    ) -> ApplicationBatchResult:
        results: list[ApplicationBatchItem] = []

        for pipeline_result in pipeline_results:
            workflow_result = self.coordinator.run(
                pipeline_result,
                allow_external=allow_external,
            )

            results.append(
                ApplicationBatchItem(
                    pipeline_result=pipeline_result,
                    workflow_result=workflow_result,
                )
            )

        return ApplicationBatchResult(
            results=results,
        )