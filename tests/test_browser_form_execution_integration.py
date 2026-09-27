from unittest.mock import MagicMock, call

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
from app.browser.playwright_form_writer import (
    PlaywrightFieldWriter,
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


def make_plan(
    *actions: AuthorizedFieldAction,
    status: ExecutionPlanStatus = ExecutionPlanStatus.AUTHORIZED,
) -> FormExecutionPlan:
    return FormExecutionPlan(
        actions=tuple(actions),
        status=status,
        reason="Test execution plan.",
    )


def make_target_authorization() -> ExecutionTargetAuthorization:
    return ExecutionTargetAuthorization(
        status=ExecutionTargetStatus.AUTHORIZED,
        reason="Test target authorization.",
    )


def test_authorized_plan_reaches_playwright_fill():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    field = make_field()

    plan = make_plan(
        AuthorizedFieldAction(
            field=field,
            value="Test",
        )
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1
    assert result.may_submit is False

    page.locator.assert_called_once_with(
        '[id="first_name"]'
    )
    locator.fill.assert_called_once_with("Test")


def test_multiple_authorized_fields_reach_fill_in_order():
    page = MagicMock()

    first_locator = MagicMock()
    first_locator.count.return_value = 1

    email_locator = MagicMock()
    email_locator.count.return_value = 1

    page.locator.side_effect = [
        first_locator,
        email_locator,
    ]

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    first_name = make_field(
        field_id="first_name",
        label="First Name",
    )

    email = make_field(
        field_id="email",
        label="Email",
        field_type=FormFieldType.EMAIL,
    )

    plan = make_plan(
        AuthorizedFieldAction(
            field=first_name,
            value="Test",
        ),
        AuthorizedFieldAction(
            field=email,
            value="test@example.com",
        ),
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 2
    assert result.may_submit is False

    assert page.locator.call_args_list == [
        call('[id="first_name"]'),
        call('[id="email"]'),
    ]

    first_locator.fill.assert_called_once_with("Test")
    email_locator.fill.assert_called_once_with(
        "test@example.com"
    )


def test_blocked_plan_never_reaches_playwright():
    page = MagicMock()

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        AuthorizedFieldAction(
            field=make_field(),
            value="Test",
        ),
        status=ExecutionPlanStatus.BLOCKED,
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    page.locator.assert_not_called()


def test_unsupported_field_never_reaches_playwright():
    page = MagicMock()

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    field = make_field(
        field_id="country",
        label="Country",
        field_type=FormFieldType.SELECT,
    )

    plan = make_plan(
        AuthorizedFieldAction(
            field=field,
            value="United States",
        )
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    page.locator.assert_not_called()


def test_writer_resolution_failure_stops_execution():
    page = MagicMock()

    missing_id = MagicMock()
    missing_id.count.return_value = 0

    missing_name = MagicMock()
    missing_name.count.return_value = 0

    page.locator.side_effect = [
        missing_id,
        missing_name,
    ]

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        AuthorizedFieldAction(
            field=make_field(),
            value="Test",
        )
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.FAILED
    assert result.completed_actions == 0
    assert result.may_submit is False

    assert page.locator.call_args_list == [
        call('[id="first_name"]'),
        call('[name="first_name"]'),
    ]

    missing_id.fill.assert_not_called()
    missing_name.fill.assert_not_called()


def test_blocked_target_never_reaches_playwright():
    page = MagicMock()

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    plan = make_plan(
        AuthorizedFieldAction(
            field=make_field(),
            value="Test",
        )
    )

    target_authorization = ExecutionTargetAuthorization(
        status=ExecutionTargetStatus.BLOCKED,
        reason="External mutation was not authorized.",
    )

    result = executor.execute(
        plan,
        target_authorization=target_authorization,
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    page.locator.assert_not_called()