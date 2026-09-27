from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional

from app.applications.question_policy import (
    ApplicationQuestionPolicy,
    QuestionPolicy,
)


class AnswerStatus(str, Enum):
    """Outcome of attempting to resolve an application answer."""

    RESOLVED = "RESOLVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SENSITIVE = "SENSITIVE"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class AnswerResolution:
    """Result of resolving one application-form question."""

    status: AnswerStatus
    answer: Optional[str]
    reason: str


class ApplicationAnswerResolver:
    """
    Resolves application questions only from explicitly verified
    candidate data.

    This class never invents candidate information and does not
    interact with a browser.
    """

    FIELD_PATTERNS = (
        ("preferred_name", r"preferred(?: first)? name"),
        ("first_name", r"first name"),
        ("last_name", r"last name"),
        ("full_name", r"full name"),
        ("email", r"email(?: address)?"),
        ("phone", r"phone(?: number)?"),
        ("linkedin", r"linkedin(?: profile| url)?"),
        ("github", r"github(?: profile| url)?"),
        ("portfolio", r"portfolio(?: website| url)?"),
        ("website", r"(?:personal )?website"),
        ("address", r"address"),
        ("city", r"city"),
        ("state", r"state"),
        ("postal_code", r"(?:zip|zip code|postal code)"),
    )

    def __init__(
        self,
        verified_answers: Mapping[str, str],
        question_policy: ApplicationQuestionPolicy,
    ):
        self.verified_answers = self._validate_answers(
            verified_answers
        )
        self.question_policy = question_policy

    def resolve(
        self,
        question: str,
    ) -> AnswerResolution:
        policy_result = self.question_policy.classify(
            question
        )

        if policy_result.policy == QuestionPolicy.MANUAL:
            return AnswerResolution(
                status=AnswerStatus.MANUAL,
                answer=None,
                reason=policy_result.reason,
            )

        if policy_result.policy == QuestionPolicy.SENSITIVE:
            return AnswerResolution(
                status=AnswerStatus.SENSITIVE,
                answer=None,
                reason=policy_result.reason,
            )

        if policy_result.policy == QuestionPolicy.REVIEW:
            return AnswerResolution(
                status=AnswerStatus.NEEDS_REVIEW,
                answer=None,
                reason=policy_result.reason,
            )

        field = self._identify_field(question)

        if field is None:
            return AnswerResolution(
                status=AnswerStatus.NEEDS_REVIEW,
                answer=None,
                reason=(
                    "Safe question could not be mapped to a "
                    "verified candidate field."
                ),
            )

        answer = self.verified_answers.get(field)

        if answer is None:
            return AnswerResolution(
                status=AnswerStatus.NEEDS_REVIEW,
                answer=None,
                reason=(
                    f"No verified answer exists for '{field}'."
                ),
            )

        return AnswerResolution(
            status=AnswerStatus.RESOLVED,
            answer=answer,
            reason=(
                f"Resolved from verified candidate field "
                f"'{field}'."
            ),
        )

    @classmethod
    def _identify_field(
        cls,
        question: str,
    ) -> Optional[str]:
        import re

        normalized = " ".join(
            question.strip().lower().split()
        )

        for field, pattern in cls.FIELD_PATTERNS:
            if re.search(pattern, normalized):
                return field

        return None

    @staticmethod
    def _validate_answers(
        answers: Mapping[str, str],
    ) -> dict[str, str]:
        if not isinstance(answers, Mapping):
            raise TypeError(
                "Verified answers must be a mapping."
            )

        validated: dict[str, str] = {}

        for key, value in answers.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(
                    "Verified answer keys must be "
                    "non-empty strings."
                )

            if not isinstance(value, str):
                raise TypeError(
                    "Verified answer values must be strings."
                )

            cleaned = value.strip()

            if not cleaned:
                raise ValueError(
                    "Verified answer values must not be empty."
                )

            validated[key.strip()] = cleaned

        return validated