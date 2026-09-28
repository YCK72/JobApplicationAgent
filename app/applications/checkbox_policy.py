from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class CheckboxPolicy(str, Enum):
    """
    Safety classification for application-form checkbox semantics.
    """

    SAFE = "SAFE"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CheckboxPolicyResult:
    """
    Classification result for one checkbox label.

    SAFE means only that the checkbox's meaning is eligible for further
    deterministic authorization.

    SAFE does not determine whether the checkbox should be checked or
    unchecked and does not authorize browser mutation or submission.
    """

    policy: CheckboxPolicy
    reason: str


class ApplicationCheckboxPolicy:
    """
    Deterministically classify application-form checkbox semantics.

    Checkbox authorization is intentionally stricter than ordinary
    application-question classification because toggling a checkbox can
    express consent, certification, acknowledgement, legal status,
    marketing preference, or other consequential intent.

    SAFE is therefore a narrow semantic allowlist. It does not supply a
    desired boolean state and does not authorize browser execution.

    BLOCKED covers known semantics that must never be automatically
    toggled by this application.

    Unknown or ambiguous checkbox labels require human review.

    This class does not interact with a browser and does not submit
    applications.
    """

    BLOCKED_PATTERNS = (
        # Certification, attestation, acknowledgement, and legal terms.
        r"\bcertif(?:y|ies|ied|ication)\b",
        r"\battest(?:ation|s|ed|ing)?\b",
        r"\backnowledg(?:e|es|ed|ement|ements|ing)\b",
        r"\bterms and conditions\b",
        r"\baccept(?:s|ed|ing)?\b.*\bterms\b",
        r"\bagree(?:s|d|ing)?\b.*\bterms\b",
        r"\bprivacy policy\b",
        r"\bconsent\b",

        # Marketing, recruiting communications, subscriptions, and
        # persistence of candidate information.
        r"\bsubscrib(?:e|es|ed|ing)\b",
        r"\bjob alerts?\b",
        r"\bmarketing\b",
        r"\bnewsletter(?:s)?\b",
        r"\bfuture opportunities\b",
        r"\brecruiting updates?\b",
        r"\brecruiting communications?\b",
        r"\bremember my information\b",
        r"\bsave my information\b",
        r"\bfuture applications?\b",

        # Sensitive employment eligibility and immigration semantics.
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

        # Sensitive demographic and legal semantics.
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

        # Signature and verification semantics remain human-only.
        r"\bsignature\b",
        r"\belectronic signature\b",
        r"\be[- ]?signature\b",
        r"\bunder penalty of perjury\b",
        r"\bcaptcha\b",
        r"\bhuman verification\b",
        r"\bnot a robot\b",
    )

    SAFE_PATTERNS = (
        r"^use my verified preferred name on this application[.!]?$",
        r"^use my verified phone number for application contact[.!]?$",
    )

    AMBIGUOUS_PATTERNS = (
        r"^confirm[.!]?$",
        r"^yes[.!]?$",
        r"^no[.!]?$",
        r"^option\s+\d+[.!]?$",
        r"^checkbox[.!]?$",
        r"^select this option[.!]?$",
    )

    def classify(
        self,
        label: str,
    ) -> CheckboxPolicyResult:
        """
        Classify a checkbox label using conservative deterministic
        matching.

        Known consequential semantics are blocked before the narrow SAFE
        allowlist is considered. Unknown or ambiguous labels require
        human review.
        """

        if not isinstance(label, str):
            raise TypeError("Checkbox label must be a string.")

        normalized = self._normalize(label)

        if not normalized:
            return CheckboxPolicyResult(
                policy=CheckboxPolicy.REVIEW,
                reason="Empty checkbox label requires human review.",
            )

        if self._matches(
            normalized,
            self.BLOCKED_PATTERNS,
        ):
            return CheckboxPolicyResult(
                policy=CheckboxPolicy.BLOCKED,
                reason=(
                    "Checkbox expresses consequential, sensitive, "
                    "consent, certification, communication, or other "
                    "semantics that must not be automatically toggled."
                ),
            )

        if self._matches(
            normalized,
            self.AMBIGUOUS_PATTERNS,
        ):
            return CheckboxPolicyResult(
                policy=CheckboxPolicy.REVIEW,
                reason=(
                    "Checkbox label is too ambiguous for automatic "
                    "authorization."
                ),
            )

        if self._matches(
            normalized,
            self.SAFE_PATTERNS,
        ):
            return CheckboxPolicyResult(
                policy=CheckboxPolicy.SAFE,
                reason=(
                    "Checkbox matches a narrowly approved "
                    "non-sensitive semantic allowlist."
                ),
            )

        return CheckboxPolicyResult(
            policy=CheckboxPolicy.REVIEW,
            reason=(
                "Checkbox semantics are not recognized as safely "
                "automatable."
            ),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.strip().lower().split())

    @staticmethod
    def _matches(
        label: str,
        patterns: tuple[str, ...],
    ) -> bool:
        return any(
            re.search(pattern, label)
            for pattern in patterns
        )