import pytest

from app.applications.question_policy import (
    ApplicationQuestionPolicy,
    QuestionPolicy,
)


@pytest.fixture
def policy():
    return ApplicationQuestionPolicy()


@pytest.mark.parametrize(
    "question",
    [
        "What are your salary expectations?",
        "What is your desired salary?",
        "What is your earliest available start date?",
        "When can you start?",
        "Are you willing to relocate?",
        "Are you willing to travel?",
        "How did you hear about us?",
        "Were you referred by an employee?",
        "Are you at least 18 years of age?",
        "What is your highest level of education?",
        "What university did you attend?",
        "What is your current employer?",
        "How many years of professional experience do you have?",
        "Have you previously worked for this company?",
        "Are you currently bound by a non-compete agreement?",
    ],
)
def test_unapproved_candidate_specific_questions_require_review(
    policy,
    question,
):
    result = policy.classify(question)

    assert result.policy == QuestionPolicy.REVIEW


@pytest.mark.parametrize(
    "question",
    [
        "What is your email address?",
        "Enter your email address",
        "Please provide your phone number.",
        "What is your first name?",
        "Enter your last name",
        "Please provide your city.",
        "What is your state?",
        "Enter your zip code",
        "Provide your LinkedIn URL",
        "Please provide your GitHub profile.",
    ],
)
def test_direct_profile_requests_are_safe(
    policy,
    question,
):
    result = policy.classify(question)

    assert result.policy == QuestionPolicy.SAFE


@pytest.mark.parametrize(
    "question",
    [
        "Are you legally authorized to work in the United States?",
        "Will you now or in the future require sponsorship?",
        "What is your visa status?",
        "What is your citizenship?",
        "Are you a permanent resident?",
        "Please select your race or ethnicity.",
        "Are you Hispanic/Latino?",
        "Are you Hispanic or Latino?",
        "Hispanic ethnicity",
        "Are you Latina?",
        "Do you identify as Latinx?",
        "What is your gender?",
        "Do you have a disability?",
        "What is your veteran status?",
        "Have you ever been convicted of a crime?",
        "Are you willing to undergo a background check?",
        "Do you have any conflicts of interest?",
    ],
)
def test_sensitive_questions_are_never_safe(
    policy,
    question,
):
    result = policy.classify(question)

    assert result.policy == QuestionPolicy.SENSITIVE


@pytest.mark.parametrize(
    "question",
    [
        "Type your electronic signature.",
        "I certify that the information provided is accurate.",
        "Please attest that the information above is correct.",
        "I agree to the terms and conditions.",
        "Complete the CAPTCHA.",
        "Confirm that you are not a robot.",
    ],
)
def test_human_action_questions_are_manual(
    policy,
    question,
):
    result = policy.classify(question)

    assert result.policy == QuestionPolicy.MANUAL


def test_unknown_question_defaults_to_review(
    policy,
):
    result = policy.classify(
        "What is your preferred working style?"
    )

    assert result.policy == QuestionPolicy.REVIEW


def test_empty_question_defaults_to_review(
    policy,
):
    result = policy.classify("   ")

    assert result.policy == QuestionPolicy.REVIEW


def test_matching_is_case_insensitive(
    policy,
):
    result = policy.classify(
        "ARE YOU LEGALLY AUTHORIZED TO WORK "
        "IN THE UNITED STATES?"
    )

    assert result.policy == QuestionPolicy.SENSITIVE


def test_manual_policy_has_priority_over_sensitive(
    policy,
):
    result = policy.classify(
        "I certify that my work authorization "
        "information is accurate."
    )

    assert result.policy == QuestionPolicy.MANUAL


def test_sensitive_policy_has_priority_over_safe(
    policy,
):
    result = policy.classify(
        "Please provide your email for "
        "work authorization verification."
    )

    assert result.policy == QuestionPolicy.SENSITIVE


def test_sensitive_content_beats_review_language(
    policy,
):
    result = policy.classify(
        "Please describe your current visa status."
    )

    assert result.policy == QuestionPolicy.SENSITIVE


def test_manual_attestation_beats_safe_profile_content(
    policy,
):
    result = policy.classify(
        "I certify that my name and email address "
        "are correct."
    )

    assert result.policy == QuestionPolicy.MANUAL


def test_manual_attestation_beats_sensitive_content(
    policy,
):
    result = policy.classify(
        "I certify that my sponsorship information "
        "is accurate."
    )

    assert result.policy == QuestionPolicy.MANUAL


def test_unknown_question_with_safe_word_is_not_necessarily_safe(
    policy,
):
    result = policy.classify(
        "Why should we contact you at this email?"
    )

    assert result.policy == QuestionPolicy.REVIEW


def test_non_string_question_is_rejected(
    policy,
):
    with pytest.raises(TypeError):
        policy.classify(None)

@pytest.mark.parametrize(
    "question",
    [
        "Preferred First Name",
        "Preferred Name",
        "Website",
        "Personal Website",
    ],
)
def test_safe_profile_aliases_are_safe(
    policy,
    question,
):
    result = policy.classify(question)

    assert result.policy == QuestionPolicy.SAFE

@pytest.mark.parametrize(
    "question",
    [
        "Country",
        "What is your country?",
        "Location (City)",
    ],
)
def test_factual_location_profile_questions_are_safe(
    policy,
    question,
):
    result = policy.classify(question)

    assert result.policy == QuestionPolicy.SAFE


@pytest.mark.parametrize(
    "question",
    [
        "Location",
        "Working location",
        "Preferred location",
        "Preferred working location",
    ],
)
def test_ambiguous_or_preference_location_questions_require_review(
    policy,
    question,
):
    result = policy.classify(question)

    assert result.policy == QuestionPolicy.REVIEW
