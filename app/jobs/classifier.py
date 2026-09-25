from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from app.jobs.models import Job, JobCategory


@dataclass(frozen=True)
class ClassificationResult:
    """Result produced by the deterministic role classifier."""

    category: JobCategory
    confidence: float
    reason: str
    matched_title: Optional[str] = None
    matched_keywords: tuple[str, ...] = ()


class RoleClassifier:
    """
    Configuration-driven job role classifier.

    Classification priority:

    1. Exact normalized title match.
    2. Configured title contained within a longer job title.
    3. Description/title keyword evidence.
    4. OTHER when there is insufficient evidence.

    Title evidence is intentionally stronger than keyword evidence.
    """

    TITLE_EXACT_CONFIDENCE = 1.0
    TITLE_CONTAINS_CONFIDENCE = 0.9

    def __init__(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ValueError("Role configuration must be a dictionary.")

        categories = config.get("categories")

        if not isinstance(categories, dict):
            raise ValueError(
                "roles.yaml must contain a 'categories' dictionary."
            )

        self.categories = categories
        self._validate_config()

    @staticmethod
    def normalize_text(value: Optional[str]) -> str:
        """
        Normalize text for deterministic matching.

        Example:
            "Machine-Learning Engineer"
            -> "machine learning engineer"
        """

        if not value:
            return ""

        normalized = value.strip().lower()
        normalized = re.sub(r"[^a-z0-9+#./]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    def _validate_config(self) -> None:
        """Validate configured category names and structures."""

        for category_name, category_config in self.categories.items():
            try:
                JobCategory(category_name)
            except ValueError as exc:
                raise ValueError(
                    f"Unknown job category in roles.yaml: "
                    f"{category_name}"
                ) from exc

            if not isinstance(category_config, dict):
                raise ValueError(
                    f"Configuration for '{category_name}' "
                    "must be a dictionary."
                )

            titles = category_config.get("titles", [])
            keywords = category_config.get("keywords", [])

            if not isinstance(titles, list):
                raise ValueError(
                    f"Titles for '{category_name}' must be a list."
                )

            if not isinstance(keywords, list):
                raise ValueError(
                    f"Keywords for '{category_name}' must be a list."
                )

    def _enabled_categories(
        self,
    ) -> list[tuple[JobCategory, dict[str, Any]]]:
        """Return enabled configured categories."""

        enabled = []

        for category_name, config in self.categories.items():
            if config.get("enabled", True):
                enabled.append(
                    (
                        JobCategory(category_name),
                        config,
                    )
                )

        return enabled

    def _find_exact_title_match(
        self,
        job_title: str,
    ) -> Optional[ClassificationResult]:
        """Find an exact normalized configured-title match."""

        normalized_job_title = self.normalize_text(job_title)

        for category, config in self._enabled_categories():
            for configured_title in config.get("titles", []):
                normalized_configured_title = self.normalize_text(
                    str(configured_title)
                )

                if (
                    normalized_configured_title
                    and normalized_job_title
                    == normalized_configured_title
                ):
                    return ClassificationResult(
                        category=category,
                        confidence=self.TITLE_EXACT_CONFIDENCE,
                        reason="Exact configured title match.",
                        matched_title=str(configured_title),
                    )

        return None

    def _find_contained_title_match(
        self,
        job_title: str,
    ) -> Optional[ClassificationResult]:
        """
        Find configured titles contained in a longer title.

        The longest configured title wins. This reduces generic matches
        winning over more specific role names.
        """

        normalized_job_title = self.normalize_text(job_title)

        matches: list[
            tuple[int, JobCategory, str]
        ] = []

        for category, config in self._enabled_categories():
            for configured_title in config.get("titles", []):
                configured_title = str(configured_title)

                normalized_configured_title = self.normalize_text(
                    configured_title
                )

                if not normalized_configured_title:
                    continue

                pattern = (
                    r"(?<![a-z0-9])"
                    + re.escape(normalized_configured_title)
                    + r"(?![a-z0-9])"
                )

                if re.search(pattern, normalized_job_title):
                    matches.append(
                        (
                            len(normalized_configured_title),
                            category,
                            configured_title,
                        )
                    )

        if not matches:
            return None

        matches.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        _, category, configured_title = matches[0]

        return ClassificationResult(
            category=category,
            confidence=self.TITLE_CONTAINS_CONFIDENCE,
            reason="Configured title found within job title.",
            matched_title=configured_title,
        )

    def _keyword_classification(
        self,
        job: Job,
    ) -> ClassificationResult:
        """
        Use configured keyword evidence when title rules do not match.

        A category needs at least two distinct keyword matches. This is
        deliberately conservative because broad terms such as Python,
        SQL, AWS, and machine learning occur across multiple career tracks.
        """

        searchable_text = self.normalize_text(
            " ".join(
                part
                for part in [
                    job.title,
                    job.description or "",
                ]
                if part
            )
        )

        category_matches: list[
            tuple[int, JobCategory, tuple[str, ...]]
        ] = []

        for category, config in self._enabled_categories():
            matched_keywords = []

            for keyword in config.get("keywords", []):
                keyword = str(keyword)
                normalized_keyword = self.normalize_text(keyword)

                if not normalized_keyword:
                    continue

                pattern = (
                    r"(?<![a-z0-9])"
                    + re.escape(normalized_keyword)
                    + r"(?![a-z0-9])"
                )

                if re.search(pattern, searchable_text):
                    matched_keywords.append(keyword)

            unique_matches = tuple(
                dict.fromkeys(matched_keywords)
            )

            if len(unique_matches) >= 2:
                category_matches.append(
                    (
                        len(unique_matches),
                        category,
                        unique_matches,
                    )
                )

        if not category_matches:
            return ClassificationResult(
                category=JobCategory.OTHER,
                confidence=0.0,
                reason="Insufficient configured role evidence.",
            )

        category_matches.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        best_count, best_category, best_keywords = (
            category_matches[0]
        )

        # A tie is ambiguous, so do not guess.
        if (
            len(category_matches) > 1
            and category_matches[1][0] == best_count
        ):
            return ClassificationResult(
                category=JobCategory.OTHER,
                confidence=0.0,
                reason="Ambiguous keyword evidence across categories.",
            )

        confidence = min(
            0.5 + (best_count * 0.05),
            0.8,
        )

        return ClassificationResult(
            category=best_category,
            confidence=confidence,
            reason="Configured keyword evidence.",
            matched_keywords=best_keywords,
        )

    def classify(self, job: Job) -> ClassificationResult:
        """Classify a job without mutating it."""

        exact_match = self._find_exact_title_match(job.title)

        if exact_match is not None:
            return exact_match

        contained_match = self._find_contained_title_match(
            job.title
        )

        if contained_match is not None:
            return contained_match

        return self._keyword_classification(job)

    def classify_job(self, job: Job) -> Job:
        """
        Classify and update a Job object.

        The Job is returned so this method can later be composed into
        the processing pipeline.
        """

        result = self.classify(job)
        job.category = result.category

        return job