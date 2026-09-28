from pathlib import Path

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
    desired_checked: bool | None = None,
) -> FieldPlan:
    return FieldPlan(
        field=field or make_field(),
        action=action,
        value=value,
        reason="Test field plan.",
        desired_checked=desired_checked,
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


def test_verified_radio_field_is_authorized():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="preferred_location",
        label="Preferred Location",
        field_type=FormFieldType.RADIO,
        options=[
            "Seattle",
            "New York",
        ],
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value="Seattle",
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert result.may_submit is False
    assert len(result.actions) == 1
    assert result.actions[0].field == field
    assert result.actions[0].value == "Seattle"


def test_file_field_is_authorized_for_controlled_execution():
    executor = ApplicationFormExecutor()

    field = make_field(
        "resume",
        "Resume",
        FormFieldType.FILE,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value="resume.pdf",
        )
    )

    result = executor.authorize(
        plan,
        authorized_resume_path="resume.pdf",
    )

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert result.may_submit is False
    assert len(result.actions) == 1

    assert result.actions[0].field == field
    assert result.actions[0].value == "resume.pdf"
    assert result.authorized_resume_path is not None


def test_empty_auto_fill_plan_is_authorized_but_cannot_submit():
    executor = ApplicationFormExecutor()

    plan = make_plan()

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert result.actions == ()
    assert result.may_submit is False


def test_file_action_carries_explicit_resume_authorization():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="resume",
        label="Resume",
        field_type=FormFieldType.FILE,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value="data/resumes/sde_resume.pdf",
        )
    )

    result = executor.authorize(
        plan,
        authorized_resume_path="data/resumes/sde_resume.pdf",
    )

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.authorized_resume_path == str(
        Path("data/resumes/sde_resume.pdf").resolve()
    )
    assert result.may_submit is False


def test_file_action_without_resume_authorization_is_blocked():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="resume",
        label="Resume",
        field_type=FormFieldType.FILE,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value="data/resumes/sde_resume.pdf",
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.actions == ()
    assert result.authorized_resume_path is None
    assert result.may_submit is False


def test_file_action_different_from_authorized_resume_is_blocked():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="resume",
        label="Resume",
        field_type=FormFieldType.FILE,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value="data/resumes/other_resume.pdf",
        )
    )

    result = executor.authorize(
        plan,
        authorized_resume_path="data/resumes/sde_resume.pdf",
    )

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.actions == ()
    assert result.authorized_resume_path is None
    assert result.may_submit is False

def test_safe_checkbox_with_explicit_true_intent_is_authorized():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="use_preferred_name",
        label=(
            "Use my verified preferred name on this application."
        ),
        field_type=FormFieldType.CHECKBOX,
        current_checked=False,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value=None,
            desired_checked=True,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert result.may_submit is False

    assert len(result.actions) == 1
    assert result.actions[0].field == field
    assert result.actions[0].value is None
    assert result.actions[0].desired_checked is True


def test_safe_checkbox_with_explicit_false_intent_is_authorized():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="use_phone",
        label=(
            "Use my verified phone number for application contact."
        ),
        field_type=FormFieldType.CHECKBOX,
        current_checked=True,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value=None,
            desired_checked=False,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert result.may_execute is True
    assert result.may_submit is False

    assert len(result.actions) == 1
    assert result.actions[0].field == field
    assert result.actions[0].value is None
    assert result.actions[0].desired_checked is False


def test_review_checkbox_semantics_are_blocked():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="unknown_checkbox",
        label="Include this information with my application.",
        field_type=FormFieldType.CHECKBOX,
        current_checked=False,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value=None,
            desired_checked=True,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.may_execute is False
    assert result.actions == ()
    assert result.may_submit is False


def test_blocked_checkbox_semantics_are_blocked():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="terms",
        label="I agree to the terms and conditions.",
        field_type=FormFieldType.CHECKBOX,
        current_checked=False,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value=None,
            desired_checked=True,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.may_execute is False
    assert result.actions == ()
    assert result.may_submit is False


def test_sensitive_checkbox_semantics_are_blocked():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="work_authorization",
        label=(
            "I am authorized to work in the United States."
        ),
        field_type=FormFieldType.CHECKBOX,
        current_checked=False,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value=None,
            desired_checked=True,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.may_execute is False
    assert result.actions == ()
    assert result.may_submit is False

def test_authorized_string_action_defaults_to_no_checkbox_intent():
    executor = ApplicationFormExecutor()

    result = executor.authorize(
        make_plan(
            make_field_plan(
                value="Test",
            )
        )
    )

    assert result.status == ExecutionPlanStatus.AUTHORIZED
    assert len(result.actions) == 1
    assert result.actions[0].value == "Test"
    assert result.actions[0].desired_checked is None


def test_non_checkbox_field_with_checkbox_intent_is_blocked():
    executor = ApplicationFormExecutor()

    plan = make_plan(
        make_field_plan(
            field=make_field(
                "first_name",
                "First Name",
                FormFieldType.TEXT,
            ),
            value="Test",
            desired_checked=True,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.may_execute is False
    assert result.actions == ()
    assert result.may_submit is False


def test_checkbox_with_string_value_and_boolean_intent_is_blocked():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="ordinary_checkbox",
        label="Ordinary Checkbox",
        field_type=FormFieldType.CHECKBOX,
        current_checked=False,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value="true",
            desired_checked=True,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.may_execute is False
    assert result.actions == ()
    assert result.may_submit is False


def test_safe_checkbox_without_explicit_boolean_intent_is_blocked():
    executor = ApplicationFormExecutor()

    field = FormField(
        field_id="use_preferred_name",
        label=(
            "Use my verified preferred name on this application."
        ),
        field_type=FormFieldType.CHECKBOX,
        current_checked=False,
    )

    plan = make_plan(
        make_field_plan(
            field=field,
            value=None,
            desired_checked=None,
        )
    )

    result = executor.authorize(plan)

    assert result.status == ExecutionPlanStatus.BLOCKED
    assert result.may_execute is False
    assert result.actions == ()
    assert result.may_submit is False
