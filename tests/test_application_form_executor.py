from app.applications.form_executor import (
    ApplicationFormExecutor,
    ExecutionPlanStatus,
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


def make_field_plan(
    *,
    field: FormField | None = None,
    action: FieldAction = FieldAction.FILL_VERIFIED,
    value: str | None = "Test",
) -> FieldPlan:
    return FieldPlan(
        field=field or make_field(),
        action=action,
        value=value,
        reason="Test field plan.",
    )


def make_plan(
    *field_plans: FieldPlan,
    status: FormPlanStatus = FormPlanStatus.AUTO_FILL_ALLOWED,
) -> FormAnswerPlan:
    return FormAnswerPlan(
        fields=tuple(field_plans),
        status=status,
        reason="Test form plan.",
    )


def test_verified_text_field_is_authorized():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan()
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert result.may_submit is False

    assert len(result.actions) == 1
    assert result.actions[0].field.field_id == "first_name"
    assert result.actions[0].value == "Test"


def test_multiple_supported_fields_are_authorized():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan(
            field=make_field(
                "first_name",
                "First Name",
                FormFieldType.TEXT,
            ),
            value="Test",
        ),
        make_field_plan(
            field=make_field(
                "email",
                "Email",
                FormFieldType.EMAIL,
            ),
            value="test@example.com",
        ),
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert len(result.actions) == 2


def test_review_plan_is_blocked():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan(),
        status=FormPlanStatus.REVIEW_REQUIRED,
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.may_execute is False
    assert result.actions == ()
    assert result.may_submit is False


def test_manual_plan_is_blocked():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan(),
        status=FormPlanStatus.MANUAL_REQUIRED,
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.may_execute is False
    assert result.actions == ()


def test_skip_review_field_blocks_entire_execution():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan(
            action=FieldAction.SKIP_REVIEW,
            value=None,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.actions == ()


def test_skip_manual_field_blocks_entire_execution():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan(
            action=FieldAction.SKIP_MANUAL,
            value=None,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.actions == ()


def test_missing_verified_value_is_blocked():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan(
            action=FieldAction.FILL_VERIFIED,
            value=None,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.actions == ()


def test_verified_select_field_is_authorized():
    executor = ApplicationFormExecutor()

    field = make_field(
        "country",
        "Country",
        FormFieldType.SELECT,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value="United States",
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert result.may_submit is False

    assert len(result.actions) == 1
    assert result.actions[0].field == field
    assert result.actions[0].value == "United States"


def test_file_field_is_never_authorized_by_current_executor():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan(
            field=make_field(
                "resume",
                "Resume",
                FormFieldType.FILE,
            ),
            value="resume.pdf",
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.actions == ()


def test_empty_auto_fill_plan_is_authorized_but_cannot_submit():
    executor = ApplicationFormExecutor()

    plan = make_plan()

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert result.actions == ()
    assert result.may_submit is False