from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class QuestionPolicy(str, Enum):
    """Safety classification for application-form questions."""

    SAFE = "SAFE"
    REVIEW = "REVIEW"
    SENSITIVE = "SENSITIVE"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class QuestionPolicyResult:
    """Classification result for one application question."""

    policy: QuestionPolicy
    reason: str


class ApplicationQuestionPolicy:
    """
    Deterministically classifies application-form questions.

    This class does not generate answers and does not interact
    with a browser.
    """

    MANUAL_PATTERNS = (
        r"\bsignature\b",
        r"\belectronic signature\b",
        r"\be[- ]?signature\b",
        r"\bcertify\b",
        r"\bcertification\b",
        r"\battest\b",
        r"\battestation\b",
        r"\bunder penalty of perjury\b",
        r"\bterms and conditions\b",
        r"\bcaptcha\b",
        r"\bhuman verification\b",
        r"\bnot a robot\b",
    )

    SENSITIVE_PATTERNS = (
        r"\bwork authorization\b",
        r"\bauthorized to work\b",
        r"\blegally authorized\b",
        r"\bemployment authorization\b",
        r"\bvisa\b",
        r"\bsponsorship\b",
        r"\bsponsor\b",
        r"\bimmigration\b",
        r"\bcitizenship\b",
        r"\bcitizen\b",
        r"\bpermanent resident\b",
        r"\bgreen card\b",
        r"\brace\b",
        r"\bethnicity\b",
        r"\bethnic\b",
        r"\bhispanic\b",
        r"\blatino\b",
        r"\blatina\b",
        r"\blatinx\b",
        r"\bgender\b",
        r"\bsex\b",
        r"\bsexual orientation\b",
        r"\bdisability\b",
        r"\bdisabled\b",
        r"\bveteran\b",
        r"\bmilitary status\b",
        r"\bcriminal\b",
        r"\bconviction\b",
        r"\bconvicted\b",
        r"\bbackground check\b",
        r"\bconflicts? of interest\b",
    )

    REVIEW_PATTERNS = (
        r"\bwhy.*(?:role|company|position)\b",
        r"\bwhy.*(?:interested|join)\b",
        r"\bdescribe\b",
        r"\bexplain\b",
        r"\btell us about\b",
        r"\btell me about\b",
        r"\bexperience with\b",
        r"\bexperience using\b",
        r"\bcover letter\b",
        r"\badditional information\b",
        r"\banything else\b",
    )

    SAFE_PATTERNS = (
        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?first name[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?last name[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?full name[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?"
        r"preferred(?: first)? name[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?email"
        r"(?: address)?[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?phone"
        r"(?: number)?[?:.]?$",

        r"^(?:enter |provide |please enter |please provide |"
        r"your )?(?:your )?linkedin(?: profile| url)?[?:.]?$",

        r"^(?:enter |provide |please enter |please provide |"
        r"your )?(?:your )?github(?: profile| url)?[?:.]?$",

        r"^(?:enter |provide |please enter |please provide |"
        r"your )?(?:your )?portfolio(?: website| url)?[?:.]?$",

        r"^(?:enter |provide |please enter |please provide |"
        r"your )?(?:your )?(?:personal )?website[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?address[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?city[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?state[?:.]?$",

        r"^(?:what is |what's |enter |provide |please enter |"
        r"please provide |your )?(?:your )?"
        r"(?:zip|zip code|postal code)[?:.]?$",
    )

    def classify(
        self,
        question: str,
    ) -> QuestionPolicyResult:
        """
        Classify a form question using conservative deterministic
        matching.

        Unknown or ambiguous questions require human review.
        """

        if not isinstance(question, str):
            raise TypeError("Question must be a string.")

        normalized = self._normalize(question)

        if not normalized:
            return QuestionPolicyResult(
                policy=QuestionPolicy.REVIEW,
                reason="Empty question requires human review.",
            )

        if self._matches(
            normalized,
            self.MANUAL_PATTERNS,
        ):
            return QuestionPolicyResult(
                policy=QuestionPolicy.MANUAL,
                reason=(
                    "Question requires explicit human action "
                    "or legal confirmation."
                ),
            )

        if self._matches(
            normalized,
            self.SENSITIVE_PATTERNS,
        ):
            return QuestionPolicyResult(
                policy=QuestionPolicy.SENSITIVE,
                reason=(
                    "Question requests sensitive candidate "
                    "information that must not be inferred."
                ),
            )

        if self._matches(
            normalized,
            self.REVIEW_PATTERNS,
        ):
            return QuestionPolicyResult(
                policy=QuestionPolicy.REVIEW,
                reason=(
                    "Question requires a contextual or "
                    "candidate-specific response."
                ),
            )

        if self._matches(
            normalized,
            self.SAFE_PATTERNS,
        ):
            return QuestionPolicyResult(
                policy=QuestionPolicy.SAFE,
                reason=(
                    "Question requests ordinary candidate "
                    "profile information."
                ),
            )

        return QuestionPolicyResult(
            policy=QuestionPolicy.REVIEW,
            reason=(
                "Question is not recognized as safely "
                "answerable."
            ),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.strip().lower().split())

    @staticmethod
    def _matches(
        question: str,
        patterns: tuple[str, ...],
    ) -> bool:
        return any(
            re.search(pattern, question)
            for pattern in patterns
        )