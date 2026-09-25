import pytest

from app.applications.answer_resolver import (
    AnswerStatus,
    ApplicationAnswerResolver,
)
from app.applications.form_analyzer import (
    ApplicationFormAnalyzer,
    FormSafetyStatus,
)
from app.applications.form_models import (
    ApplicationForm,
    FormField,
    FormFieldType,
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
            "full_name": "Test Candidate",
            "email": "test@example.com",
            "phone": "555-0100",
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


def test_all_verified_safe_fields_are_auto_answerable(
    analyzer,
):
    form = make_form(
        make_field(
            "first_name",
            "First Name",
        ),
        make_field(
            "last_name",
            "Last Name",
        ),
        make_field(
            "email",
            "Email",
            FormFieldType.EMAIL,
        ),
    )

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.AUTO_ANSWERABLE
    )
    assert result.can_auto_fill is True

    assert all(
        field.can_auto_answer
        for field in result.fields
    )

    assert [
        field.resolution.answer
        for field in result.fields
    ] == [
        "Test",
        "Candidate",
        "test@example.com",
    ]


def test_missing_verified_safe_answer_requires_review(
    analyzer,
):
    form = make_form(
        make_field(
            "github",
            "GitHub",
        ),
    )

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.NEEDS_REVIEW
    )
    assert result.can_auto_fill is False

    assert (
        result.fields[0].resolution.status
        == AnswerStatus.NEEDS_REVIEW
    )
    assert result.fields[0].resolution.answer is None


def test_open_ended_question_requires_review(
    analyzer,
):
    form = make_form(
        make_field(
            "why_company",
            "Why do you want to work at this company?",
            FormFieldType.TEXTAREA,
        ),
    )

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.NEEDS_REVIEW
    )

    assert (
        result.fields[0].resolution.status
        == AnswerStatus.NEEDS_REVIEW
    )


@pytest.mark.parametrize(
    "label",
    [
        "Are you authorized to work in the United States?",
        "Will you now or in the future require sponsorship?",
        "What is your citizenship status?",
        "Do you have a disability?",
        "What is your veteran status?",
        "Have you ever been convicted of a crime?",
    ],
)
def test_sensitive_question_requires_manual_handling(
    analyzer,
    label,
):
    form = make_form(
        make_field(
            "sensitive",
            label,
        ),
    )

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.MANUAL_REQUIRED
    )
    assert result.can_auto_fill is False

    assert (
        result.fields[0].resolution.status
        == AnswerStatus.SENSITIVE
    )
    assert result.fields[0].resolution.answer is None


@pytest.mark.parametrize(
    "label",
    [
        "Type your signature",
        "I certify that the information above is correct",
        "I attest that the information provided is accurate",
        "Complete the CAPTCHA",
        "Confirm that you are not a robot",
    ],
)
def test_manual_question_requires_manual_handling(
    analyzer,
    label,
):
    form = make_form(
        make_field(
            "manual",
            label,
        ),
    )

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.MANUAL_REQUIRED
    )

    assert (
        result.fields[0].resolution.status
        == AnswerStatus.MANUAL
    )
    assert result.fields[0].resolution.answer is None


def test_sensitive_field_overrides_review_field(
    analyzer,
):
    form = make_form(
        make_field(
            "why_company",
            "Why do you want to work here?",
        ),
        make_field(
            "sponsorship",
            "Will you require sponsorship?",
        ),
    )

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.MANUAL_REQUIRED
    )


def test_field_id_cannot_override_human_visible_question(
    analyzer,
):
    form = make_form(
        make_field(
            "email",
            "Why should we contact you at this email?",
        ),
    )

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.NEEDS_REVIEW
    )

    assert (
        result.fields[0].resolution.status
        == AnswerStatus.NEEDS_REVIEW
    )

    assert result.fields[0].resolution.answer is None


def test_sensitive_label_with_safe_field_id_is_not_auto_answered(
    analyzer,
):
    form = make_form(
        make_field(
            "state",
            "What is your citizenship status?",
        ),
    )

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.MANUAL_REQUIRED
    )

    assert (
        result.fields[0].resolution.status
        == AnswerStatus.SENSITIVE
    )

    assert result.fields[0].resolution.answer is None


def test_empty_form_is_auto_answerable(
    analyzer,
):
    form = make_form()

    result = analyzer.analyze(form)

    assert (
        result.status
        == FormSafetyStatus.AUTO_ANSWERABLE
    )
    assert result.can_auto_fill is True
    assert result.fields == ()