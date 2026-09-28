from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, call
import pytest
from app.applications.execution_guard import ExternalExecutionGuard

from app.applications.browser_form_executor import (
    BrowserExecutionStatus,
    BrowserFormExecutor,
)
from app.applications.execution_guard import (
    ExecutionTargetAuthorization,
    ExecutionTargetStatus,
)
from app.applications.form_executor import (
    AuthorizedFieldAction,
    ExecutionPlanStatus,
    FormExecutionPlan,
)
from app.applications.form_models import (
    FormField,
    FormFieldType,
)


TARGET_URL = "https://example.com/application"
OTHER_TARGET_URL = "https://example.com/other"


def make_field(
    field_id: str = "first_name",
    label: str = "First Name",
    field_type: FormFieldType = FormFieldType.TEXT,
) -> FormField:
    return FormField(
        field_id=field_id,
        label=label,
        field_type=field_type,
    )


def make_action(
    *,
    field: FormField | None = None,
    value: str = "Test",
) -> AuthorizedFieldAction:
    return AuthorizedFieldAction(
        field=field or make_field(),
        value=value,
    )


def make_plan(
    *actions: AuthorizedFieldAction,
    status: ExecutionPlanStatus = ExecutionPlanStatus.AUTHORIZED,
    authorized_resume_path: str | None = None,
) -> FormExecutionPlan:
    return FormExecutionPlan(
        actions=tuple(actions),
        status=status,
        reason="Test execution plan.",
        authorized_resume_path=authorized_resume_path,
    )


def make_writer(
    current_url: str = TARGET_URL,
):
    writer = MagicMock()
    writer.current_url = current_url
    return writer


def make_target_authorization(
    *,
    status: ExecutionTargetStatus = ExecutionTargetStatus.AUTHORIZED,
    target_url: str | None = TARGET_URL,
) -> ExecutionTargetAuthorization:
    return ExecutionTargetAuthorization(
        status=status,
        reason="Test target authorization.",
        target_url=target_url,
    )


def execute(
    executor: BrowserFormExecutor,
    plan: FormExecutionPlan,
):
    return executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )


def test_authorized_text_action_reaches_writer():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    field = make_field()
    plan = make_plan(
        make_action(
            field=field,
            value="Test",
        )
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.succeeded is True
    assert result.completed_actions == 1
    assert result.may_submit is False

    writer.write_text.assert_called_once_with(
        field=field,
        value="Test",
    )


def test_multiple_authorized_actions_execute_in_order():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    first_name = make_field(
        "first_name",
        "First Name",
    )
    email = make_field(
        "email",
        "Email",
        FormFieldType.EMAIL,
    )

    plan = make_plan(
        make_action(
            field=first_name,
            value="Test",
        ),
        make_action(
            field=email,
            value="test@example.com",
        ),
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 2

    assert writer.write_text.call_args_list == [
        call(
            field=first_name,
            value="Test",
        ),
        call(
            field=email,
            value="test@example.com",
        ),
    ]


def test_blocked_plan_never_reaches_writer():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action(),
        status=ExecutionPlanStatus.BLOCKED,
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.succeeded is False
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()


def test_unsupported_field_type_never_reaches_writer():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action(
            field=make_field(
                "unsupported",
                "Unsupported",
                FormFieldType.RADIO,
            ),
            value="Verified Value",
        )
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()
    writer.select_option.assert_not_called()


def test_external_resume_file_reaches_writer():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    field = make_field(
        "resume",
        "Resume",
        FormFieldType.FILE,
    )

    resume_path = "resume.pdf"

    plan = make_plan(
        make_action(
            field=field,
            value=resume_path,
        ),
        authorized_resume_path=str(
            Path(resume_path).resolve()
        ),
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1
    assert result.may_submit is False

    writer.upload_file.assert_called_once_with(
        field=field,
        file_path=resume_path,
    )


def test_writer_failure_stops_execution():
    writer = make_writer()
    writer.write_text.side_effect = RuntimeError(
        "simulated browser failure"
    )

    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action()
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.FAILED
    assert result.succeeded is False
    assert result.completed_actions == 0
    assert result.may_submit is False
    assert "simulated browser failure" in result.reason

    writer.write_text.assert_called_once()


def test_failure_stops_later_actions():
    writer = make_writer()

    writer.write_text.side_effect = [
        None,
        RuntimeError("second action failed"),
        None,
    ]

    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action(
            field=make_field(
                "first_name",
                "First Name",
            ),
            value="Test",
        ),
        make_action(
            field=make_field(
                "email",
                "Email",
                FormFieldType.EMAIL,
            ),
            value="test@example.com",
        ),
        make_action(
            field=make_field(
                "city",
                "City",
            ),
            value="Seattle",
        ),
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.FAILED
    assert result.completed_actions == 1
    assert result.may_submit is False
    assert writer.write_text.call_count == 2


def test_empty_authorized_plan_completes_without_writer_calls():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    result = execute(
        executor,
        make_plan(),
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.succeeded is True
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()


def test_blocked_target_never_reaches_writer():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action()
    )

    target_authorization = make_target_authorization(
        status=ExecutionTargetStatus.BLOCKED,
        target_url=None,
    )

    result = executor.execute(
        plan,
        target_authorization=target_authorization,
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.succeeded is False
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()


def test_empty_plan_still_requires_target_authorization():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    target_authorization = make_target_authorization(
        status=ExecutionTargetStatus.BLOCKED,
        target_url=None,
    )

    result = executor.execute(
        make_plan(),
        target_authorization=target_authorization,
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.succeeded is False
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()


def test_authorization_for_different_url_never_reaches_writer():
    writer = make_writer(
        current_url=OTHER_TARGET_URL
    )
    executor = BrowserFormExecutor(writer)

    result = executor.execute(
        make_plan(make_action()),
        target_authorization=make_target_authorization(
            target_url=TARGET_URL,
        ),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False
    assert "does not match" in result.reason

    writer.write_text.assert_not_called()


def test_authorized_target_without_bound_url_fails_closed():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    target_authorization = ExecutionTargetAuthorization(
        status=ExecutionTargetStatus.AUTHORIZED,
        reason="Malformed test authorization.",
        target_url=None,
    )

    result = executor.execute(
        make_plan(make_action()),
        target_authorization=target_authorization,
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()


def test_invalid_current_browser_url_fails_closed():
    writer = make_writer(
        current_url="not-a-url"
    )
    executor = BrowserFormExecutor(writer)

    result = executor.execute(
        make_plan(make_action()),
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False
    assert "could not be safely normalized" in result.reason

    writer.write_text.assert_not_called()


def test_equivalent_normalized_current_url_is_allowed():
    writer = make_writer(
        current_url="HTTPS://EXAMPLE.COM:443/application"
    )
    executor = BrowserFormExecutor(writer)

    result = executor.execute(
        make_plan(make_action()),
        target_authorization=make_target_authorization(
            target_url=TARGET_URL,
        ),
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1

    writer.write_text.assert_called_once()


def test_navigation_between_actions_blocks_later_mutation():
    writer = MagicMock()

    type(writer).current_url = PropertyMock(
        side_effect=[
            TARGET_URL,
            TARGET_URL,
            OTHER_TARGET_URL,
        ]
    )

    executor = BrowserFormExecutor(writer)

    first_action = make_action(
        field=make_field(
            "first_name",
            "First Name",
        ),
        value="Test",
    )
    second_action = make_action(
        field=make_field(
            "email",
            "Email",
            FormFieldType.EMAIL,
        ),
        value="test@example.com",
    )

    result = executor.execute(
        make_plan(
            first_action,
            second_action,
        ),
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 1
    assert result.may_submit is False
    assert "does not match" in result.reason

    writer.write_text.assert_called_once_with(
        field=first_action.field,
        value=first_action.value,
    )


def test_query_difference_blocks_mutation():
    writer = make_writer(
        current_url=f"{TARGET_URL}?source=other"
    )
    executor = BrowserFormExecutor(writer)

    result = executor.execute(
        make_plan(make_action()),
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0

    writer.write_text.assert_not_called()


def test_fragment_difference_blocks_mutation():
    writer = make_writer(
        current_url=f"{TARGET_URL}#different"
    )
    executor = BrowserFormExecutor(writer)

    result = executor.execute(
        make_plan(make_action()),
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0

    writer.write_text.assert_not_called()

def test_external_sensitive_field_never_reaches_writer():
    writer = make_writer()

    executor = BrowserFormExecutor(writer)

    action = AuthorizedFieldAction(
        field=FormField(
            field_id="work_authorization",
            label="Are you authorized to work in the United States?",
            field_type=FormFieldType.TEXT,
        ),
        value="Verified Value",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Forged execution plan.",
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()


def test_external_review_field_never_reaches_writer():
    writer = make_writer()

    executor = BrowserFormExecutor(writer)

    action = AuthorizedFieldAction(
        field=FormField(
            field_id="short_answer",
            label="Why are you interested in this role?",
            field_type=FormFieldType.TEXTAREA,
        ),
        value="Generated answer",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Forged execution plan.",
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0

    writer.write_text.assert_not_called()


def test_external_safe_profile_field_reaches_writer():
    writer = make_writer()

    executor = BrowserFormExecutor(writer)

    action = AuthorizedFieldAction(
        field=FormField(
            field_id="first_name",
            label="First Name",
            field_type=FormFieldType.TEXT,
        ),
        value="Verified Name",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Verified safe profile field.",
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1
    assert result.may_submit is False

    writer.write_text.assert_called_once_with(
        field=action.field,
        value="Verified Name",
    )


def test_external_safe_field_before_sensitive_field_stops_at_sensitive():
    writer = make_writer()

    executor = BrowserFormExecutor(writer)

    safe_action = AuthorizedFieldAction(
        field=FormField(
            field_id="first_name",
            label="First Name",
            field_type=FormFieldType.TEXT,
        ),
        value="Verified Name",
    )

    sensitive_action = AuthorizedFieldAction(
        field=FormField(
            field_id="sponsorship",
            label="Will you require visa sponsorship?",
            field_type=FormFieldType.TEXT,
        ),
        value="Forged Value",
    )

    plan = FormExecutionPlan(
        actions=(
            safe_action,
            sensitive_action,
        ),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Mixed forged execution plan.",
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 1
    assert result.may_submit is False

    writer.write_text.assert_called_once_with(
        field=safe_action.field,
        value="Verified Name",
    )

def test_local_fixture_does_not_use_external_semantic_policy(
    tmp_path,
):
    fixture_path = tmp_path / "safe_application_form.html"
    fixture_path.write_text(
        "<html></html>",
        encoding="utf-8",
    )

    fixture_url = fixture_path.resolve().as_uri()

    writer = MagicMock()
    writer.current_url = fixture_url

    external_policy = MagicMock()

    executor = BrowserFormExecutor(
        writer,
        external_field_policy=external_policy,
    )

    action = AuthorizedFieldAction(
        field=FormField(
            field_id="short_answer",
            label="Short Answer",
            field_type=FormFieldType.TEXTAREA,
        ),
        value="Controlled fixture value",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Controlled local fixture.",
    )

    guard = ExternalExecutionGuard(
        allowed_local_fixture=fixture_path,
    )

    authorization = guard.authorize(fixture_url)

    result = executor.execute(
        plan,
        target_authorization=authorization,
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1

    external_policy.authorize.assert_not_called()

    writer.write_text.assert_called_once_with(
        field=action.field,
        value="Controlled fixture value",
    )
def test_local_fixture_select_reaches_writer(
    tmp_path,
):
    fixture_path = tmp_path / "safe_application_form.html"
    fixture_path.write_text(
        "<html></html>",
        encoding="utf-8",
    )

    fixture_url = fixture_path.resolve().as_uri()

    writer = MagicMock()
    writer.current_url = fixture_url

    external_policy = MagicMock()

    executor = BrowserFormExecutor(
        writer,
        external_field_policy=external_policy,
    )

    field = FormField(
        field_id="country",
        label="Country",
        field_type=FormFieldType.SELECT,
        options=[
            "Select...",
            "United States",
            "Canada",
        ],
    )

    action = AuthorizedFieldAction(
        field=field,
        value="United States",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Controlled local SELECT fixture.",
    )

    guard = ExternalExecutionGuard(
        allowed_local_fixture=fixture_path,
    )

    authorization = guard.authorize(fixture_url)

    result = executor.execute(
        plan,
        target_authorization=authorization,
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1
    assert result.may_submit is False

    external_policy.authorize.assert_not_called()

    writer.select_option.assert_called_once_with(
        field=field,
        value="United States",
    )

    writer.write_text.assert_not_called()


def test_external_safe_select_reaches_writer():
    writer = make_writer()

    executor = BrowserFormExecutor(writer)

    field = FormField(
        field_id="country",
        label="Country",
        field_type=FormFieldType.SELECT,
        options=[
            "United States",
            "Canada",
        ],
    )

    action = AuthorizedFieldAction(
        field=field,
        value="United States",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Verified safe SELECT execution plan.",
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1
    assert result.may_submit is False

    writer.select_option.assert_called_once_with(
        field=field,
        value="United States",
    )
    writer.write_text.assert_not_called()


def test_external_sensitive_select_remains_blocked():
    writer = make_writer()

    executor = BrowserFormExecutor(writer)

    field = FormField(
        field_id="sponsorship",
        label="Will you require visa sponsorship?",
        field_type=FormFieldType.SELECT,
        options=[
            "Yes",
            "No",
        ],
    )

    action = AuthorizedFieldAction(
        field=field,
        value="No",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Forged sensitive SELECT plan.",
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.select_option.assert_not_called()
    writer.write_text.assert_not_called()


@pytest.mark.parametrize(
    "field_type",
    [
        FormFieldType.RADIO,
        FormFieldType.CHECKBOX,
        FormFieldType.UNKNOWN,
    ],
)
def test_non_select_non_text_controls_remain_blocked(
    field_type: FormFieldType,
):
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    field = FormField(
        field_id="unsupported",
        label="Unsupported",
        field_type=field_type,
    )

    plan = make_plan(
        make_action(
            field=field,
            value="Verified Value",
        )
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()
    writer.select_option.assert_not_called()

def test_local_fixture_file_reaches_writer(
    tmp_path,
):
    fixture_path = tmp_path / "safe_application_form.html"
    fixture_path.write_text(
        "<html></html>",
        encoding="utf-8",
    )

    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4 test")

    fixture_url = fixture_path.resolve().as_uri()

    writer = MagicMock()
    writer.current_url = fixture_url

    external_policy = MagicMock()

    executor = BrowserFormExecutor(
        writer,
        external_field_policy=external_policy,
    )

    field = FormField(
        field_id="resume",
        label="Resume",
        field_type=FormFieldType.FILE,
    )

    action = AuthorizedFieldAction(
        field=field,
        value=str(resume_path),
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Controlled local FILE fixture.",
        authorized_resume_path=str(resume_path.resolve()),
    )

    guard = ExternalExecutionGuard(
        allowed_local_fixture=fixture_path,
    )

    authorization = guard.authorize(fixture_url)

    result = executor.execute(
        plan,
        target_authorization=authorization,
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1
    assert result.may_submit is False

    external_policy.authorize.assert_not_called()

    writer.upload_file.assert_called_once_with(
        field=field,
        file_path=str(resume_path),
    )

    writer.write_text.assert_not_called()
    writer.select_option.assert_not_called()


def test_external_non_resume_file_remains_blocked():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    field = FormField(
        field_id="cover_letter",
        label="Cover Letter",
        field_type=FormFieldType.FILE,
    )

    action = AuthorizedFieldAction(
        field=field,
        value="data/resumes/resume.pdf",
    )

    plan = make_plan(action)

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.upload_file.assert_not_called()

def test_file_action_matching_plan_resume_authorization_reaches_writer():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    field = make_field(
        "resume",
        "Resume",
        FormFieldType.FILE,
    )

    action = AuthorizedFieldAction(
        field=field,
        value="data/resumes/sde_resume.pdf",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Test authorized plan.",
        authorized_resume_path=str(
            Path("data/resumes/sde_resume.pdf").resolve()
        ),
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1
    assert result.may_submit is False

    writer.upload_file.assert_called_once_with(
        field=field,
        file_path="data/resumes/sde_resume.pdf",
    )


def test_file_action_mismatching_plan_resume_authorization_is_blocked():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    field = make_field(
        "resume",
        "Resume",
        FormFieldType.FILE,
    )

    action = AuthorizedFieldAction(
        field=field,
        value="data/resumes/other_resume.pdf",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Test authorized plan.",
        authorized_resume_path=str(
            Path("data/resumes/sde_resume.pdf").resolve()
        ),
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.upload_file.assert_not_called()


def test_file_action_without_plan_resume_authorization_is_blocked():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    field = make_field(
        "resume",
        "Resume",
        FormFieldType.FILE,
    )

    action = AuthorizedFieldAction(
        field=field,
        value="data/resumes/sde_resume.pdf",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Test authorized plan.",
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.upload_file.assert_not_called()