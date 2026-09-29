from unittest.mock import MagicMock

from app.applications.run_coordinator import (
    ApplicationRunCoordinator,
)
from app.applications.workflow import (
    ApplicationWorkflowResult,
    ApplicationWorkflowStatus,
)
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


def make_job() -> Job:
    return Job(
        company="Example Company",
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
    job_id: int | None = 123,
) -> PipelineResult:
    return PipelineResult(
        job=make_job(),
        outcome=outcome,
        reason="Controlled pipeline result.",
        job_id=job_id,
    )


def make_ready_for_review_result() -> ApplicationWorkflowResult:
    return ApplicationWorkflowResult(
        status=ApplicationWorkflowStatus.READY_FOR_REVIEW,
        reason="Controlled workflow completion.",
        completed_actions=1,
    )


def test_auto_ready_result_is_forwarded_to_application_workflow():
    workflow = MagicMock()
    workflow.run.return_value = make_ready_for_review_result()

    coordinator = ApplicationRunCoordinator(
        workflow=workflow,
    )

    pipeline_result = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
    )

    result = coordinator.run(
        pipeline_result,
        allow_external=True,
    )

    workflow.run.assert_called_once_with(
        pipeline_result,
        allow_external=True,
    )

    assert (
        result.status
        == ApplicationWorkflowStatus.READY_FOR_REVIEW
    )

    assert result.may_submit is False


def test_external_execution_is_not_authorized_by_default():
    workflow = MagicMock()
    workflow.run.return_value = make_ready_for_review_result()

    coordinator = ApplicationRunCoordinator(
        workflow=workflow,
    )

    pipeline_result = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
    )

    coordinator.run(pipeline_result)

    workflow.run.assert_called_once_with(
        pipeline_result,
        allow_external=False,
    )


def test_non_auto_ready_results_never_reach_application_workflow():
    blocked_outcomes = (
        PipelineOutcome.DUPLICATE,
        PipelineOutcome.FILTERED_OUT,
        PipelineOutcome.BLOCKED,
        PipelineOutcome.MANUAL_REVIEW,
    )

    for outcome in blocked_outcomes:
        workflow = MagicMock()

        coordinator = ApplicationRunCoordinator(
            workflow=workflow,
        )

        pipeline_result = make_pipeline_result(
            outcome,
        )

        result = coordinator.run(
            pipeline_result,
            allow_external=True,
        )

        workflow.run.assert_not_called()

        assert (
            result.status
            == ApplicationWorkflowStatus.BLOCKED
        )

        assert result.succeeded is False
        assert result.completed_actions == 0
        assert result.may_submit is False


def test_auto_ready_without_persisted_job_id_fails_closed():
    workflow = MagicMock()

    coordinator = ApplicationRunCoordinator(
        workflow=workflow,
    )

    pipeline_result = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
        job_id=None,
    )

    result = coordinator.run(
        pipeline_result,
        allow_external=True,
    )

    workflow.run.assert_not_called()

    assert (
        result.status
        == ApplicationWorkflowStatus.BLOCKED
    )

    assert result.succeeded is False
    assert result.may_submit is False

    assert "job id" in result.reason.lower()


def test_coordinator_has_no_submission_capability():
    workflow = MagicMock()

    coordinator = ApplicationRunCoordinator(
        workflow=workflow,
    )

    assert not hasattr(coordinator, "submit")
    assert not hasattr(coordinator, "confirm_submission")
    assert not hasattr(
        coordinator,
        "submission_confirmation_service",
    )


def test_ready_for_review_does_not_become_applied():
    workflow = MagicMock()
    workflow.run.return_value = make_ready_for_review_result()

    coordinator = ApplicationRunCoordinator(
        workflow=workflow,
    )

    pipeline_result = make_pipeline_result(
        PipelineOutcome.AUTO_READY,
    )

    result = coordinator.run(
        pipeline_result,
        allow_external=True,
    )

    assert (
        result.status
        == ApplicationWorkflowStatus.READY_FOR_REVIEW
    )

    assert result.may_submit is False

    assert (
        pipeline_result.job.status
        == ApplicationStatus.NEEDS_APPLICATION
    )

    assert (
        pipeline_result.job.status
        != ApplicationStatus.APPLIED
    )
