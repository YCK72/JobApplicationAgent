import pytest

from app.applications.external_field_policy import (
    ExternalFieldExecutionPolicy,
    ExternalFieldPolicyStatus,
)
from app.applications.form_executor import AuthorizedFieldAction
from app.applications.form_models import (
    FormField,
    FormFieldType,
)


def make_action(
    label: str,
    *,
    field_type: FormFieldType = FormFieldType.TEXT,
    value: str | None = "Verified Value",
    desired_checked: bool | None = None,
) -> AuthorizedFieldAction:
    return AuthorizedFieldAction(
        field=FormField(
            field_id="test_field",
            label=label,
            field_type=field_type,
        ),
        value=value,
        desired_checked=desired_checked,
    )


@pytest.fixture
def policy() -> ExternalFieldExecutionPolicy:
    return ExternalFieldExecutionPolicy()


@pytest.mark.parametrize(
    ("label", "field_type"),
    [
        ("First Name", FormFieldType.TEXT),
        ("Last Name", FormFieldType.TEXT),
        ("Full Name", FormFieldType.TEXT),
        ("Preferred Name", FormFieldType.TEXT),
        ("Email", FormFieldType.EMAIL),
        ("Phone", FormFieldType.PHONE),
        ("LinkedIn", FormFieldType.TEXT),
        ("GitHub", FormFieldType.TEXT),
        ("Portfolio URL", FormFieldType.TEXT),
        ("Personal Website", FormFieldType.TEXT),
        ("Address", FormFieldType.TEXTAREA),
        ("City", FormFieldType.TEXT),
        ("State", FormFieldType.TEXT),
        ("Zip Code", FormFieldType.TEXT),
    ],
)
def test_safe_verified_profile_field_is_allowed(
    policy: ExternalFieldExecutionPolicy,
    label: str,
    field_type: FormFieldType,
):
    result = policy.authorize(
        make_action(
            label,
            field_type=field_type,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.ALLOWED
    assert result.may_mutate is True
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Are you authorized to work in the United States?",
        "Will you now or in the future require sponsorship?",
        "What is your visa status?",
        "What is your citizenship?",
        "Are you a permanent resident?",
        "What is your race?",
        "What is your ethnicity?",
        "Are you Hispanic/Latino?",
        "Are you Hispanic or Latino?",
        "What is your gender?",
        "What is your sex?",
        "What is your sexual orientation?",
        "Do you have a disability?",
        "What is your veteran status?",
        "Have you ever been convicted of a crime?",
        "Do you consent to a background check?",
        "Do you have any conflicts of interest?",
    ],
)
def test_sensitive_field_is_blocked(
    policy: ExternalFieldExecutionPolicy,
    label: str,
):
    result = policy.authorize(
        make_action(label)
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Electronic Signature",
        "Please certify that this information is correct",
        "Please attest that the information above is accurate",
        "CAPTCHA",
        "Human Verification",
        "I am not a robot",
    ],
)
def test_manual_or_verification_field_is_blocked(
    policy: ExternalFieldExecutionPolicy,
    label: str,
):
    result = policy.authorize(
        make_action(label)
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Why are you interested in this role?",
        "Describe your experience",
        "Tell us about yourself",
        "Cover Letter",
        "Additional Information",
        "Anything Else?",
        "Desired Salary",
        "Expected Compensation",
        "Earliest Start Date",
        "Are you willing to relocate?",
        "How did you hear about us?",
    ],
)
def test_review_or_unknown_field_is_blocked(
    policy: ExternalFieldExecutionPolicy,
    label: str,
):
    result = policy.authorize(
        make_action(label)
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "field_type",
    [
        FormFieldType.UNKNOWN,
    ],
)
def test_unsupported_control_type_is_blocked(
    policy: ExternalFieldExecutionPolicy,
    field_type: FormFieldType,
):
    result = policy.authorize(
        make_action(
            "First Name",
            field_type=field_type,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False

def test_safe_checkbox_with_true_intent_is_allowed():
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            "Use my verified preferred name on this application.",
            field_type=FormFieldType.CHECKBOX,
            value=None,
            desired_checked=True,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.ALLOWED
    assert result.may_mutate is True
    assert result.may_submit is False


def test_safe_checkbox_with_false_intent_is_allowed():
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            "Use my verified phone number for application contact.",
            field_type=FormFieldType.CHECKBOX,
            value=None,
            desired_checked=False,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.ALLOWED
    assert result.may_mutate is True
    assert result.may_submit is False


def test_safe_checkbox_without_explicit_boolean_intent_is_blocked():
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            "Use my verified preferred name on this application.",
            field_type=FormFieldType.CHECKBOX,
            value=None,
            desired_checked=None,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


def test_checkbox_with_string_value_is_blocked():
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            "Use my verified preferred name on this application.",
            field_type=FormFieldType.CHECKBOX,
            value="true",
            desired_checked=True,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "I agree to the terms and conditions.",
        "I consent to receive recruiting communications.",
        "I certify that this information is correct.",
        "I am authorized to work in the United States.",
        "I will require visa sponsorship.",
        "I am a United States citizen.",
        "I identify as Hispanic or Latino.",
        "I have a disability.",
        "I am a veteran.",
        "I have been convicted of a crime.",
        "I have a conflict of interest.",
    ],
)
def test_blocked_checkbox_semantics_remain_blocked(
    label: str,
):
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            label,
            field_type=FormFieldType.CHECKBOX,
            value=None,
            desired_checked=True,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Confirm",
        "Yes",
        "No",
        "Checkbox",
        "Select this option",
        "Include this information with my application.",
    ],
)
def test_review_or_ambiguous_checkbox_remains_blocked(
    label: str,
):
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            label,
            field_type=FormFieldType.CHECKBOX,
            value=None,
            desired_checked=False,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


def test_safe_radio_field_is_allowed():
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            "Country",
            field_type=FormFieldType.RADIO,
            value="United States",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.ALLOWED
    assert result.may_mutate is True
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Are you authorized to work in the United States?",
        "Will you now or in the future require sponsorship?",
        "What is your visa status?",
        "What is your citizenship?",
        "What is your gender?",
        "What is your race?",
        "What is your ethnicity?",
        "Are you Hispanic/Latino?",
        "Do you have a disability?",
        "What is your veteran status?",
    ],
)
def test_sensitive_radio_remains_blocked(
    label: str,
):
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            label,
            field_type=FormFieldType.RADIO,
            value="Forged Value",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Electronic Signature",
        "Please certify that this information is correct",
        "Please attest that the information above is accurate",
        "Terms and Conditions",
        "CAPTCHA",
        "Human Verification",
    ],
)
def test_manual_radio_remains_blocked(
    label: str,
):
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            label,
            field_type=FormFieldType.RADIO,
            value="Forged Value",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Preferred Location",
        "Are you willing to relocate?",
        "How did you hear about us?",
        "Favorite programming language",
    ],
)
def test_review_or_unknown_radio_remains_blocked(
    label: str,
):
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            label,
            field_type=FormFieldType.RADIO,
            value="Forged Value",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
    ],
)
def test_empty_value_is_blocked(
    policy: ExternalFieldExecutionPolicy,
    value: str,
):
    result = policy.authorize(
        make_action(
            "First Name",
            value=value,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False


def test_unknown_field_fails_closed(
    policy: ExternalFieldExecutionPolicy,
):
    result = policy.authorize(
        make_action("Favorite programming language")
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


def test_safe_field_id_cannot_bypass_sensitive_label(
    policy: ExternalFieldExecutionPolicy,
):
    action = AuthorizedFieldAction(
        field=FormField(
            field_id="first_name",
            label="Will you require visa sponsorship?",
            field_type=FormFieldType.TEXT,
        ),
        value="Verified Value",
    )

    result = policy.authorize(action)

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False


def test_sensitive_field_id_cannot_override_safe_label(
    policy: ExternalFieldExecutionPolicy,
):
    action = AuthorizedFieldAction(
        field=FormField(
            field_id="visa_status",
            label="First Name",
            field_type=FormFieldType.TEXT,
        ),
        value="Verified Value",
    )

    result = policy.authorize(action)

    assert result.status == ExternalFieldPolicyStatus.ALLOWED
    assert result.may_mutate is True


def test_authorization_never_allows_submission(
    policy: ExternalFieldExecutionPolicy,
):
    result = policy.authorize(
        make_action("First Name")
    )

    assert result.status == ExternalFieldPolicyStatus.ALLOWED
    assert result.may_submit is False


def test_safe_country_select_is_allowed():
    result = ExternalFieldExecutionPolicy().authorize(
        make_action(
            "Country",
            field_type=FormFieldType.SELECT,
            value="United States",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.ALLOWED
    assert result.may_mutate is True
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Country of citizenship",
        "What is your citizenship?",
        "Are you authorized to work in the United States?",
        "Will you now or in the future require sponsorship?",
        "What is your visa status?",
        "What is your gender?",
        "What is your race?",
        "What is your ethnicity?",
        "Are you Hispanic/Latino?",
        "Do you have a disability?",
        "What is your veteran status?",
    ],
)
def test_sensitive_select_remains_blocked(
    policy: ExternalFieldExecutionPolicy,
    label: str,
):
    result = policy.authorize(
        make_action(
            label,
            field_type=FormFieldType.SELECT,
            value="Forged Value",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Working location",
        "Preferred location",
        "Preferred working location",
        "Are you willing to relocate?",
        "Favorite programming language",
    ],
)
def test_review_or_unknown_select_remains_blocked(
    policy: ExternalFieldExecutionPolicy,
    label: str,
):
    result = policy.authorize(
        make_action(
            label,
            field_type=FormFieldType.SELECT,
            value="Forged Value",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Resume",
        "resume",
        "  Resume  ",
        "CV",
        "cv",
        "Curriculum Vitae",
        "  curriculum   vitae  ",
    ],
)
def test_explicit_resume_file_field_is_allowed(
    policy: ExternalFieldExecutionPolicy,
    label: str,
):
    result = policy.authorize(
        make_action(
            label,
            field_type=FormFieldType.FILE,
            value="C:/verified/resume.pdf",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.ALLOWED
    assert result.may_mutate is True
    assert result.may_submit is False


@pytest.mark.parametrize(
    "label",
    [
        "Cover Letter",
        "Transcript",
        "Supporting Document",
        "Additional Document",
        "Portfolio",
        "Attachment",
        "Upload",
        "Attach",
        "Resume Upload",
        "Upload Resume",
        "Resume/Cover Letter",
        "Supporting Resume Document",
        "First Name",
    ],
)
def test_non_resume_file_field_remains_blocked(
    policy: ExternalFieldExecutionPolicy,
    label: str,
):
    result = policy.authorize(
        make_action(
            label,
            field_type=FormFieldType.FILE,
            value="C:/verified/resume.pdf",
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
    ],
)
def test_resume_file_with_empty_value_is_blocked(
    policy: ExternalFieldExecutionPolicy,
    value: str,
):
    result = policy.authorize(
        make_action(
            "Resume",
            field_type=FormFieldType.FILE,
            value=value,
        )
    )

    assert result.status == ExternalFieldPolicyStatus.BLOCKED
    assert result.may_mutate is False
    assert result.may_submit is False