import pytest

from app.applications.answer_resolver import (
    AnswerStatus,
    ApplicationAnswerResolver,
)
from app.applications.question_policy import (
    ApplicationQuestionPolicy,
)


@pytest.fixture
def verified_answers():
    return {
        "first_name": "Test",
        "last_name": "Candidate",
        "full_name": "Test Candidate",
        "email": "candidate@example.com",
        "phone": "555-0100",
        "city": "Example City",
        "state": "WA",
        "postal_code": "98101",
        "linkedin": "https://linkedin.com/in/example",
        "github": "https://github.com/example",
    }


@pytest.fixture
def resolver(verified_answers):
    return ApplicationAnswerResolver(
        verified_answers=verified_answers,
        question_policy=ApplicationQuestionPolicy(),
    )


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("First Name", "Test"),
        ("Last Name", "Candidate"),
        ("What is your full name?", "Test Candidate"),
        (
            "Email Address",
            "candidate@example.com",
        ),
        ("Phone Number", "555-0100"),
        ("City", "Example City"),
        ("State", "WA"),
        ("Zip Code", "98101"),
        (
            "LinkedIn Profile",
            "https://linkedin.com/in/example",
        ),
        (
            "GitHub URL",
            "https://github.com/example",
        ),
    ],
)
def test_safe_questions_resolve_from_verified_data(
    resolver,
    question,
    expected,
):
    result = resolver.resolve(question)

    assert result.status == AnswerStatus.RESOLVED
    assert result.answer == expected


def test_missing_verified_answer_requires_review():
    resolver = ApplicationAnswerResolver(
        verified_answers={
            "first_name": "Test",
        },
        question_policy=ApplicationQuestionPolicy(),
    )

    result = resolver.resolve(
        "Please provide your phone number."
    )

    assert result.status == AnswerStatus.NEEDS_REVIEW
    assert result.answer is None


def test_contextual_question_is_not_answered(
    resolver,
):
    result = resolver.resolve(
        "Why are you interested in this role?"
    )

    assert result.status == AnswerStatus.NEEDS_REVIEW
    assert result.answer is None


def test_work_authorization_is_not_answered(
    resolver,
):
    result = resolver.resolve(
        "Are you legally authorized to work "
        "in the United States?"
    )

    assert result.status == AnswerStatus.SENSITIVE
    assert result.answer is None


def test_sponsorship_is_not_answered(
    resolver,
):
    result = resolver.resolve(
        "Will you require sponsorship?"
    )

    assert result.status == AnswerStatus.SENSITIVE
    assert result.answer is None


def test_signature_is_not_answered(
    resolver,
):
    result = resolver.resolve(
        "Type your electronic signature."
    )

    assert result.status == AnswerStatus.MANUAL
    assert result.answer is None


def test_attestation_is_not_answered(
    resolver,
):
    result = resolver.resolve(
        "I certify that this information is accurate."
    )

    assert result.status == AnswerStatus.MANUAL
    assert result.answer is None


def test_missing_field_never_generates_answer():
    resolver = ApplicationAnswerResolver(
        verified_answers={},
        question_policy=ApplicationQuestionPolicy(),
    )

    result = resolver.resolve("Email Address")

    assert result.status == AnswerStatus.NEEDS_REVIEW
    assert result.answer is None


def test_answer_values_are_trimmed():
    resolver = ApplicationAnswerResolver(
        verified_answers={
            "email": "  candidate@example.com  ",
        },
        question_policy=ApplicationQuestionPolicy(),
    )

    result = resolver.resolve("Email Address")

    assert result.answer == "candidate@example.com"


def test_empty_answer_is_rejected():
    with pytest.raises(ValueError):
        ApplicationAnswerResolver(
            verified_answers={
                "email": "   ",
            },
            question_policy=ApplicationQuestionPolicy(),
        )


def test_non_string_answer_is_rejected():
    with pytest.raises(TypeError):
        ApplicationAnswerResolver(
            verified_answers={
                "phone": 12345,
            },
            question_policy=ApplicationQuestionPolicy(),
        )


def test_non_mapping_answers_are_rejected():
    with pytest.raises(TypeError):
        ApplicationAnswerResolver(
            verified_answers=[],
            question_policy=ApplicationQuestionPolicy(),
        )

@pytest.mark.parametrize(
    "question",
    [
        "Why should we contact you at this email?",
        "Describe the state of your current project.",
        "How would you address a disagreement with a teammate?",
        "Tell us about your experience working in Washington state.",
        "What email marketing tools have you used?",
    ],
)
def test_profile_words_inside_contextual_questions_are_not_resolved(
    resolver,
    question,
):
    result = resolver.resolve(question)

    assert result.status == AnswerStatus.NEEDS_REVIEW
    assert result.answer is None


def test_sensitive_question_containing_state_is_not_resolved(
    resolver,
):
    result = resolver.resolve(
        "What is your current immigration status "
        "in the state where you reside?"
    )

    assert result.status == AnswerStatus.SENSITIVE
    assert result.answer is None


def test_sensitive_question_containing_address_is_not_resolved(
    resolver,
):
    result = resolver.resolve(
        "Provide your address and describe your "
        "work authorization status."
    )

    assert result.status == AnswerStatus.SENSITIVE
    assert result.answer is None


def test_manual_question_containing_email_is_not_resolved(
    resolver,
):
    result = resolver.resolve(
        "I certify that the email address above "
        "is accurate."
    )

    assert result.status == AnswerStatus.MANUAL
    assert result.answer is None


def test_manual_question_containing_name_is_not_resolved(
    resolver,
):
    result = resolver.resolve(
        "Type your full name as your electronic signature."
    )

    assert result.status == AnswerStatus.MANUAL
    assert result.answer is None

def test_email_address_maps_to_email_not_address(
    resolver,
):
    result = resolver.resolve(
        "Email Address"
    )

    assert result.status == AnswerStatus.RESOLVED
    assert result.answer == "candidate@example.com"


def test_linkedin_url_does_not_map_to_generic_website(
    resolver,
):
    result = resolver.resolve(
        "LinkedIn URL"
    )

    assert result.status == AnswerStatus.RESOLVED
    assert (
        result.answer
        == "https://linkedin.com/in/example"
    )