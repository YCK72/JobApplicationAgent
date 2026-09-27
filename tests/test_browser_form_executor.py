from unittest.mock import MagicMock

from app.applications.browser_form_executor import (
    BrowserExecutionStatus,
    BrowserFormExecutor,
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


def test_authorized_text_action_reaches_writer():
    writer = MagicMock()
    executor = BrowserFormExecutor(writer)

    field = make_field()
    plan = make_plan(
        make_action(
            field=field,
            value="Test",
        )
    )

    result = executor.execute(plan)

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.succeeded is True
    assert result.completed_actions == 1
    assert result.may_submit is False

    writer.write_text.assert_called_once_with(
        field=field,
        value="Test",
    )


def test_multiple_authorized_actions_execute_in_order():
    writer = MagicMock()
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

    result = executor.execute(plan)

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 2

    assert writer.write_text.call_args_list == [
        (( ), {"field": first_name, "value": "Test"}),
        (( ), {"field": email, "value": "test@example.com"}),
    ]


def test_blocked_plan_never_reaches_writer():
    writer = MagicMock()
    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action(),
        status=ExecutionPlanStatus.BLOCKED,
    )

    result = executor.execute(plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.succeeded is False
    assert result.completed_actions == 0

    writer.write_text.assert_not_called()


def test_unsupported_field_type_never_reaches_writer():
    writer = MagicMock()
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

    result = executor.execute(plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0

    writer.write_text.assert_not_called()


def test_file_field_never_reaches_writer():
    writer = MagicMock()
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

    result = executor.execute(plan)

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0

    writer.write_text.assert_not_called()


def test_writer_failure_stops_execution():
    writer = MagicMock()
    writer.write_text.side_effect = RuntimeError(
        "simulated browser failure"
    )

    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action()
    )

    result = executor.execute(plan)

    assert result.status == BrowserExecutionStatus.FAILED
    assert result.succeeded is False
    assert result.completed_actions == 0
    assert "simulated browser failure" in result.reason

    writer.write_text.assert_called_once()


def test_failure_stops_later_actions():
    writer = MagicMock()

    writer.write_text.side_effect = [
        None,
        RuntimeError("second action failed"),
        None,
    ]

    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        make_action(
            field=make_field("first_name", "First Name"),
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
            field=make_field("city", "City"),
            value="Seattle",
        ),
    )

    result = executor.execute(plan)

    assert result.status == BrowserExecutionStatus.FAILED
    assert result.completed_actions == 1
    assert writer.write_text.call_count == 2


def test_empty_authorized_plan_completes_without_writer_calls():
    writer = MagicMock()
    executor = BrowserFormExecutor(writer)

    result = executor.execute(
        make_plan()
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.succeeded is True
    assert result.completed_actions == 0
    assert result.may_submit is False

    writer.write_text.assert_not_called()
