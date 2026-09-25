from pathlib import Path

import pytest

from app.applications.answer_loader import (
    ApplicationAnswerConfigError,
)
from app.applications.answer_resolver import (
    AnswerStatus,
)
from app.applications.answer_service import (
    build_application_answer_resolver,
)


def write_config(
    tmp_path: Path,
    content: str,
) -> Path:
    path = tmp_path / "application_answers.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_builds_resolver_from_verified_config(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
first_name: Test
email: candidate@example.com
""",
    )

    resolver = build_application_answer_resolver(path)

    result = resolver.resolve(
        "What is your email address?"
    )

    assert result.status == AnswerStatus.RESOLVED
    assert result.answer == "candidate@example.com"


def test_missing_verified_value_still_requires_review(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
first_name: Test
""",
    )

    resolver = build_application_answer_resolver(path)

    result = resolver.resolve(
        "Email Address"
    )

    assert result.status == AnswerStatus.NEEDS_REVIEW
    assert result.answer is None


def test_sensitive_question_still_cannot_be_answered(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
first_name: Test
state: WA
""",
    )

    resolver = build_application_answer_resolver(path)

    result = resolver.resolve(
        "What is your visa status?"
    )

    assert result.status == AnswerStatus.SENSITIVE
    assert result.answer is None


def test_manual_question_still_requires_human_action(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
full_name: Test Candidate
""",
    )

    resolver = build_application_answer_resolver(path)

    result = resolver.resolve(
        "Type your electronic signature."
    )

    assert result.status == AnswerStatus.MANUAL
    assert result.answer is None


def test_invalid_config_fails_during_construction(
    tmp_path,
):
    path = write_config(
        tmp_path,
        """
visa_status: example
""",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        build_application_answer_resolver(path)


def test_missing_config_fails_closed(
    tmp_path,
):
    path = tmp_path / "does_not_exist.yaml"

    with pytest.raises(FileNotFoundError):
        build_application_answer_resolver(path)