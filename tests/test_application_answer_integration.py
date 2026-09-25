from pathlib import Path

import pytest

from app.applications.answer_loader import (
    ApplicationAnswerConfigError,
    ApplicationAnswerLoader,
)
from app.applications.answer_resolver import (
    AnswerStatus,
    ApplicationAnswerResolver,
)
from app.applications.question_policy import (
    ApplicationQuestionPolicy,
)


def write_config(
    tmp_path: Path,
    content: str,
) -> Path:
    path = tmp_path / "application_answers.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def build_resolver(
    config_path: Path,
) -> ApplicationAnswerResolver:
    answers = ApplicationAnswerLoader().load(
        config_path
    )

    return ApplicationAnswerResolver(
        verified_answers=answers,
        question_policy=ApplicationQuestionPolicy(),
    )


def test_verified_safe_answer_flows_through_system(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
first_name: Test
last_name: Candidate
email: candidate@example.com
city: Example City
state: WA
""",
    )

    resolver = build_resolver(path)

    result = resolver.resolve(
        "What is your email address?"
    )

    assert result.status == AnswerStatus.RESOLVED
    assert result.answer == "candidate@example.com"


def test_missing_safe_answer_requires_review(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
first_name: Test
last_name: Candidate
""",
    )

    resolver = build_resolver(path)

    result = resolver.resolve(
        "What is your email address?"
    )

    assert result.status == AnswerStatus.NEEDS_REVIEW
    assert result.answer is None


def test_contextual_question_is_never_generated(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
email: candidate@example.com
""",
    )

    resolver = build_resolver(path)

    result = resolver.resolve(
        "Why are you interested in this role?"
    )

    assert result.status == AnswerStatus.NEEDS_REVIEW
    assert result.answer is None


def test_sensitive_question_cannot_use_profile_data(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
first_name: Test
state: WA
""",
    )

    resolver = build_resolver(path)

    result = resolver.resolve(
        "Are you legally authorized to work "
        "in the United States?"
    )

    assert result.status == AnswerStatus.SENSITIVE
    assert result.answer is None


def test_sponsorship_question_cannot_be_resolved(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
first_name: Test
""",
    )

    resolver = build_resolver(path)

    result = resolver.resolve(
        "Will you now or in the future require "
        "sponsorship?"
    )

    assert result.status == AnswerStatus.SENSITIVE
    assert result.answer is None


def test_signature_requires_manual_action(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
full_name: Test Candidate
""",
    )

    resolver = build_resolver(path)

    result = resolver.resolve(
        "Type your full name as your "
        "electronic signature."
    )

    assert result.status == AnswerStatus.MANUAL
    assert result.answer is None


def test_attestation_requires_manual_action(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
email: candidate@example.com
""",
    )

    resolver = build_resolver(path)

    result = resolver.resolve(
        "I certify that the email address "
        "above is correct."
    )

    assert result.status == AnswerStatus.MANUAL
    assert result.answer is None


def test_sensitive_field_cannot_enter_answer_store(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
email: candidate@example.com
visa_status: example
""",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        build_resolver(path)


def test_unknown_field_cannot_enter_answer_store(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
email: candidate@example.com
salary_expectation: example
""",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        build_resolver(path)


def test_empty_config_produces_no_automatic_answers(
    tmp_path,
):
    path = write_config(
        tmp_path,
        "",
    )

    resolver = build_resolver(path)

    result = resolver.resolve(
        "Email Address"
    )

    assert result.status == AnswerStatus.NEEDS_REVIEW
    assert result.answer is None