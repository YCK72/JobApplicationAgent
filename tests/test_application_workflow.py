from unittest.mock import MagicMock, call


from app.applications.browser_form_executor import (
    BrowserExecutionResult,
    BrowserExecutionStatus,
    BrowserFormExecutor,
)
from app.applications.execution_guard import (
    ExecutionTargetAuthorization,
    ExecutionTargetStatus,
    ExternalExecutionGuard,
)
from app.applications.form_executor import (
    ApplicationFormExecutor,
    ExecutionPlanStatus,
    FormExecutionPlan,
)
from app.applications.form_models import (
    FormField,
    FormFieldType,
)
from app.applications.form_plan import (
    FieldAction,
    FieldPlan,
    FormAnswerPlan,
    FormPlanStatus,
)
from app.applications.inspection_service import (
    InspectionOutcome,
    InspectionResult,
)
from app.applications.router import (
    PreparationOutcome,
    PreparationResult,
)
from app.applications.workflow import (
    ApplicationWorkflow,
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
    job: Job,
) -> PipelineResult:
    return PipelineResult(
        job=job,
        outcome=PipelineOutcome.AUTO_READY,
        reason="Test pipeline result.",
        job_id=123,
    )


def make_preparation_result(
    job: Job,
) -> PreparationResult:
    return PreparationResult(
        job=job,
        outcome=PreparationOutcome.READY,
        reason="Test preparation result.",
        job_id=123,
    )


def make_form_plan() -> FormAnswerPlan:
    return FormAnswerPlan(
        fields=(),
        status=FormPlanStatus.AUTO_FILL_ALLOWED,
        reason="Test form plan.",
    )


def make_inspection_result(
    job: Job,
    plan: FormAnswerPlan,
) -> InspectionResult:
    return InspectionResult(
        job=job,
        outcome=InspectionOutcome.INSPECTED,
        reason="Test inspection result.",
        plan=plan,
    )


def make_execution_plan() -> FormExecutionPlan:
    return FormExecutionPlan(
        actions=(),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Test execution plan.",
    )


def make_target_authorization() -> ExecutionTargetAuthorization:
    return ExecutionTargetAuthorization(
        status=ExecutionTargetStatus.AUTHORIZED,
        reason="Test target authorization.",
        target_url=TARGET_URL,
    )


def make_browser_result() -> BrowserExecutionResult:
    return BrowserExecutionResult(
        status=BrowserExecutionStatus.COMPLETED,
        reason="Test browser execution.",
        completed_actions=0,
    )


def test_successful_workflow_coordinates_existing_safety_layers_in_order():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    preparation_service = MagicMock()
    inspection_service = MagicMock()
    form_executor = MagicMock()
    execution_guard = MagicMock()
    browser_executor = MagicMock()

    preparation_result = make_preparation_result(job)
    form_plan = make_form_plan()
    inspection_result = make_inspection_result(
        job,
        form_plan,
    )
    execution_plan = make_execution_plan()
    target_authorization = make_target_authorization()
    browser_result = make_browser_result()

    events = []

    preparation_service.prepare.side_effect = (
        lambda result: (
            events.append("prepare"),
            setattr(
                job,
                "status",
                ApplicationStatus.READY_TO_APPLY,
            ),
            preparation_result,
        )[-1]
    )

    inspection_service.inspect.side_effect = (
        lambda inspected_job, job_id: (
            events.append("inspect"),
            inspection_result,
        )[-1]
    )

    form_executor.authorize.side_effect = (
        lambda plan, authorized_resume_path=None: (
            events.append("authorize_form"),
            execution_plan,
        )[-1]
    )

    execution_guard.authorize.side_effect = (
        lambda target_url, allow_external=False: (
            events.append("authorize_target"),
            target_authorization,
        )[-1]
    )

    browser_executor.execute.side_effect = (
        lambda plan, target_authorization: (
            events.append("execute_browser"),
            browser_result,
        )[-1]
    )

    workflow = ApplicationWorkflow(
        preparation_service=preparation_service,
        inspection_service=inspection_service,
        form_executor=form_executor,
        execution_guard=execution_guard,
        browser_executor=browser_executor,
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert events == [
        "prepare",
        "inspect",
        "authorize_form",
        "authorize_target",
        "execute_browser",
    ]

    preparation_service.prepare.assert_called_once_with(
        pipeline_result
    )

    inspection_service.inspect.assert_called_once_with(
        job,
        123,
    )

    form_executor.authorize.assert_called_once_with(
        form_plan,
        authorized_resume_path=job.resume_used,
    )

    execution_guard.authorize.assert_called_once_with(
        TARGET_URL,
        allow_external=True,
    )

    browser_executor.execute.assert_called_once_with(
        execution_plan,
        target_authorization=target_authorization,
    )

    assert (
        result.status
        == ApplicationWorkflowStatus.READY_FOR_REVIEW
    )
    assert result.succeeded is True
    assert result.completed_actions == 0
    assert result.may_submit is False

    assert job.status == ApplicationStatus.READY_TO_APPLY

def build_workflow():
    preparation_service = MagicMock()
    inspection_service = MagicMock()
    form_executor = MagicMock()
    execution_guard = MagicMock()
    browser_executor = MagicMock()

    workflow = ApplicationWorkflow(
        preparation_service=preparation_service,
        inspection_service=inspection_service,
        form_executor=form_executor,
        execution_guard=execution_guard,
        browser_executor=browser_executor,
    )

    return (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    )


def assert_no_calls_after_preparation(
    inspection_service,
    form_executor,
    execution_guard,
    browser_executor,
):
    inspection_service.inspect.assert_not_called()
    form_executor.authorize.assert_not_called()
    execution_guard.authorize.assert_not_called()
    browser_executor.execute.assert_not_called()


def assert_no_calls_after_inspection(
    form_executor,
    execution_guard,
    browser_executor,
):
    form_executor.authorize.assert_not_called()
    execution_guard.authorize.assert_not_called()
    browser_executor.execute.assert_not_called()


def assert_no_calls_after_form_authorization(
    execution_guard,
    browser_executor,
):
    execution_guard.authorize.assert_not_called()
    browser_executor.execute.assert_not_called()


def test_preparation_not_eligible_stops_workflow():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = PreparationResult(
        job=job,
        outcome=PreparationOutcome.NOT_ELIGIBLE,
        reason="Job is not eligible for preparation.",
        job_id=123,
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert (
        result.status
        == ApplicationWorkflowStatus.NOT_ELIGIBLE
    )
    assert result.succeeded is False
    assert result.completed_actions == 0
    assert result.may_submit is False

    assert_no_calls_after_preparation(
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    )


def test_preparation_needs_review_stops_workflow():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = PreparationResult(
        job=job,
        outcome=PreparationOutcome.NEEDS_REVIEW,
        reason="Preparation requires review.",
        job_id=123,
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert (
        result.status
        == ApplicationWorkflowStatus.NEEDS_REVIEW
    )
    assert result.succeeded is False
    assert result.may_submit is False

    assert_no_calls_after_preparation(
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    )


def test_inspection_needs_review_stops_before_execution_authorization():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = (
        make_preparation_result(job)
    )

    inspection_service.inspect.return_value = InspectionResult(
        job=job,
        outcome=InspectionOutcome.NEEDS_REVIEW,
        reason="Application form requires review.",
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert (
        result.status
        == ApplicationWorkflowStatus.NEEDS_REVIEW
    )
    assert result.succeeded is False
    assert result.may_submit is False

    assert_no_calls_after_inspection(
        form_executor,
        execution_guard,
        browser_executor,
    )


def test_inspection_without_plan_fails_closed():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = (
        make_preparation_result(job)
    )

    inspection_service.inspect.return_value = InspectionResult(
        job=job,
        outcome=InspectionOutcome.INSPECTED,
        reason="Malformed successful inspection.",
        plan=None,
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert result.status == ApplicationWorkflowStatus.BLOCKED
    assert result.succeeded is False
    assert result.may_submit is False
    assert "without a form plan" in result.reason

    assert_no_calls_after_inspection(
        form_executor,
        execution_guard,
        browser_executor,
    )


def test_blocked_form_execution_plan_stops_before_target_authorization():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = (
        make_preparation_result(job)
    )

    form_plan = make_form_plan()

    inspection_service.inspect.return_value = (
        make_inspection_result(
            job,
            form_plan,
        )
    )

    form_executor.authorize.return_value = FormExecutionPlan(
        actions=(),
        status=ExecutionPlanStatus.BLOCKED,
        reason="Execution plan blocked.",
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert result.status == ApplicationWorkflowStatus.BLOCKED
    assert result.succeeded is False
    assert result.may_submit is False

    assert_no_calls_after_form_authorization(
        execution_guard,
        browser_executor,
    )


def test_external_target_is_not_authorized_by_default():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = (
        make_preparation_result(job)
    )

    form_plan = make_form_plan()

    inspection_service.inspect.return_value = (
        make_inspection_result(
            job,
            form_plan,
        )
    )

    execution_plan = make_execution_plan()

    form_executor.authorize.return_value = execution_plan

    execution_guard.authorize.return_value = (
        ExecutionTargetAuthorization(
            status=ExecutionTargetStatus.BLOCKED,
            reason=(
                "External browser mutation requires "
                "explicit authorization."
            ),
            target_url=None,
        )
    )

    result = workflow.run(pipeline_result)

    execution_guard.authorize.assert_called_once_with(
        TARGET_URL,
        allow_external=False,
    )

    assert result.status == ApplicationWorkflowStatus.BLOCKED
    assert result.succeeded is False
    assert result.may_submit is False

    browser_executor.execute.assert_not_called()


def test_malformed_authorized_target_without_mutation_permission_stops():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = (
        make_preparation_result(job)
    )

    form_plan = make_form_plan()

    inspection_service.inspect.return_value = (
        make_inspection_result(
            job,
            form_plan,
        )
    )

    form_executor.authorize.return_value = (
        make_execution_plan()
    )

    execution_guard.authorize.return_value = (
        ExecutionTargetAuthorization(
            status=ExecutionTargetStatus.AUTHORIZED,
            reason="Malformed authorization.",
            target_url=None,
        )
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert result.status == ApplicationWorkflowStatus.BLOCKED
    assert result.succeeded is False
    assert result.may_submit is False

    browser_executor.execute.assert_not_called()


def test_browser_block_is_propagated_without_submission_permission():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = (
        make_preparation_result(job)
    )

    form_plan = make_form_plan()

    inspection_service.inspect.return_value = (
        make_inspection_result(
            job,
            form_plan,
        )
    )

    execution_plan = make_execution_plan()
    target_authorization = make_target_authorization()

    form_executor.authorize.return_value = execution_plan
    execution_guard.authorize.return_value = (
        target_authorization
    )

    browser_executor.execute.return_value = (
        BrowserExecutionResult(
            status=BrowserExecutionStatus.BLOCKED,
            reason="Browser execution blocked.",
            completed_actions=1,
        )
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert result.status == ApplicationWorkflowStatus.BLOCKED
    assert result.succeeded is False
    assert result.completed_actions == 1
    assert result.may_submit is False


def test_browser_failure_is_reported_without_submission_permission():
    job = make_job()
    pipeline_result = make_pipeline_result(job)

    (
        workflow,
        preparation_service,
        inspection_service,
        form_executor,
        execution_guard,
        browser_executor,
    ) = build_workflow()

    preparation_service.prepare.return_value = (
        make_preparation_result(job)
    )

    form_plan = make_form_plan()

    inspection_service.inspect.return_value = (
        make_inspection_result(
            job,
            form_plan,
        )
    )

    execution_plan = make_execution_plan()
    target_authorization = make_target_authorization()

    form_executor.authorize.return_value = execution_plan
    execution_guard.authorize.return_value = (
        target_authorization
    )

    browser_executor.execute.return_value = (
        BrowserExecutionResult(
            status=BrowserExecutionStatus.FAILED,
            reason="Simulated browser failure.",
            completed_actions=2,
        )
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert result.status == ApplicationWorkflowStatus.FAILED
    assert result.succeeded is False
    assert result.completed_actions == 2
    assert result.may_submit is False

def test_real_execution_boundaries_compose_with_explicit_external_authorization(
    tmp_path,
):
    local_fixture = tmp_path / "unused_local_fixture.html"
    local_fixture.write_text(
        "<html><body>unused fixture</body></html>",
        encoding="utf-8",
    )

    job = make_job()
    pipeline_result = make_pipeline_result(job)

    preparation_service = MagicMock()
    inspection_service = MagicMock()

    preparation_service.prepare.side_effect = lambda result: (
        setattr(
            job,
            "status",
            ApplicationStatus.READY_TO_APPLY,
        ),
        PreparationResult(
            job=job,
            outcome=PreparationOutcome.READY,
            reason="Controlled preparation result.",
            job_id=123,
        ),
    )[-1]

    field = FormField(
        field_id="first_name",
        label="First Name",
        field_type=FormFieldType.TEXT,
    )

    form_plan = FormAnswerPlan(
        fields=(
            FieldPlan(
                field=field,
                action=FieldAction.FILL_VERIFIED,
                value="Test",
                reason="Verified test value.",
            ),
        ),
        status=FormPlanStatus.AUTO_FILL_ALLOWED,
        reason="Controlled safe plan.",
    )

    inspection_service.inspect.return_value = InspectionResult(
        job=job,
        outcome=InspectionOutcome.INSPECTED,
        reason="Controlled inspection result.",
        plan=form_plan,
    )

    writer = MagicMock()
    writer.current_url = TARGET_URL

    workflow = ApplicationWorkflow(
        preparation_service=preparation_service,
        inspection_service=inspection_service,
        form_executor=ApplicationFormExecutor(),
        execution_guard=ExternalExecutionGuard(
            allowed_local_fixture=local_fixture,
        ),
        browser_executor=BrowserFormExecutor(writer),
    )

    result = workflow.run(
        pipeline_result,
        allow_external=True,
    )

    assert (
        result.status
        == ApplicationWorkflowStatus.READY_FOR_REVIEW
    )
    assert result.succeeded is True
    assert result.completed_actions == 1
    assert result.may_submit is False

    preparation_service.prepare.assert_called_once_with(
        pipeline_result
    )

    inspection_service.inspect.assert_called_once_with(
        job,
        123,
    )

    writer.write_text.assert_called_once_with(
        field=field,
        value="Test",
    )

    writer.select_option.assert_not_called()
    writer.select_radio_option.assert_not_called()
    writer.set_checkbox_state.assert_not_called()
    writer.upload_file.assert_not_called()

    assert job.status == ApplicationStatus.READY_TO_APPLY