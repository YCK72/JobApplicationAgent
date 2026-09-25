from __future__ import annotations

from pathlib import Path

from app.applications.answer_loader import (
    ApplicationAnswerLoader,
)
from app.applications.answer_resolver import (
    ApplicationAnswerResolver,
)
from app.applications.question_policy import (
    ApplicationQuestionPolicy,
)


DEFAULT_ANSWER_CONFIG = Path(
    "config/application_answers.yaml"
)


def build_application_answer_resolver(
    config_path: str | Path = DEFAULT_ANSWER_CONFIG,
) -> ApplicationAnswerResolver:
    """
    Build an application-answer resolver from verified private
    candidate configuration.

    Loading, policy classification, and answer resolution remain
    separate deterministic layers.
    """

    verified_answers = ApplicationAnswerLoader().load(
        config_path
    )

    return ApplicationAnswerResolver(
        verified_answers=verified_answers,
        question_policy=ApplicationQuestionPolicy(),
    )