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
from app.browser.playwright_form_writer import (
    PlaywrightFieldWriter,
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


def make_page(
    current_url: str = TARGET_URL,
):
    page = MagicMock()
    page.url = current_url
    return page


def make_target_authorization(
    target_url: str = TARGET_URL,
) -> ExecutionTargetAuthorization:
    return ExecutionTargetAuthorization(
        status=ExecutionTargetStatus.AUTHORIZED,
        reason="Test target authorization.",
        target_url=target_url,
    )


def test_authorized_plan_reaches_playwright_fill():
    page = make_page()

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
    page = make_page()

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
    page = make_page()

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
    page = make_page()

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    field = make_field(
        field_id="unsupported",
        label="Unsupported",
        field_type=FormFieldType.RADIO,
    )

    plan = make_plan(
        AuthorizedFieldAction(
            field=field,
            value="Verified Value",
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
    page = make_page()

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
    page = make_page()

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
        target_url=None,
    )

    result = executor.execute(
        plan,
        target_authorization=target_authorization,
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    page.locator.assert_not_called()


def test_authorization_for_url_a_cannot_mutate_url_b():
    page = make_page(
        current_url=OTHER_TARGET_URL
    )

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
        target_authorization=make_target_authorization(
            TARGET_URL
        ),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False
    assert "does not match" in result.reason

    page.locator.assert_not_called()


def test_navigation_between_fields_blocks_second_playwright_fill():
    page = MagicMock()

    type(page).url = PropertyMock(
        side_effect=[
            TARGET_URL,
            TARGET_URL,
            OTHER_TARGET_URL,
        ]
    )

    first_locator = MagicMock()
    first_locator.count.return_value = 1

    page.locator.return_value = first_locator

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

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 1
    assert result.may_submit is False
    assert "does not match" in result.reason

    page.locator.assert_called_once_with(
        '[id="first_name"]'
    )

    first_locator.fill.assert_called_once_with("Test")


def test_external_sensitive_field_never_reaches_playwright_fill():
    page = MagicMock()
    page.url = TARGET_URL

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    action = AuthorizedFieldAction(
        field=FormField(
            field_id="work_authorization",
            label="Are you authorized to work in the United States?",
            field_type=FormFieldType.TEXT,
        ),
        value="Forged Value",
    )

    plan = FormExecutionPlan(
        actions=(action,),
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Forged sensitive execution plan.",
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    page.locator.assert_not_called()


def test_external_review_field_never_reaches_playwright_fill():
    page = MagicMock()
    page.url = TARGET_URL

    writer = PlaywrightFieldWriter(page)
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
        reason="Forged review execution plan.",
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    page.locator.assert_not_called()


def test_external_safe_profile_field_reaches_playwright_fill():
    page = MagicMock()
    page.url = TARGET_URL

    locator = MagicMock()
    locator.count.return_value = 1
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)
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

    locator.fill.assert_called_once_with(
        "Verified Name"
    )


def test_external_resume_file_reaches_playwright_upload(
    tmp_path,
):
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4 test resume")

    page = make_page()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "file",
    }

    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    field = make_field(
        field_id="resume",
        label="Resume",
        field_type=FormFieldType.FILE,
    )

    plan = make_plan(
        AuthorizedFieldAction(
            field=field,
            value=str(resume_path),
        ),
        authorized_resume_path=str(resume_path.resolve()),
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.COMPLETED
    assert result.completed_actions == 1
    assert result.may_submit is False

    page.locator.assert_called_once_with(
        '[id="resume"]'
    )

    locator.set_input_files.assert_called_once_with(
        str(resume_path.resolve())
    )


def test_external_cover_letter_file_never_reaches_playwright_upload(
    tmp_path,
):
    cover_letter_path = tmp_path / "cover_letter.pdf"
    cover_letter_path.write_bytes(b"%PDF-1.4 test cover letter")

    page = make_page()

    writer = PlaywrightFieldWriter(page)
    executor = BrowserFormExecutor(writer)

    field = make_field(
        field_id="cover_letter",
        label="Cover Letter",
        field_type=FormFieldType.FILE,
    )

    plan = make_plan(
        AuthorizedFieldAction(
            field=field,
            value=str(cover_letter_path),
        ),
        authorized_resume_path=str(cover_letter_path.resolve()),
    )

    result = executor.execute(
        plan,
        target_authorization=make_target_authorization(),
    )

    assert result.status == BrowserExecutionStatus.BLOCKED
    assert result.completed_actions == 0
    assert result.may_submit is False

    page.locator.assert_not_called()