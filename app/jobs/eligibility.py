"""Conservative screening of explicit posting requirements against local facts.

This is not a legal-status determination or an application-answer resolver.
Unrecognized requirements are reviewed, not inferred from a name or resume.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from enum import Enum
import re

from app.jobs.models import Job


class EligibilityStatus(str, Enum):
    CLEAR = "CLEAR"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True)
class EligibilityResult:
    status: EligibilityStatus
    findings: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        return (
            "; ".join(self.findings)
            or "No unresolved supported eligibility requirement detected."
        )


class JobEligibilityGate:
    """A narrow deterministic gate; CLEAR is not comprehensive eligibility.

    Missing facts stay unknown. Only explicit contradictory facts justify
    INELIGIBLE. Seasonal dates, legal categories and clearance eligibility
    always need review. Preferences and clearly negated requirements do not
    become hard exclusions.
    """

    MONTHS = {
        name.lower(): number
        for number, name in enumerate(calendar.month_name)
        if name
    }
    MONTH_PATTERN = "(?:" + "|".join(MONTHS) + ")"
    WINDOW = re.compile(
        r"(?:graduation(?: date)?|graduat(?:e|ing))\s+(?:between\s+)?"
        r"(" + MONTH_PATTERN + r")\s+(20\d{2})\s*(?:and|to|-)\s*"
        r"(" + MONTH_PATTERN + r")\s+(20\d{2})"
    )
    NO_SPONSOR = re.compile(
        r"without (?:current or future |now or future |visa |employment )?sponsorship"
        r"|(?:do not|cannot|can't|will not|unable to) (?:provide |offer )?(?:visa |employment )?sponsor(?:ship| visas?)?"
        r"|(?:visa |employment )?sponsorship (?:is |will be )?not (?:available|provided|offered)"
        r"|ineligible for (?:employment )?(?:visa )?sponsorship"
        r"|no (?:visa |employment )?sponsorship(?: (?:is )?(?:available|provided|offered))?"
        r"|must not require (?:visa |employment )?sponsorship"
    )

    def __init__(self, config: dict | None = None) -> None:
        config = {} if config is None else config
        if not isinstance(config, dict):
            raise ValueError("Candidate configuration must be a dictionary")
        candidate = config.get("candidate", {})
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be a dictionary")
        facts = candidate.get("eligibility", {})
        if not isinstance(facts, dict):
            raise ValueError("candidate.eligibility must be a dictionary")
        self.requires_sponsorship = self._boolean(facts, "requires_sponsorship")
        self.currently_enrolled = self._boolean(facts, "currently_enrolled")
        self.active_clearance = facts.get("active_clearance")
        if self.active_clearance not in {
            None,
            "none",
            "secret",
            "top_secret",
            "ts_sci",
        }:
            raise ValueError(
                "active_clearance must be null, none, secret, "
                "top_secret, or ts_sci"
            )
        education = candidate.get("education", {})
        if not isinstance(education, dict):
            raise ValueError("candidate.education must be a dictionary")
        degree = education.get("highest_degree", {})
        if not isinstance(degree, dict):
            raise ValueError("highest_degree must be a dictionary")
        graduation = degree.get("graduation", {})
        if not isinstance(graduation, dict):
            raise ValueError("graduation must be a dictionary")
        year, month = graduation.get("year"), graduation.get("month")
        if year is not None and (
            type(year) is not int
            or not 1900 <= year <= 2200
        ):
            raise ValueError("graduation.year must be a valid integer year")
        if month is not None and (type(month) is not int or not 1 <= month <= 12):
            raise ValueError("graduation.month must be an integer from 1 to 12")
        self.graduation = (
            (year, month)
            if year is not None and month is not None
            else None
        )

    @staticmethod
    def _boolean(facts: dict, key: str) -> bool | None:
        value = facts.get(key)
        if value is not None and type(value) is not bool:
            raise ValueError(f"candidate.eligibility.{key} must be true, false, or null")
        return value

    @staticmethod
    def _text(job: Job) -> str:
        description = job.description or ""
        # LinkedIn extraction includes recommendations after the actual posting.
        description = re.split(
            r"(?im)^\s*(?:[-*]\s*)?#{1,6}\s*(?:Seniority level|Similar jobs|People also viewed|More jobs|Explore collaborative articles)\b",
            description, maxsplit=1,
        )[0]
        text = (job.title + "\n" + description).lower()
        text = text.replace("u.s.", "us").replace("u.s", "us")
        text = text.translate(
            str.maketrans({
                "\u2019": "'",
                "\u2018": "'",
                "\u2013": "-",
                "\u2014": "-",
            })
        )
        clauses = re.split(r"\n+|;\s*|(?<=[.!?])\s+", text)
        kept = []
        for clause in clauses:
            if re.search(r"do not discriminate|without regard to|regardless of|not on race", clause):
                continue
            if (
                re.search(r"\bpreferred\b|\bnot required\b", clause)
                and not re.search(r"\bmust\b", clause)
            ):
                continue
            kept.append(clause)
        return re.sub(r"[ \t]+", " ", "\n".join(kept))

    def evaluate(self, job: Job) -> EligibilityResult:
        text = self._text(job)
        findings: list[tuple[EligibilityStatus, str]] = []

        def review(reason: str) -> None:
            findings.append((EligibilityStatus.NEEDS_REVIEW, reason))

        def mismatch(reason: str) -> None:
            findings.append((EligibilityStatus.INELIGIBLE, reason))

        if not job.description or not job.description.strip():
            review("Posting description is missing; eligibility cannot be screened")

        sponsor_clauses = [
            line
            for line in text.splitlines()
            if re.search(r"\bsponsorship\b|\bsponsor\b.*\bvisas?\b", line)
        ]
        if sponsor_clauses:
            sponsor_text = "\n".join(sponsor_clauses)
            denials = list(self.NO_SPONSOR.finditer(sponsor_text))
            remaining = self.NO_SPONSOR.sub("", sponsor_text)
            uncertain = re.search(
                r"\b(?:except|exceptions?|unless|may|might|depending)\b"
                r"|case by case",
                sponsor_text,
            )
            no_restriction = re.search(
                r"\bno sponsorship restrictions?\b",
                sponsor_text,
            )
            positive = re.search(
                r"sponsorship (?:is )?(?:available|provided|offered)"
                r"|(?:provide|offer) (?:visa )?sponsorship",
                remaining,
            )
            if no_restriction and not uncertain and not positive:
                denials = []
                sponsor_text = ""
            if not sponsor_text:
                pass
            if uncertain or positive and denials or not denials:
                if sponsor_text:
                    review("Sponsorship wording requires review")
            elif self.requires_sponsorship is True:
                mismatch("Posting prohibits sponsorship but candidate requires it")
            elif self.requires_sponsorship is None:
                review("Posting prohibits sponsorship; candidate sponsorship need is unknown")

        graduation_signal = re.search(
            r"graduation(?: date)?\s*(?::\s*)?"
            r"(?:between|by|in|before|after|"
            + self.MONTH_PATTERN
            + r"|fall|spring|summer|winter|20\d{2})\b"
            r"|graduat(?:e|ing) (?:between|by|in|before|after)\b"
            r"|recent graduates? only\b",
            text,
        )
        if graduation_signal:
            windows = {
                (
                    int(match[2]),
                    self.MONTHS[match[1]],
                    int(match[4]),
                    self.MONTHS[match[3]],
                )
                for match in self.WINDOW.finditer(text)
            }
            if len(windows) != 1:
                review("Graduation requirement is ambiguous or uses an unsupported date window")
            elif self.graduation is None:
                review("Posting specifies a graduation window; candidate graduation is unknown")
            else:
                y1, m1, y2, m2 = next(iter(windows))
                if (
                    (y1, m1) > (y2, m2)
                    or re.search(
                        r"\b(?:preferred|except|unless|or equivalent)\b",
                        text,
                    )
                ):
                    review("Graduation window needs review")
                elif not (y1, m1) <= self.graduation <= (y2, m2):
                    mismatch("Candidate graduation is outside the explicit month/year window")

        student_signal = re.search(r"currently (?:enrolled|pursuing)|must be (?:currently )?(?:enrolled|pursuing)|current enrollment|college students|student status", text)
        if student_signal:
            student_lines = "\n".join(
                line
                for line in text.splitlines()
                if re.search(
                    r"enroll|pursuing|students?|recently completed",
                    line,
                )
            )
            negated = re.search(
                r"\b(?:do not|does not|not) (?:need|required)"
                r"(?: to be)? (?:currently )?(?:enrolled|pursuing)",
                student_lines,
            )
            alternatives = re.search(
                r"\bor\b[^.!?\n]{0,80}"
                r"(?:recent graduate|graduated|completed|equivalent)"
                r"|\b(?:may|preferred|except|unless)\b",
                student_lines,
            )
            if negated:
                pass
            elif alternatives:
                review(
                    "Student/graduate alternatives or conditional "
                    "enrollment need review"
                )
            elif self.currently_enrolled is False:
                mismatch("Posting requires current enrollment but candidate is not enrolled")
            elif self.currently_enrolled is None:
                review("Posting requires current enrollment; candidate enrollment is unknown")

        if re.search(r"\bclearance\b", text):
            levels = re.findall(
                r"active (top secret|secret|ts/sci|ts sci)"
                r"(?: security)? clearance",
                text,
            )
            if (
                len(set(levels)) != 1
                or re.search(
                    r"obtain|eligib|may be required|depending",
                    text,
                )
            ):
                review("Clearance eligibility or requirement needs independent review")
            else:
                required = {
                    "secret": "secret",
                    "top secret": "top_secret",
                    "ts/sci": "ts_sci",
                    "ts sci": "ts_sci",
                }[levels[0]]
                if self.active_clearance == "none":
                    mismatch("Posting requires an active clearance but candidate reports none")
                elif self.active_clearance != required:
                    review(
                        "Required active clearance level has not been "
                        "explicitly confirmed"
                    )

        if re.search(
            r"\bus person\b"
            r"|\b(?:us |united states )?citizenship\b"
            r"|\b(?:us|united states) citizen\b"
            r"|export.control",
            text,
        ):
            review("Citizenship/export-control eligibility requires independent review")
        if re.search(r"(?:legally )?authorized to work|work authorization", text):
            review("Work-authorization requirement needs independent confirmation")

        status = EligibilityStatus.CLEAR
        if any(s == EligibilityStatus.INELIGIBLE for s, _ in findings):
            status = EligibilityStatus.INELIGIBLE
        elif findings:
            status = EligibilityStatus.NEEDS_REVIEW
        return EligibilityResult(
            status=status,
            findings=tuple(reason for _, reason in findings),
        )
