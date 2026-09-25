from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.jobs.models import Job


class DuplicateReason(str, Enum):
    """Reason a job was classified as a duplicate."""

    URL = "URL"
    EXTERNAL_JOB_ID = "EXTERNAL_JOB_ID"
    COMPANY_TITLE_LOCATION = "COMPANY_TITLE_LOCATION"


@dataclass(frozen=True)
class DuplicateResult:
    """
    Result of checking an incoming job against existing jobs.
    """

    is_duplicate: bool
    reason: Optional[DuplicateReason] = None
    matched_job: Optional[Job] = None


class JobDeduplicator:
    """
    Deterministic and conservative duplicate detector.

    A job is considered a duplicate when one of the following is true:

    1. The normalized URLs are identical.
    2. Company and external job ID are identical.
    3. Company, title, and location are identical after normalization.

    Fuzzy matching is intentionally avoided because false-positive duplicate
    detection could cause a legitimate job opportunity to be discarded.
    """

    TRACKING_QUERY_PARAMETERS = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "source",
        "src",
        "ref",
        "referrer",
        "trackingid",
    }

    @staticmethod
    def normalize_text(value: Optional[str]) -> str:
        """
        Normalize general text for deterministic comparisons.

        Example:
            "  Software   Engineer " -> "software engineer"
        """

        if not value:
            return ""

        normalized = value.strip().lower()
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized

    @classmethod
    def normalize_company(cls, company: str) -> str:
        """
        Normalize a company name.

        The CompanyRouter should normally canonicalize companies before
        deduplication. This method still handles common punctuation and
        whitespace differences defensively.
        """

        normalized = cls.normalize_text(company)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    @classmethod
    def normalize_title(cls, title: str) -> str:
        """
        Normalize a job title without performing fuzzy matching.
        """

        normalized = cls.normalize_text(title)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    @classmethod
    def normalize_location(cls, location: Optional[str]) -> str:
        """
        Normalize location formatting.

        Examples:
            "Seattle, WA" -> "seattle wa"
            " Seattle,  WA " -> "seattle wa"
        """

        normalized = cls.normalize_text(location)

        if not normalized:
            return ""

        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    @classmethod
    def normalize_external_job_id(
        cls,
        external_job_id: Optional[str],
    ) -> str:
        """
        Normalize an external job identifier.
        """

        return cls.normalize_text(external_job_id)

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """
        Normalize a URL while preserving parameters that may identify
        different job postings.

        Removes:
            - URL fragments
            - common tracking query parameters
            - trailing slash differences

        Does not remove arbitrary query parameters because some job boards
        identify jobs through query-string values.
        """

        raw_url = str(url).strip()

        parsed = urlsplit(raw_url)

        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()

        if parsed.port:
            netloc = f"{hostname}:{parsed.port}"
        else:
            netloc = hostname

        path = parsed.path

        if path != "/":
            path = path.rstrip("/")

        filtered_query = []

        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        ):
            if key.lower() not in cls.TRACKING_QUERY_PARAMETERS:
                filtered_query.append((key, value))

        # Sorting makes equivalent query parameter ordering deterministic.
        filtered_query.sort()

        query = urlencode(filtered_query, doseq=True)

        return urlunsplit(
            (
                scheme,
                netloc,
                path,
                query,
                "",
            )
        )

    @classmethod
    def same_url(cls, first: Job, second: Job) -> bool:
        return cls.normalize_url(
            first.url.encoded_string()
        ) == cls.normalize_url(
            second.url.encoded_string()
        )

    @classmethod
    def same_external_job_id(
        cls,
        first: Job,
        second: Job,
    ) -> bool:
        """
        External IDs are only compared when both jobs have one.

        Company must also match because different employers can use the
        same numeric or textual job identifier.
        """

        first_id = cls.normalize_external_job_id(
            first.external_job_id
        )
        second_id = cls.normalize_external_job_id(
            second.external_job_id
        )

        if not first_id or not second_id:
            return False

        same_company = (
            cls.normalize_company(first.company)
            == cls.normalize_company(second.company)
        )

        return same_company and first_id == second_id

    @classmethod
    def same_company_title_location(
        cls,
        first: Job,
        second: Job,
    ) -> bool:
        """
        Conservative fallback identity check.

        Location must be present on both jobs. If either location is missing,
        we do not declare a duplicate using this rule because a company may
        have the same job title in several locations.
        """

        first_location = cls.normalize_location(first.location)
        second_location = cls.normalize_location(second.location)

        if not first_location or not second_location:
            return False

        return (
            cls.normalize_company(first.company)
            == cls.normalize_company(second.company)
            and cls.normalize_title(first.title)
            == cls.normalize_title(second.title)
            and first_location == second_location
        )

    @classmethod
    def compare(
        cls,
        incoming_job: Job,
        existing_job: Job,
    ) -> DuplicateResult:
        """
        Compare two jobs using duplicate rules in priority order.
        """

        if cls.same_url(incoming_job, existing_job):
            return DuplicateResult(
                is_duplicate=True,
                reason=DuplicateReason.URL,
                matched_job=existing_job,
            )

        if cls.same_external_job_id(
            incoming_job,
            existing_job,
        ):
            return DuplicateResult(
                is_duplicate=True,
                reason=DuplicateReason.EXTERNAL_JOB_ID,
                matched_job=existing_job,
            )

        if cls.same_company_title_location(
            incoming_job,
            existing_job,
        ):
            return DuplicateResult(
                is_duplicate=True,
                reason=DuplicateReason.COMPANY_TITLE_LOCATION,
                matched_job=existing_job,
            )

        return DuplicateResult(is_duplicate=False)

    @classmethod
    def find_duplicate(
        cls,
        incoming_job: Job,
        existing_jobs: Iterable[Job],
    ) -> DuplicateResult:
        """
        Search existing jobs and return the first deterministic duplicate.

        If no duplicate exists, return is_duplicate=False.
        """

        for existing_job in existing_jobs:
            result = cls.compare(
                incoming_job,
                existing_job,
            )

            if result.is_duplicate:
                return result

        return DuplicateResult(is_duplicate=False)