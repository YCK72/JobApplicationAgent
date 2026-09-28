import pytest

from app.applications.checkbox_policy import (
    ApplicationCheckboxPolicy,
    CheckboxPolicy,
)


@pytest.fixture
def policy():
    return ApplicationCheckboxPolicy()


@pytest.mark.parametrize(
    "label",
    [
        "I certify that the information provided is accurate.",
        "I attest that the information above is correct.",
        "I agree to the terms and conditions.",
        "I accept the terms and conditions.",
        "I acknowledge the privacy policy.",
        "I agree to the privacy policy.",
        "I consent to the processing of my personal data.",
        "I consent to receive text messages.",
    ],
)
def test_consent_certification_and_acknowledgement_are_blocked(
    policy,
    label,
):
    result = policy.classify(label)

    assert result.policy == CheckboxPolicy.BLOCKED


@pytest.mark.parametrize(
    "label",
    [
        "Subscribe me to recruiting updates.",
        "Sign me up for job alerts.",
        "Send me marketing communications.",
        "Email me about future opportunities.",
        "Receive recruiting newsletters.",
        "Remember my information for future applications.",
    ],
)
def test_optional_marketing_and_persistence_opt_ins_are_blocked(
    policy,
    label,
):
    result = policy.classify(label)

    assert result.policy == CheckboxPolicy.BLOCKED


@pytest.mark.parametrize(
    "label",
    [
        "I am authorized to work in the United States.",
        "I require visa sponsorship.",
        "I am a United States citizen.",
        "I am a permanent resident.",
        "I identify as Hispanic or Latino.",
        "I have a disability.",
        "I am a veteran.",
        "I have been convicted of a crime.",
        "I have a conflict of interest.",
    ],
)
def test_sensitive_checkbox_questions_are_blocked(
    policy,
    label,
):
    result = policy.classify(label)

    assert result.policy == CheckboxPolicy.BLOCKED


@pytest.mark.parametrize(
    "label",
    [
        "",
        " ",
        "Confirm",
        "Yes",
        "No",
        "Option 1",
        "Checkbox",
        "Select this option",
    ],
)
def test_ambiguous_checkbox_labels_require_review(
    policy,
    label,
):
    result = policy.classify(label)

    assert result.policy == CheckboxPolicy.REVIEW


@pytest.mark.parametrize(
    "label",
    [
        "Use my verified preferred name on this application.",
        "Use my verified phone number for application contact.",
    ],
)
def test_narrow_non_sensitive_checkbox_semantics_can_be_safe(
    policy,
    label,
):
    result = policy.classify(label)

    assert result.policy == CheckboxPolicy.SAFE


def test_unknown_checkbox_defaults_to_review(
    policy,
):
    result = policy.classify(
        "Include this information with my application."
    )

    assert result.policy == CheckboxPolicy.REVIEW


def test_matching_is_case_insensitive(
    policy,
):
    result = policy.classify(
        "I AGREE TO THE TERMS AND CONDITIONS."
    )

    assert result.policy == CheckboxPolicy.BLOCKED


def test_blocked_semantics_take_priority_over_safe_language(
    policy,
):
    result = policy.classify(
        "Use my verified phone number and I consent "
        "to receive text messages."
    )

    assert result.policy == CheckboxPolicy.BLOCKED


def test_non_string_checkbox_label_is_rejected(
    policy,
):
    with pytest.raises(TypeError):
        policy.classify(None)