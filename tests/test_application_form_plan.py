import pytest

from app.applications.answer_resolver import (
    ApplicationAnswerResolver,
)
from app.applications.form_analyzer import (
    ApplicationFormAnalyzer,
)
from app.applications.form_models import (
    ApplicationForm,
    FormField,
    FormFieldType,
)
from app.applications.form_plan import (
    ApplicationFormPlanner,
    FieldAction,
    FieldPlan,
    FormPlanStatus,
)
from app.applications.question_policy import (
    ApplicationQuestionPolicy,
)


@pytest.fixture
def resolver():
    return ApplicationAnswerResolver(
        verified_answers={
            "first_name": "Test",
            "last_name": "Candidate",
            "email": "test@example.com",
            "city": "Seattle",
            "state": "Washington",
        },
        question_policy=ApplicationQuestionPolicy(),
    )


@pytest.fixture
def analyzer(resolver):
    return ApplicationFormAnalyzer(
        answer_resolver=resolver
    )


@pytest.fixture
def planner():
    return ApplicationFormPlanner()


def make_form(*fields):
    return ApplicationForm(
        provider="Test ATS",
        job_url="https://example.com/jobs/123",
        fields=list(fields),
    )


def make_field(
    field_id,
    label,
    field_type=FormFieldType.TEXT,
):
    return FormField(
        field_id=field_id,
        label=label,
        field_type=field_type,
    )


def analyze_and_plan(
    analyzer,
    planner,
    form,
):
    analysis = analyzer.analyze(form)

    return planner.build_plan(analysis)


def test_verified_fields_produce_fill_actions(
    analyzer,
    planner,
):
    form = make_form(
        make_field(
            "first_name",
            "First Name",
        ),
        make_field(
            "email",
            "Email",
            FormFieldType.EMAIL,
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.AUTO_FILL_ALLOWED
    )
    assert plan.may_auto_fill is True
    assert plan.may_submit is False

    assert len(plan.fields) == 2

    assert (
        plan.fields[0].action
        == FieldAction.FILL_VERIFIED
    )
    assert plan.fields[0].value == "Test"
    assert plan.fields[0].may_fill is True

    assert (
        plan.fields[1].action
        == FieldAction.FILL_VERIFIED
    )
    assert plan.fields[1].value == "test@example.com"
    assert plan.fields[1].may_fill is True


def test_missing_verified_answer_is_skipped_for_review(
    analyzer,
    planner,
):
    form = make_form(
        make_field(
            "github",
            "GitHub",
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.REVIEW_REQUIRED
    )
    assert plan.may_auto_fill is False
    assert plan.may_submit is False

    assert (
        plan.fields[0].action
        == FieldAction.SKIP_REVIEW
    )
    assert plan.fields[0].value is None
    assert plan.fields[0].may_fill is False


def test_open_ended_question_is_skipped_for_review(
    analyzer,
    planner,
):
    form = make_form(
        make_field(
            "why_company",
            "Why do you want to work at this company?",
            FormFieldType.TEXTAREA,
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.REVIEW_REQUIRED
    )

    assert (
        plan.fields[0].action
        == FieldAction.SKIP_REVIEW
    )
    assert plan.fields[0].value is None


@pytest.mark.parametrize(
    "label",
    [
        "Are you authorized to work in the United States?",
        "Will you now or in the future require sponsorship?",
        "What is your citizenship status?",
        "Do you have a disability?",
        "What is your veteran status?",
    ],
)
def test_sensitive_fields_are_never_fill_actions(
    analyzer,
    planner,
    label,
):
    form = make_form(
        make_field(
            "sensitive",
            label,
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.MANUAL_REQUIRED
    )
    assert plan.may_auto_fill is False
    assert plan.may_submit is False

    assert (
        plan.fields[0].action
        == FieldAction.SKIP_MANUAL
    )
    assert plan.fields[0].value is None
    assert plan.fields[0].may_fill is False


@pytest.mark.parametrize(
    "label",
    [
        "Type your signature",
        "I certify that the information above is correct",
        "Complete the CAPTCHA",
        "Confirm that you are not a robot",
    ],
)
def test_manual_fields_are_never_fill_actions(
    analyzer,
    planner,
    label,
):
    form = make_form(
        make_field(
            "manual",
            label,
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.MANUAL_REQUIRED
    )

    assert (
        plan.fields[0].action
        == FieldAction.SKIP_MANUAL
    )
    assert plan.fields[0].value is None


def test_mixed_safe_and_review_form_blocks_auto_fill(
    analyzer,
    planner,
):
    form = make_form(
        make_field(
            "first_name",
            "First Name",
        ),
        make_field(
            "why_company",
            "Why do you want to work here?",
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.REVIEW_REQUIRED
    )
    assert plan.may_auto_fill is False

    assert (
        plan.fields[0].action
        == FieldAction.FILL_VERIFIED
    )
    assert plan.fields[0].value == "Test"

    assert (
        plan.fields[1].action
        == FieldAction.SKIP_REVIEW
    )
    assert plan.fields[1].value is None


def test_sensitive_field_escalates_entire_plan_to_manual(
    analyzer,
    planner,
):
    form = make_form(
        make_field(
            "first_name",
            "First Name",
        ),
        make_field(
            "sponsorship",
            "Will you require sponsorship?",
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.MANUAL_REQUIRED
    )
    assert plan.may_auto_fill is False

    assert (
        plan.fields[0].action
        == FieldAction.FILL_VERIFIED
    )

    assert (
        plan.fields[1].action
        == FieldAction.SKIP_MANUAL
    )


def test_safe_field_id_cannot_bypass_question_policy(
    analyzer,
    planner,
):
    form = make_form(
        make_field(
            "email",
            "Why should we contact you at this email?",
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.REVIEW_REQUIRED
    )

    assert (
        plan.fields[0].action
        == FieldAction.SKIP_REVIEW
    )
    assert plan.fields[0].value is None


def test_empty_form_never_authorizes_submission(
    analyzer,
    planner,
):
    form = make_form()

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.AUTO_FILL_ALLOWED
    )
    assert plan.fields == ()
    assert plan.may_auto_fill is True

    # Form analysis/filling and application submission are
    # intentionally separate permissions.
    assert plan.may_submit is False

def test_resolved_select_option_is_preserved_in_plan():
    resolver = ApplicationAnswerResolver(
        verified_answers={
            "country": "United States",
        },
        question_policy=ApplicationQuestionPolicy(),
    )

    analyzer = ApplicationFormAnalyzer(
        answer_resolver=resolver
    )

    planner = ApplicationFormPlanner()

    form = make_form(
        FormField(
            field_id="country",
            label="Country",
            field_type=FormFieldType.SELECT,
            options=[
                "Select...",
                "United States",
                "Canada",
            ],
        ),
    )

    plan = analyze_and_plan(
        analyzer,
        planner,
        form,
    )

    assert (
        plan.status
        == FormPlanStatus.AUTO_FILL_ALLOWED
    )

    assert len(plan.fields) == 1
    assert (
        plan.fields[0].action
        == FieldAction.FILL_VERIFIED
    )
    assert plan.fields[0].value == "United States"

    # Planning a deterministic answer is not browser authorization.
    assert plan.may_submit is False

def test_field_plan_defaults_to_no_checkbox_intent():
    field = make_field(
        "first_name",
        "First Name",
    )

    field_plan = FieldPlan(
        field=field,
        action=FieldAction.FILL_VERIFIED,
        value="Test",
        reason="Verified ordinary profile field.",
    )

    assert field_plan.value == "Test"
    assert field_plan.desired_checked is None
    assert field_plan.may_fill is True


def test_field_plan_can_preserve_explicit_checked_intent():
    field = make_field(
        "ordinary_checkbox",
        "Ordinary Checkbox",
        FormFieldType.CHECKBOX,
    )

    field_plan = FieldPlan(
        field=field,
        action=FieldAction.FILL_VERIFIED,
        value=None,
        reason="Explicit test checkbox intent.",
        desired_checked=True,
    )

    assert field_plan.value is None
    assert field_plan.desired_checked is True


def test_field_plan_can_preserve_explicit_unchecked_intent():
    field = make_field(
        "ordinary_checkbox",
        "Ordinary Checkbox",
        FormFieldType.CHECKBOX,
    )

    field_plan = FieldPlan(
        field=field,
        action=FieldAction.FILL_VERIFIED,
        value=None,
        reason="Explicit test checkbox intent.",
        desired_checked=False,
    )

    assert field_plan.value is None
    assert field_plan.desired_checked is False

def test_checkbox_intent_is_not_considered_string_fillable():
    field = make_field(
        "ordinary_checkbox",
        "Ordinary Checkbox",
        FormFieldType.CHECKBOX,
    )

    field_plan = FieldPlan(
        field=field,
        action=FieldAction.FILL_VERIFIED,
        value=None,
        reason="Explicit test checkbox intent.",
        desired_checked=True,
    )

    assert field_plan.may_fill is False


def test_ordinary_string_plan_has_no_checkbox_intent():
    field = make_field(
        "first_name",
        "First Name",
        FormFieldType.TEXT,
    )

    field_plan = FieldPlan(
        field=field,
        action=FieldAction.FILL_VERIFIED,
        value="Test",
        reason="Verified ordinary profile field.",
    )

    assert field_plan.may_fill is True
    assert field_plan.desired_checked is None