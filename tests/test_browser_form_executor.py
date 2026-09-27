from unittest.mock import MagicMock, PropertyMock, call

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
) -> FormExecutionPlan:
    return FormExecutionPlan(
        actions=tuple(actions),
        status=status,
        reason="Test execution plan.",
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
                "country",
                "Country",
                FormFieldType.SELECT,
            ),
            value="United States",
        )
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()


def test_file_field_never_reaches_writer():
    writer = make_writer()
    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action(
            field=make_field(
                "resume",
                "Resume",
                FormFieldType.FILE,
            ),
            value="resume.pdf",
        )
    )

    result = execute(executor, plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()


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