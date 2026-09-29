from unittest.mock import MagicMock, call

from app.applications.batch_runner import (
    ApplicationBatchResult,
    ApplicationBatchRunner,
)
from app.applications.workflow import (
    ApplicationWorkflowResult,
    ApplicationWorkflowStatus,
)
from app.discovery.runner import DiscoveryRunResult
from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.jobs.pipeline import (
    PipelineOutcome,
    PipelineResult,
)


TARGET_URL = (
    "https://job-boards.greenhouse.io/"
    "example/jobs/123"
)


def make_job(
    *,
    company: str,
) -> Job:
    return Job(
        company=company,
        title="Software Engineer I",
        location="Seattle, WA",
        url=TARGET_URL,
        source="Test",
        status=ApplicationStatus.NEEDS_APPLICATION,
        resume_used="data/resumes/sde_resume.pdf",
    )


def make_pipeline_result(
    outcome: PipelineOutcome,
    *,
    company: str,
    job_id: int | None,
) -> PipelineResult:
    return PipelineResult(
        job=make_job(
            company=company,
        ),
        outcome=outcome,
        reason="Controlled pipeline result.",
        job_id=job_id,
    )


def make_workflow_result(
    status: ApplicationWorkflowStatus,
    *,
    completed_actions: int = 0,
) -> ApplicationWorkflowResult:
    return ApplicationWorkflowResult(
        status=status,
        reason="Controlled workflow result.",
        completed_actions=completed_actions,
    )


def test_empty_batch_returns_empty_summary():
    coordinator = MagicMock()

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run([])

    assert isinstance(
        result,
        ApplicationBatchResult,
    )

    assert result.results == []
    assert result.total_count == 0
    assert result.attempted_count == 0
    assert result.ready_for_review_count == 0
    assert result.needs_review_count == 0
    assert result.blocked_count == 0
    assert result.failed_count == 0
    assert result.skipped_count == 0

    coordinator.run.assert_not_called()


def test_batch_delegates_every_pipeline_result_in_order():
    coordinator = MagicMock()

    first = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="First Company",
        job_id=1,
    )

    second = make_pipeline_result(
        PipelineOutcome.MANUAL_REVIEW,
        company="Second Company",
        job_id=2,
    )

    coordinator.run.side_effect = [
        make_workflow_result(
            ApplicationWorkflowStatus.READY_FOR_REVIEW,
            completed_actions=2,
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.BLOCKED,
        ),
    ]

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run(
        [first, second],
        allow_external=True,
    )

    assert coordinator.run.call_args_list == [
        call(
            first,
            allow_external=True,
        ),
        call(
            second,
            allow_external=True,
        ),
    ]

    assert len(result.results) == 2

    assert (
        result.results[0].pipeline_result
        is first
    )

    assert (
        result.results[1].pipeline_result
        is second
    )


def test_batch_does_not_authorize_external_execution_by_default():
    coordinator = MagicMock()

    pipeline_result = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="Example Company",
        job_id=1,
    )

    coordinator.run.return_value = (
        make_workflow_result(
            ApplicationWorkflowStatus.READY_FOR_REVIEW,
        )
    )

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    runner.run([pipeline_result])

    coordinator.run.assert_called_once_with(
        pipeline_result,
        allow_external=False,
    )


def test_batch_summary_counts_attempted_and_skipped_results():
    coordinator = MagicMock()

    auto_ready = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="Auto Company",
        job_id=1,
    )

    manual = make_pipeline_result(
        PipelineOutcome.MANUAL_REVIEW,
        company="Manual Company",
        job_id=2,
    )

    filtered = make_pipeline_result(
        PipelineOutcome.FILTERED_OUT,
        company="Filtered Company",
        job_id=3,
    )

    coordinator.run.side_effect = [
        make_workflow_result(
            ApplicationWorkflowStatus.READY_FOR_REVIEW,
            completed_actions=3,
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.BLOCKED,
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.BLOCKED,
        ),
    ]

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run(
        [
            auto_ready,
            manual,
            filtered,
        ]
    )

    assert result.total_count == 3

    # Only AUTO_READY represents an application attempt.
    assert result.attempted_count == 1

    assert result.ready_for_review_count == 1
    assert result.needs_review_count == 0
    assert result.failed_count == 0

    # The coordinator blocks non-AUTO_READY results, but the
    # batch summary distinguishes those upstream skips from a
    # genuinely blocked AUTO_READY application attempt.
    assert result.blocked_count == 0
    assert result.skipped_count == 2


def test_batch_summary_distinguishes_blocked_auto_ready_from_skips():
    coordinator = MagicMock()

    auto_ready = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="Auto Company",
        job_id=1,
    )

    manual = make_pipeline_result(
        PipelineOutcome.MANUAL_REVIEW,
        company="Manual Company",
        job_id=2,
    )

    coordinator.run.side_effect = [
        make_workflow_result(
            ApplicationWorkflowStatus.BLOCKED,
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.BLOCKED,
        ),
    ]

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run(
        [auto_ready, manual]
    )

    assert result.attempted_count == 1
    assert result.blocked_count == 1
    assert result.skipped_count == 1


def test_batch_summary_counts_workflow_statuses_for_auto_ready_jobs():
    coordinator = MagicMock()

    pipeline_results = [
        make_pipeline_result(
            PipelineOutcome.AUTO_READY,
            company="Ready Company",
            job_id=1,
        ),
        make_pipeline_result(
            PipelineOutcome.AUTO_READY,
            company="Review Company",
            job_id=2,
        ),
        make_pipeline_result(
            PipelineOutcome.AUTO_READY,
            company="Blocked Company",
            job_id=3,
        ),
        make_pipeline_result(
            PipelineOutcome.AUTO_READY,
            company="Failed Company",
            job_id=4,
        ),
    ]

    coordinator.run.side_effect = [
        make_workflow_result(
            ApplicationWorkflowStatus.READY_FOR_REVIEW,
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.NEEDS_REVIEW,
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.BLOCKED,
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.FAILED,
        ),
    ]

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run(
        pipeline_results,
    )

    assert result.total_count == 4
    assert result.attempted_count == 4
    assert result.ready_for_review_count == 1
    assert result.needs_review_count == 1
    assert result.blocked_count == 1
    assert result.failed_count == 1
    assert result.skipped_count == 0


def test_batch_runner_has_no_submission_capability():
    runner = ApplicationBatchRunner(
        coordinator=MagicMock(),
    )

    assert not hasattr(runner, "submit")
    assert not hasattr(
        runner,
        "confirm_submission",
    )

    assert not hasattr(
        runner,
        "submission_confirmation_service",
    )


def test_discovery_result_pipeline_results_can_feed_application_batch():
    coordinator = MagicMock()

    auto_ready = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="Auto Company",
        job_id=1,
    )

    manual = make_pipeline_result(
        PipelineOutcome.MANUAL_REVIEW,
        company="Manual Company",
        job_id=2,
    )

    discovery_result = DiscoveryRunResult(
        pipeline_results=[
            auto_ready,
            manual,
        ],
        errors=[
            "Example Source: controlled discovery failure."
        ],
    )

    coordinator.run.side_effect = [
        make_workflow_result(
            ApplicationWorkflowStatus.READY_FOR_REVIEW,
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.BLOCKED,
        ),
    ]

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run(
        discovery_result.pipeline_results,
    )

    assert result.total_count == 2
    assert result.attempted_count == 1
    assert result.ready_for_review_count == 1
    assert result.skipped_count == 1

    # Application processing must not mutate or consume
    # discovery-level error reporting.
    assert discovery_result.errors == [
        "Example Source: controlled discovery failure."
    ]


def test_discovery_errors_do_not_become_application_attempts():
    coordinator = MagicMock()

    discovery_result = DiscoveryRunResult(
        pipeline_results=[],
        errors=[
            "Source A: discovery failed.",
            "Source B: discovery failed.",
        ],
    )

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run(
        discovery_result.pipeline_results,
    )

    assert result.total_count == 0
    assert result.attempted_count == 0
    assert result.skipped_count == 0

    coordinator.run.assert_not_called()

    assert discovery_result.error_count == 2

def test_unexpected_coordinator_exception_becomes_failed_result():
    coordinator = MagicMock()

    pipeline_result = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="Failing Company",
        job_id=1,
    )

    coordinator.run.side_effect = RuntimeError(
        "simulated unexpected runtime failure"
    )

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run(
        [pipeline_result],
        allow_external=True,
    )

    assert result.total_count == 1
    assert result.attempted_count == 1
    assert result.failed_count == 1
    assert result.skipped_count == 0

    workflow_result = result.results[0].workflow_result

    assert (
        workflow_result.status
        == ApplicationWorkflowStatus.FAILED
    )
    assert workflow_result.succeeded is False
    assert workflow_result.completed_actions == 0
    assert workflow_result.may_submit is False
    assert (
        "simulated unexpected runtime failure"
        in workflow_result.reason
    )


def test_unexpected_failure_does_not_stop_later_jobs():
    coordinator = MagicMock()

    first = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="Failing Company",
        job_id=1,
    )

    second = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="Successful Company",
        job_id=2,
    )

    coordinator.run.side_effect = [
        RuntimeError(
            "first job failed unexpectedly"
        ),
        make_workflow_result(
            ApplicationWorkflowStatus.READY_FOR_REVIEW,
            completed_actions=3,
        ),
    ]

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run(
        [first, second],
    )

    assert result.total_count == 2
    assert result.attempted_count == 2
    assert result.failed_count == 1
    assert result.ready_for_review_count == 1
    assert result.skipped_count == 0

    assert (
        result.results[0].workflow_result.status
        == ApplicationWorkflowStatus.FAILED
    )

    assert (
        result.results[1].workflow_result.status
        == ApplicationWorkflowStatus.READY_FOR_REVIEW
    )

    assert coordinator.run.call_args_list == [
        call(
            first,
            allow_external=False,
        ),
        call(
            second,
            allow_external=False,
        ),
    ]


def test_non_auto_ready_exception_is_not_counted_as_application_failure():
    coordinator = MagicMock()

    manual = make_pipeline_result(
        PipelineOutcome.MANUAL_REVIEW,
        company="Manual Company",
        job_id=1,
    )

    coordinator.run.side_effect = RuntimeError(
        "simulated coordinator failure"
    )

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run([manual])

    assert result.total_count == 1
    assert result.attempted_count == 0
    assert result.failed_count == 0
    assert result.skipped_count == 1

    assert (
        result.results[0].workflow_result.status
        == ApplicationWorkflowStatus.FAILED
    )
    assert result.results[0].workflow_result.may_submit is False


def test_failure_isolation_does_not_add_submission_capability():
    coordinator = MagicMock()

    pipeline_result = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        company="Failing Company",
        job_id=1,
    )

    coordinator.run.side_effect = RuntimeError(
        "simulated failure"
    )

    runner = ApplicationBatchRunner(
        coordinator=coordinator,
    )

    result = runner.run([pipeline_result])

    assert result.failed_count == 1

    workflow_result = result.results[0].workflow_result

    assert workflow_result.may_submit is False

    assert not hasattr(
        runner,
        "submit",
    )
    assert not hasattr(
        runner,
        "confirm_submission",
    )
    assert not hasattr(
        runner,
        "submission_confirmation_service",
    )
