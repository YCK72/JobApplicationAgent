from app.applications.dry_run import (
    ApplicationDryRunReporter,
    DryRunFieldStatus,
)
from app.applications.form_executor import ExecutionPlanStatus
from app.applications.form_models import (
    ApplicationForm,
    FormField,
    FormFieldType,
)
from app.applications.form_plan import (
    FieldAction,
    FieldPlan,
    FormAnswerPlan,
    FormPlanStatus,
)


JOB_URL = "https://job-boards.greenhouse.io/example/jobs/123"


def make_field(
    field_id: str,
    label: str,
    field_type: FormFieldType = FormFieldType.TEXT,
    *,
    required: bool = True,
) -> FormField:
    return FormField(
        field_id=field_id,
        label=label,
        field_type=field_type,
        required=required,
    )


def make_fill(
    field: FormField,
    value: str,
) -> FieldPlan:
    return FieldPlan(
        field=field,
        action=FieldAction.FILL_VERIFIED,
        value=value,
        reason="Resolved from verified candidate data.",
    )


def make_form(
    *fields: FormField,
) -> ApplicationForm:
    return ApplicationForm(
        provider="greenhouse",
        job_url=JOB_URL,
        fields=tuple(fields),
    )


def test_safe_verified_form_reports_would_fill():
    first_name = make_field(
        "first_name",
        "First Name",
    )
    email = make_field(
        "email",
        "Email",
        FormFieldType.EMAIL,
    )

    form = make_form(first_name, email)

    plan = FormAnswerPlan(
        fields=(
            make_fill(first_name, "Verified Name"),
            make_fill(email, "verified@example.com"),
        ),
        status=FormPlanStatus.AUTO_FILL_ALLOWED,
        reason="All fields have verified answers.",
    )

    report = ApplicationDryRunReporter().build_report(
        form,
        plan,
    )

    assert report.execution_status == ExecutionPlanStatus.AUTHORIZED
    assert report.would_execute is True
    assert report.may_submit is False
    assert report.would_fill_count == 2

    assert [field.status for field in report.fields] == [
        DryRunFieldStatus.WOULD_FILL,
        DryRunFieldStatus.WOULD_FILL,
    ]


def test_manual_form_remains_whole_form_blocked():
    first_name = make_field(
        "first_name",
        "First Name",
    )
    sponsorship = make_field(
        "sponsorship",
        "Will you require visa sponsorship?",
    )

    form = make_form(first_name, sponsorship)

    plan = FormAnswerPlan(
        fields=(
            make_fill(first_name, "Verified Name"),
            FieldPlan(
                field=sponsorship,
                action=FieldAction.SKIP_MANUAL,
                value=None,
                reason="Sensitive field requires manual handling.",
            ),
        ),
        status=FormPlanStatus.MANUAL_REQUIRED,
        reason="Manual handling required.",
    )

    report = ApplicationDryRunReporter().build_report(
        form,
        plan,
    )

    assert report.execution_status == ExecutionPlanStatus.BLOCKED
    assert report.would_execute is False
    assert report.may_submit is False

    assert report.fields[0].status == DryRunFieldStatus.WOULD_FILL
    assert report.fields[1].status == DryRunFieldStatus.MANUAL_REQUIRED

    # Diagnostic WOULD_FILL must not override whole-form blocking.
    assert report.would_fill_count == 1


def test_review_field_is_reported_without_value():
    field = make_field(
        "why_company",
        "Why are you interested in this role?",
        FormFieldType.TEXTAREA,
    )

    form = make_form(field)

    plan = FormAnswerPlan(
        fields=(
            FieldPlan(
                field=field,
                action=FieldAction.SKIP_REVIEW,
                value=None,
                reason="Question requires human review.",
            ),
        ),
        status=FormPlanStatus.REVIEW_REQUIRED,
        reason="Human review required.",
    )

    report = ApplicationDryRunReporter().build_report(
        form,
        plan,
    )

    result = report.fields[0]

    assert result.status == DryRunFieldStatus.REVIEW_REQUIRED
    assert result.value is None
    assert report.would_execute is False
    assert report.may_submit is False


def test_forged_sensitive_fill_is_blocked_by_external_policy():
    field = make_field(
        "sponsorship",
        "Will you require visa sponsorship?",
    )

    form = make_form(field)

    plan = FormAnswerPlan(
        fields=(
            make_fill(
                field,
                "Forged Value",
            ),
        ),
        status=FormPlanStatus.AUTO_FILL_ALLOWED,
        reason="Forged plan.",
    )

    report = ApplicationDryRunReporter().build_report(
        form,
        plan,
    )

    # The generic form executor sees a supported verified-fill shape,
    # but the external semantic policy independently blocks the field.
    assert report.execution_status == ExecutionPlanStatus.AUTHORIZED
    assert report.fields[0].status == (
        DryRunFieldStatus.BLOCKED_EXTERNAL_POLICY
    )
    assert report.fields[0].value is None
    assert report.would_fill_count == 0
    assert report.may_submit is False


def test_unsupported_control_never_reports_would_fill():
    field = make_field(
        "country",
        "Country",
        FormFieldType.SELECT,
    )

    form = make_form(field)

    plan = FormAnswerPlan(
        fields=(
            make_fill(field, "United States"),
        ),
        status=FormPlanStatus.AUTO_FILL_ALLOWED,
        reason="Test plan.",
    )

    report = ApplicationDryRunReporter().build_report(
        form,
        plan,
    )

    assert report.execution_status == ExecutionPlanStatus.BLOCKED
    assert report.fields[0].status == (
        DryRunFieldStatus.BLOCKED_EXTERNAL_POLICY
    )
    assert report.would_fill_count == 0
    assert report.may_submit is False


def test_report_preserves_form_identity():
    field = make_field(
        "first_name",
        "First Name",
    )

    form = make_form(field)

    plan = FormAnswerPlan(
        fields=(
            make_fill(field, "Verified Name"),
        ),
        status=FormPlanStatus.AUTO_FILL_ALLOWED,
        reason="Verified.",
    )

    report = ApplicationDryRunReporter().build_report(
        form,
        plan,
    )

    assert report.provider == "greenhouse"
    assert report.job_url == JOB_URL


def test_report_never_authorizes_submission():
    field = make_field(
        "first_name",
        "First Name",
    )

    report = ApplicationDryRunReporter().build_report(
        make_form(field),
        FormAnswerPlan(
            fields=(
                make_fill(field, "Verified Name"),
            ),
            status=FormPlanStatus.AUTO_FILL_ALLOWED,
            reason="Verified.",
        ),
    )

    assert report.may_submit is False