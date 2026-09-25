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

    1. Generic / non-job posting protection.
    2. Exact normalized configured-title match.
    3. Configured technical title contained within a longer job title.
    4. Explicit non-target occupation protection.
    5. Description/title keyword evidence.
    6. OTHER when there is insufficient evidence.

    Generic/non-job protection intentionally runs before technical
    title matching. A posting such as "Software Engineer Talent
    Community" contains a valid technical title, but it is not a
    specific vacancy and must not enter the application workflow.

    For actual job vacancies, technical title evidence is intentionally
    stronger than non-target occupation signals and keyword evidence.
    """

    TITLE_EXACT_CONFIDENCE = 1.0
    TITLE_CONTAINS_CONFIDENCE = 0.9

    def __init__(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ValueError(
                "Role configuration must be a dictionary."
            )

        categories = config.get("categories")

        if not isinstance(categories, dict):
            raise ValueError(
                "roles.yaml must contain a 'categories' dictionary."
            )

        self.categories = categories

        exclusions = config.get(
            "classification_exclusions",
            {},
        )

        if exclusions is None:
            exclusions = {}

        if not isinstance(exclusions, dict):
            raise ValueError(
                "'classification_exclusions' must be a dictionary."
            )

        non_target_titles = exclusions.get(
            "non_target_title_signals",
            [],
        )

        if not isinstance(non_target_titles, list):
            raise ValueError(
                "'classification_exclusions."
                "non_target_title_signals' must be a list."
            )

        self.non_target_title_signals = tuple(
            self.normalize_text(str(value))
            for value in non_target_titles
            if str(value).strip()
        )

        non_job_titles = exclusions.get(
            "non_job_title_signals",
            [],
        )

        if not isinstance(non_job_titles, list):
            raise ValueError(
                "'classification_exclusions."
                "non_job_title_signals' must be a list."
            )

        self.non_job_title_signals = tuple(
            self.normalize_text(str(value))
            for value in non_job_titles
            if str(value).strip()
        )

        self._validate_config()

    @staticmethod
    def normalize_text(
        value: Optional[str],
    ) -> str:
        """
        Normalize text for deterministic matching.

        Example:
            "Machine-Learning Engineer"
            -> "machine learning engineer"
        """

        if not value:
            return ""

        normalized = value.strip().lower()

        normalized = re.sub(
            r"[^a-z0-9+#./]+",
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
        """
        Return True when phrase appears with safe alphanumeric
        boundaries.
        """

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

    def _validate_config(self) -> None:
        """Validate configured category names and structures."""

        for (
            category_name,
            category_config,
        ) in self.categories.items():
            try:
                JobCategory(category_name)
            except ValueError as exc:
                raise ValueError(
                    "Unknown job category in roles.yaml: "
                    f"{category_name}"
                ) from exc

            if not isinstance(
                category_config,
                dict,
            ):
                raise ValueError(
                    f"Configuration for '{category_name}' "
                    "must be a dictionary."
                )

            titles = category_config.get(
                "titles",
                [],
            )

            keywords = category_config.get(
                "keywords",
                [],
            )

            if not isinstance(titles, list):
                raise ValueError(
                    f"Titles for '{category_name}' "
                    "must be a list."
                )

            if not isinstance(keywords, list):
                raise ValueError(
                    f"Keywords for '{category_name}' "
                    "must be a list."
                )

    def _enabled_categories(
        self,
    ) -> list[
        tuple[
            JobCategory,
            dict[str, Any],
        ]
    ]:
        """Return enabled configured categories."""

        enabled = []

        for (
            category_name,
            config,
        ) in self.categories.items():
            if config.get(
                "enabled",
                True,
            ):
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

        normalized_job_title = self.normalize_text(
            job_title
        )

        for (
            category,
            config,
        ) in self._enabled_categories():
            for configured_title in config.get(
                "titles",
                [],
            ):
                normalized_configured_title = (
                    self.normalize_text(
                        str(configured_title)
                    )
                )

                if (
                    normalized_configured_title
                    and normalized_job_title
                    == normalized_configured_title
                ):
                    return ClassificationResult(
                        category=category,
                        confidence=(
                            self.TITLE_EXACT_CONFIDENCE
                        ),
                        reason=(
                            "Exact configured title match."
                        ),
                        matched_title=str(
                            configured_title
                        ),
                    )

        return None

    def _find_contained_title_match(
        self,
        job_title: str,
    ) -> Optional[ClassificationResult]:
        """
        Find configured technical titles contained in a longer title.

        The longest configured title wins. This reduces generic matches
        winning over more specific role names.
        """

        normalized_job_title = self.normalize_text(
            job_title
        )

        matches: list[
            tuple[
                int,
                JobCategory,
                str,
            ]
        ] = []

        for (
            category,
            config,
        ) in self._enabled_categories():
            for configured_title in config.get(
                "titles",
                [],
            ):
                configured_title = str(
                    configured_title
                )

                normalized_configured_title = (
                    self.normalize_text(
                        configured_title
                    )
                )

                if not normalized_configured_title:
                    continue

                pattern = (
                    r"(?<![a-z0-9])"
                    + re.escape(
                        normalized_configured_title
                    )
                    + r"(?![a-z0-9])"
                )

                if re.search(
                    pattern,
                    normalized_job_title,
                ):
                    matches.append(
                        (
                            len(
                                normalized_configured_title
                            ),
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

        (
            _,
            category,
            configured_title,
        ) = matches[0]

        return ClassificationResult(
            category=category,
            confidence=(
                self.TITLE_CONTAINS_CONFIDENCE
            ),
            reason=(
                "Configured title found within job title."
            ),
            matched_title=configured_title,
        )

    def _find_non_target_title_signal(
        self,
        job_title: str,
    ) -> Optional[str]:
        """
        Find a configured title signal that clearly indicates a
        non-target occupation.

        This check intentionally uses only the job title. Description
        text may discuss sales, customers, marketing, recruiting, or
        other business functions even for legitimate engineering jobs.
        """

        normalized_title = self.normalize_text(
            job_title
        )

        for signal in self.non_target_title_signals:
            if self._contains_phrase(
                normalized_title,
                signal,
            ):
                return signal

        return None

    def _find_non_job_title_signal(
        self,
        job_title: str,
    ) -> Optional[str]:
        """
        Find a configured title signal indicating that the posting is
        not a specific job vacancy.

        Examples include talent communities, general applications,
        future-opportunity pools, and expressions of interest.
        """

        normalized_title = self.normalize_text(
            job_title
        )

        for signal in self.non_job_title_signals:
            if self._contains_phrase(
                normalized_title,
                signal,
            ):
                return signal

        return None

    def _keyword_classification(
        self,
        job: Job,
    ) -> ClassificationResult:
        """
        Use configured keyword evidence when title rules do not match.

        A category needs at least two distinct keyword matches. This is
        deliberately conservative because broad terms such as Python,
        SQL, AWS, and machine learning occur across multiple career
        tracks.
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
            tuple[
                int,
                JobCategory,
                tuple[str, ...],
            ]
        ] = []

        for (
            category,
            config,
        ) in self._enabled_categories():
            matched_keywords = []

            for keyword in config.get(
                "keywords",
                [],
            ):
                keyword = str(keyword)

                normalized_keyword = (
                    self.normalize_text(
                        keyword
                    )
                )

                if not normalized_keyword:
                    continue

                pattern = (
                    r"(?<![a-z0-9])"
                    + re.escape(
                        normalized_keyword
                    )
                    + r"(?![a-z0-9])"
                )

                if re.search(
                    pattern,
                    searchable_text,
                ):
                    matched_keywords.append(
                        keyword
                    )

            unique_matches = tuple(
                dict.fromkeys(
                    matched_keywords
                )
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
                reason=(
                    "Insufficient configured role evidence."
                ),
            )

        category_matches.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        (
            best_count,
            best_category,
            best_keywords,
        ) = category_matches[0]

        # A tie is ambiguous, so do not guess.
        if (
            len(category_matches) > 1
            and category_matches[1][0]
            == best_count
        ):
            return ClassificationResult(
                category=JobCategory.OTHER,
                confidence=0.0,
                reason=(
                    "Ambiguous keyword evidence "
                    "across categories."
                ),
            )

        confidence = min(
            0.5 + (best_count * 0.05),
            0.8,
        )

        return ClassificationResult(
            category=best_category,
            confidence=confidence,
            reason=(
                "Configured keyword evidence."
            ),
            matched_keywords=best_keywords,
        )

    def classify(
        self,
        job: Job,
    ) -> ClassificationResult:
        """Classify a job without mutating it."""

        # ----------------------------------------------------
        # 1. Generic / non-job posting protection
        # ----------------------------------------------------
        #
        # This intentionally runs before technical title matching.
        #
        # Example:
        #
        #     Software Engineer Talent Community
        #
        # contains a valid technical title, but is not a specific
        # vacancy and therefore must not enter the application
        # workflow.

        non_job_signal = (
            self._find_non_job_title_signal(
                job.title
            )
        )

        if non_job_signal is not None:
            return ClassificationResult(
                category=JobCategory.OTHER,
                confidence=1.0,
                reason=(
                    "Job title indicates a generic or "
                    "non-specific job posting."
                ),
                matched_title=non_job_signal,
            )

        # ----------------------------------------------------
        # 2. Exact technical title
        # ----------------------------------------------------

        exact_match = self._find_exact_title_match(
            job.title
        )

        if exact_match is not None:
            return exact_match

        # ----------------------------------------------------
        # 3. Technical title contained within a longer title
        # ----------------------------------------------------

        contained_match = (
            self._find_contained_title_match(
                job.title
            )
        )

        if contained_match is not None:
            return contained_match

        # ----------------------------------------------------
        # 4. Clearly non-target occupational title
        # ----------------------------------------------------
        #
        # This happens before keyword fallback so a sales,
        # recruiting, marketing, etc. posting cannot become a
        # technical role merely because its description discusses
        # technical products or technologies.

        non_target_signal = (
            self._find_non_target_title_signal(
                job.title
            )
        )

        if non_target_signal is not None:
            return ClassificationResult(
                category=JobCategory.OTHER,
                confidence=1.0,
                reason=(
                    "Job title contains a configured "
                    "non-target occupation signal."
                ),
                matched_title=non_target_signal,
            )

        # ----------------------------------------------------
        # 5. Conservative keyword fallback
        # ----------------------------------------------------

        return self._keyword_classification(
            job
        )

    def classify_job(
        self,
        job: Job,
    ) -> Job:
        """
        Classify and update a Job object.

        The Job is returned so this method can later be composed into
        the processing pipeline.
        """

        result = self.classify(
            job
        )

        job.category = result.category

        return job