from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from app.jobs.models import (
    ApplicationStatus,
    Job,
    JobCategory,
    SeniorityLevel,
)


@dataclass(frozen=True)
class SeniorityResult:
    """Result of deterministic seniority classification."""

    seniority: SeniorityLevel
    reason: str
    matched_signal: Optional[str] = None


@dataclass(frozen=True)
class FilterResult:
    """Result of determining whether a job should continue."""

    keep: bool
    reason: str
    seniority: SeniorityLevel


class JobFilter:
    """
    Determines job seniority and whether a job should continue
    through the application pipeline.

    Filtering is intentionally conservative. Jobs are rejected only
    when there is sufficiently strong evidence that they fall outside
    the configured target roles or seniority range.
    """

    ENTRY_LEVEL_SIGNALS = (
        "entry level",
        "new grad",
        "new graduate",
        "university graduate",
        "graduate",
        "junior",
        "level i",
    )

    EARLY_CAREER_SIGNALS = (
        "early career",
        "associate",
    )

    SENIOR_SIGNALS = (
        "senior",
        "staff",
        "principal",
        "lead",
        "manager",
        "director",
    )

    US_STATE_CODES = frozenset({
        "al", "ak", "az", "ar", "ca", "co", "ct", "de",
        "fl", "ga", "hi", "id", "il", "in", "ia", "ks",
        "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
        "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny",
        "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
        "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
        "wi", "wy", "dc",
    })

    # Required experience above this threshold is treated as
    # outside the early-career target.
    MAX_REQUIRED_YEARS = 2

    def __init__(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ValueError(
                "Role configuration must be a dictionary."
            )

        seniority_config = config.get("seniority")

        if not isinstance(seniority_config, dict):
            raise ValueError(
                "roles.yaml must contain a 'seniority' dictionary."
            )

        self.seniority_config = seniority_config

        location_config = config.get("location")

        if not isinstance(location_config, dict):
            raise ValueError(
                "roles.yaml must contain a 'location' dictionary."
            )

        self.location_config = location_config

        self.country_aliases = tuple(
            self._normalize_text(value)
            for value in location_config.get(
                "country_aliases",
                [],
            )
            if str(value).strip()
        )

        self.us_location_aliases = tuple(
            self._normalize_text(value)
            for value in location_config.get(
                "us_location_aliases",
                [],
            )
            if str(value).strip()
        )

        self.excluded_location_signals = tuple(
            self._normalize_text(value)
            for value in location_config.get(
                "excluded_location_signals",
                [],
            )
            if str(value).strip()
        )

        self.allow_us_states = bool(
            location_config.get(
                "allow_us_states",
                True,
            )
        )

        self.allow_remote_us = bool(
            location_config.get(
                "allow_remote_us",
                True,
            )
        )

        self.allow_unknown_location = bool(
            location_config.get(
                "allow_unknown",
                False,
            )
        )

        self.preferred_signals = tuple(
            self._normalize_text(value)
            for value in seniority_config.get("preferred", [])
            if str(value).strip()
        )

        self.excluded_signals = tuple(
            self._normalize_text(value)
            for value in seniority_config.get(
                "usually_exclude",
                [],
            )
            if str(value).strip()
        )

        experience_config = seniority_config.get(
            "experience",
            {},
        )

        if not isinstance(experience_config, dict):
            raise ValueError(
                "'seniority.experience' must be a dictionary."
            )

        self.do_not_reject_preferred_experience = bool(
            experience_config.get(
                "do_not_reject_preferred_experience_automatically",
                True,
            )
        )

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        if not value:
            return ""

        normalized = value.lower().strip()

        normalized = re.sub(
            r"[^a-z0-9+#./–—-]+",
            " ",
            normalized,
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        return normalized.strip()

    @staticmethod
    def _contains_phrase(
        text: str,
        phrase: str,
    ) -> bool:
        if not text or not phrase:
            return False

        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(phrase)
            + r"(?![a-z0-9])"
        )

        return re.search(
            pattern,
            text,
        ) is not None

    def _find_signal(
        self,
        text: str,
        signals: tuple[str, ...],
    ) -> Optional[str]:
        for signal in signals:
            if self._contains_phrase(
                text,
                signal,
            ):
                return signal

        return None

    @staticmethod
    def _extract_required_experience(
        text: str,
    ) -> Optional[int]:
        """
        Extract the minimum years from clearly required experience
        statements.

        Examples:
            "3+ years of experience required" -> 3
            "minimum 4 years of experience" -> 4
            "requires 5 years of experience" -> 5
            "3-5 years of experience required" -> 3

        Preferred experience is intentionally ignored here.
        """

        if not text:
            return None

        patterns = (
            # "3+ years of experience required"
            r"(\d+)\s*\+?\s*years?"
            r"(?:\s+of)?\s+experience"
            r"[^.!?\n]{0,40}\brequired\b",

            # "3-5 years of experience required"
            r"(\d+)\s*(?:-|–|—|to)\s*\d+\s*years?"
            r"(?:\s+of)?\s+experience"
            r"[^.!?\n]{0,40}\brequired\b",

            # "minimum 3 years of experience"
            r"\bminimum\s+(?:of\s+)?(\d+)\s*\+?\s*years?"
            r"(?:\s+of)?\s+experience",

            # "requires 3 years of experience"
            r"\brequires?\s+(?:at\s+least\s+)?"
            r"(\d+)\s*\+?\s*years?"
            r"(?:\s+of)?\s+experience",

            # "at least 3 years of experience"
            r"\bat\s+least\s+(\d+)\s*\+?\s*years?"
            r"(?:\s+of)?\s+experience",
        )

        matches: list[int] = []

        for pattern in patterns:
            for match in re.finditer(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                matches.append(
                    int(match.group(1))
                )

        if not matches:
            return None

        return max(matches)

    @staticmethod
    def _has_preferred_experience_statement(
        text: str,
    ) -> bool:
        """
        Detect experience statements explicitly described as preferred.

        This is not used as evidence for rejection.
        """

        if not text:
            return False

        patterns = (
            r"\d+\s*\+?\s*years?"
            r"(?:\s+of)?\s+experience"
            r"[^.!?\n]{0,40}\bpreferred\b",

            r"\bpreferred\b"
            r"[^.!?\n]{0,40}"
            r"\d+\s*\+?\s*years?"
            r"(?:\s+of)?\s+experience",
        )

        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            is not None
            for pattern in patterns
        )

    def classify_seniority(
        self,
        job: Job,
    ) -> SeniorityResult:
        """
        Determine seniority using title first and description second.

        Explicit senior title signals take highest priority.
        """

        title = self._normalize_text(
            job.title
        )

        description = self._normalize_text(
            job.description
        )

        # ----------------------------------------------------
        # Explicit configured senior title signals
        # ----------------------------------------------------

        senior_signal = self._find_signal(
            title,
            self.excluded_signals,
        )

        if senior_signal:
            return SeniorityResult(
                seniority=SeniorityLevel.SENIOR,
                reason=(
                    "Job title contains an excluded "
                    "seniority signal."
                ),
                matched_signal=senior_signal,
            )

        # ----------------------------------------------------
        # Common "Sr" / "Sr." abbreviation
        # ----------------------------------------------------
        #
        # Use explicit boundaries instead of substring matching.
        #
        # Matches:
        #     Sr Software Engineer
        #     Sr. Software Engineer
        #     Sr/Software Engineer
        #
        # Does not match unrelated words merely containing "sr".
        # ----------------------------------------------------

        if re.search(
            r"(?<![a-z0-9])sr\.?(?![a-z0-9])",
            title,
        ):
            return SeniorityResult(
                seniority=SeniorityLevel.SENIOR,
                reason=(
                    "Job title contains the senior "
                    "abbreviation 'Sr'."
                ),
                matched_signal="sr",
            )

        # ----------------------------------------------------
        # Level II+
        # ----------------------------------------------------

        if re.search(
            r"\b(?:engineer|developer|scientist|analyst)"
            r"\s+(?:ii|iii|iv|v)\b",
            title,
        ):
            return SeniorityResult(
                seniority=SeniorityLevel.MID_LEVEL,
                reason=(
                    "Job title indicates a level above "
                    "entry-level Level I."
                ),
                matched_signal="level ii+",
            )

        # ----------------------------------------------------
        # Level I
        # ----------------------------------------------------

        if re.search(
            r"\b(?:engineer|developer|scientist|analyst)"
            r"\s+(?:1|i)\b",
            title,
        ):
            return SeniorityResult(
                seniority=SeniorityLevel.ENTRY_LEVEL,
                reason=(
                    "Job title indicates Level I."
                ),
                matched_signal="level i",
            )

        # ----------------------------------------------------
        # Junior
        # ----------------------------------------------------

        if self._contains_phrase(
            title,
            "junior",
        ):
            return SeniorityResult(
                seniority=SeniorityLevel.ENTRY_LEVEL,
                reason=(
                    "Job title contains an entry-level signal."
                ),
                matched_signal="junior",
            )

        # ----------------------------------------------------
        # New graduate
        # ----------------------------------------------------

        if (
            self._contains_phrase(
                title,
                "new grad",
            )
            or self._contains_phrase(
                title,
                "new graduate",
            )
        ):
            return SeniorityResult(
                seniority=SeniorityLevel.ENTRY_LEVEL,
                reason=(
                    "Job title explicitly targets new graduates."
                ),
                matched_signal="new grad",
            )

        # ----------------------------------------------------
        # Entry level
        # ----------------------------------------------------

        if self._contains_phrase(
            title,
            "entry level",
        ):
            return SeniorityResult(
                seniority=SeniorityLevel.ENTRY_LEVEL,
                reason=(
                    "Job title explicitly indicates entry level."
                ),
                matched_signal="entry level",
            )

        # ----------------------------------------------------
        # Associate / early career
        # ----------------------------------------------------

        if (
            self._contains_phrase(
                title,
                "associate",
            )
            or self._contains_phrase(
                title,
                "early career",
            )
        ):
            return SeniorityResult(
                seniority=SeniorityLevel.EARLY_CAREER,
                reason=(
                    "Job title contains an early-career signal."
                ),
                matched_signal=(
                    "associate"
                    if self._contains_phrase(
                        title,
                        "associate",
                    )
                    else "early career"
                ),
            )

        # ----------------------------------------------------
        # Required experience
        # ----------------------------------------------------

        required_years = self._extract_required_experience(
            description
        )

        if required_years is not None:
            if required_years <= self.MAX_REQUIRED_YEARS:
                return SeniorityResult(
                    seniority=SeniorityLevel.EARLY_CAREER,
                    reason=(
                        "Required experience is within the "
                        "configured early-career range."
                    ),
                    matched_signal=(
                        f"{required_years} years required"
                    ),
                )

            return SeniorityResult(
                seniority=SeniorityLevel.MID_LEVEL,
                reason=(
                    "Required experience exceeds the "
                    "early-career threshold."
                ),
                matched_signal=(
                    f"{required_years} years required"
                ),
            )

        # ----------------------------------------------------
        # Configured preferred early-career title signals
        # ----------------------------------------------------

        preferred_signal = self._find_signal(
            title,
            self.preferred_signals,
        )

        if preferred_signal:
            return SeniorityResult(
                seniority=SeniorityLevel.EARLY_CAREER,
                reason=(
                    "Job title contains a configured "
                    "preferred early-career signal."
                ),
                matched_signal=preferred_signal,
            )

        # ----------------------------------------------------
        # Unknown
        # ----------------------------------------------------

        return SeniorityResult(
            seniority=SeniorityLevel.UNKNOWN,
            reason=(
                "No reliable seniority signal was found."
            ),
        )

    def evaluate(
        self,
        job: Job,
    ) -> FilterResult:
        """
        Decide whether a job should continue through the pipeline.
        """

        seniority_result = self.classify_seniority(
            job
        )

        # Unsupported role category.
        if job.category == JobCategory.OTHER:
            return FilterResult(
                keep=False,
                reason=(
                    "Unsupported role category: OTHER."
                ),
                seniority=seniority_result.seniority,
            )

        # Location eligibility.
        #
        # Location filtering belongs in the deterministic eligibility
        # layer and must run before fit scoring. A technically strong
        # non-US job must never become AUTO_READY under the configured
        # US-only policy.
        location_allowed, location_reason = (
            self._is_location_allowed(
                job.location
            )
        )

        if not location_allowed:
            return FilterResult(
                keep=False,
                reason=location_reason,
                seniority=seniority_result.seniority,
            )

        # Explicit senior role.
        if (
            seniority_result.seniority
            == SeniorityLevel.SENIOR
        ):
            return FilterResult(
                keep=False,
                reason=(
                    "Job is outside the target seniority range: "
                    f"{seniority_result.reason}"
                ),
                seniority=seniority_result.seniority,
            )

        # Explicit mid-level role.
        if (
            seniority_result.seniority
            == SeniorityLevel.MID_LEVEL
        ):
            return FilterResult(
                keep=False,
                reason=(
                    "Job is outside the target early-career "
                    f"range: {seniority_result.reason}"
                ),
                seniority=seniority_result.seniority,
            )

        return FilterResult(
            keep=True,
            reason=(
                "Job is compatible with the target role "
                "and seniority rules."
            ),
            seniority=seniority_result.seniority,
        )

    def _is_location_allowed(
        self,
        location: Optional[str],
    ) -> tuple[bool, str]:
        """
        Determine whether a job location satisfies the configured
        United States location policy.
        """

        normalized = self._normalize_text(location)

        if not normalized:
            if self.allow_unknown_location:
                return (
                    True,
                    "Unknown location is allowed by configuration.",
                )

            return (
                False,
                "Job location is missing or unknown.",
            )

        # Explicit excluded/non-US signals take priority.
        for signal in self.excluded_location_signals:
            if self._contains_phrase(
                normalized,
                signal,
            ):
                return (
                    False,
                    (
                        "Job location contains excluded "
                        f"location signal: {signal}."
                    ),
                )

        # Explicit United States aliases.
        for alias in self.country_aliases + self.us_location_aliases:
            if self._contains_phrase(
                normalized,
                alias,
            ):
                return (
                    True,
                    (
                        "Job location matches allowed "
                        f"country signal: {alias}."
                    ),
                )

        # Remote jobs must explicitly indicate that they are US-based.
        if "remote" in normalized:
            if self.allow_remote_us:
                return (
                    False,
                    (
                        "Remote location does not explicitly "
                        "indicate United States eligibility."
                    ),
                )

            return (
                False,
                "Remote jobs are not allowed by configuration.",
            )

        # Accept standard US state abbreviations such as:
        #     Seattle, WA
        #     Austin, TX
        #     Portland, OR
        #     Indianapolis, IN
        #
        # State codes are detected from the original location string
        # rather than normalized text so that uppercase abbreviations
        # remain distinguishable from ordinary words such as "in"
        # and "or".
        if self.allow_us_states and location:
            state_match = re.search(
                r"(?:,\s*|\s+)([A-Z]{2})\b",
                location.strip(),
            )

            if (
                    state_match
                    and state_match.group(1).lower()
                    in self.US_STATE_CODES
            ):
                return (
                    True,
                    "Job location contains a US state code.",
                )

        return (
            False,
            (
                "Job location could not be verified as "
                "United States."
            ),
        )

    def filter_job(
        self,
        job: Job,
    ) -> Job:
        """
        Apply seniority classification and filtering to a Job.

        Filtered jobs remain trackable rather than being discarded.
        """

        result = self.evaluate(
            job
        )

        job.seniority = result.seniority

        if not result.keep:
            job.status = (
                ApplicationStatus.FILTERED_OUT
            )

            if job.notes:
                job.notes = (
                    f"{job.notes}\n"
                    f"Filter: {result.reason}"
                )
            else:
                job.notes = (
                    f"Filter: {result.reason}"
                )

        return job
