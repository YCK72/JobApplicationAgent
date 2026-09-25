from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.jobs.models import (
    ApplicationStatus,
    Job,
    JobCategory,
    SeniorityLevel,
)


@dataclass(frozen=True)
class FitScoreResult:
    score: float
    explanation: str
    matched_skills: tuple[str, ...]
    category_matches: tuple[str, ...]


class FitScorer:
    """
    Deterministic job-fit scorer.

    The scorer measures how strongly a surviving job matches the
    candidate's verified profile. It does NOT decide whether to apply.
    """

    CATEGORY_SKILL_GROUPS = {
        JobCategory.SDE: (
            "languages",
            "backend_systems",
            "frontend",
            "databases",
            "cloud",
            "devops_infrastructure",
            "observability_reliability",
            "engineering_practices",
        ),
        JobCategory.AI_ML: (
            "languages",
            "machine_learning",
            "nlp_llm",
            "data",
            "cloud",
            "devops_infrastructure",
            "databases",
        ),
        JobCategory.DATA_SCIENCE: (
            "languages",
            "machine_learning",
            "data",
            "nlp_llm",
            "databases",
            "cloud",
        ),
        JobCategory.IT: (
            "languages",
            "cloud",
            "devops_infrastructure",
            "observability_reliability",
            "databases",
            "backend_systems",
        ),
    }

    CATEGORY_CORE_GROUPS = {
        JobCategory.SDE: (
            "backend_systems",
            "frontend",
            "engineering_practices",
        ),
        JobCategory.AI_ML: (
            "machine_learning",
            "nlp_llm",
        ),
        JobCategory.DATA_SCIENCE: (
            "machine_learning",
            "data",
        ),
        JobCategory.IT: (
            "cloud",
            "devops_infrastructure",
            "observability_reliability",
        ),
    }

    SENIORITY_SCORES = {
        SeniorityLevel.ENTRY_LEVEL: 15.0,
        SeniorityLevel.EARLY_CAREER: 15.0,
        SeniorityLevel.UNKNOWN: 8.0,
        SeniorityLevel.MID_LEVEL: 0.0,
        SeniorityLevel.SENIOR: 0.0,
    }

    def __init__(self, candidate_config: dict[str, Any]) -> None:
        if not isinstance(candidate_config, dict):
            raise ValueError(
                "Candidate configuration must be a dictionary."
            )

        candidate = candidate_config.get("candidate")

        if not isinstance(candidate, dict):
            raise ValueError(
                "candidate.yaml must contain a 'candidate' dictionary."
            )

        skills = candidate.get("skills")

        if not isinstance(skills, dict) or not skills:
            raise ValueError(
                "candidate.yaml must contain a non-empty "
                "'candidate.skills' dictionary."
            )

        self.skills = self._validate_skills(skills)

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if not value:
            return ""

        text = value.lower()

        # Normalize common punctuation without destroying
        # technology names such as C++ or CI/CD.
        text = text.replace("–", "-")
        text = text.replace("—", "-")
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    @staticmethod
    def _normalize_skill(skill: str) -> str:
        normalized = skill.lower().strip()

        aliases = {
            "rest api": "rest api",
            "scikit-learn": "scikit-learn",
            "machine learning": "machine learning",
            "deep learning": "deep learning",
            "distributed systems": "distributed systems",
            "system design": "system design",
            "feature engineering": "feature engineering",
            "statistical testing": "statistical testing",
            "prompt engineering": "prompt engineering",
            "explainable ai": "explainable ai",
            "github actions": "github actions",
        }

        return aliases.get(normalized, normalized)

    @staticmethod
    def _skill_pattern(skill: str) -> str:
        """
        Build a conservative regex for a skill.

        Boundaries prevent matches such as:
            R -> "required"
            Go -> "Google"

        while still allowing punctuation-heavy skills such as:
            C++
            CI/CD
            Node.js
        """

        escaped = re.escape(skill)

        return (
            r"(?<![a-z0-9])"
            + escaped
            + r"(?![a-z0-9])"
        )

    def _skill_in_text(
        self,
        skill: str,
        text: str,
    ) -> bool:
        normalized_skill = self._normalize_skill(skill)

        return (
            re.search(
                self._skill_pattern(normalized_skill),
                text,
                flags=re.IGNORECASE,
            )
            is not None
        )

    @staticmethod
    def _validate_skills(
        skills: dict[str, Any],
    ) -> dict[str, tuple[str, ...]]:
        validated: dict[str, tuple[str, ...]] = {}

        for group_name, values in skills.items():
            if not isinstance(values, list):
                raise ValueError(
                    f"Skill group '{group_name}' must be a list."
                )

            cleaned: list[str] = []

            for value in values:
                if not isinstance(value, str):
                    raise ValueError(
                        f"Skill values in '{group_name}' "
                        "must be strings."
                    )

                value = value.strip()

                if value:
                    cleaned.append(value)

            validated[group_name] = tuple(cleaned)

        return validated

    def _get_relevant_skills(
        self,
        category: JobCategory,
    ) -> dict[str, tuple[str, ...]]:
        groups = self.CATEGORY_SKILL_GROUPS.get(
            category,
            (),
        )

        return {
            group: self.skills.get(group, ())
            for group in groups
        }

    def _find_matches(
        self,
        category: JobCategory,
        text: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        relevant = self._get_relevant_skills(category)

        matched_skills: list[str] = []
        matched_core_groups: set[str] = set()

        core_groups = set(
            self.CATEGORY_CORE_GROUPS.get(
                category,
                (),
            )
        )

        seen: set[str] = set()

        for group, skills in relevant.items():
            for skill in skills:
                normalized = self._normalize_skill(skill)

                if normalized in seen:
                    continue

                if self._skill_in_text(skill, text):
                    matched_skills.append(skill)
                    seen.add(normalized)

                    if group in core_groups:
                        matched_core_groups.add(group)

        return (
            tuple(matched_skills),
            tuple(sorted(matched_core_groups)),
        )

    @staticmethod
    def _skill_score(
        match_count: int,
    ) -> float:
        """
        General technical match component: maximum 50 points.

        Diminishing returns prevent huge keyword-heavy job
        descriptions from dominating the score.
        """

        if match_count <= 0:
            return 0.0

        return min(
            50.0,
            match_count * 6.25,
        )

    def _core_category_score(
        self,
        category: JobCategory,
        matched_core_groups: tuple[str, ...],
    ) -> float:
        """
        Category-specific evidence component: maximum 25 points.
        """

        core_groups = self.CATEGORY_CORE_GROUPS.get(
            category,
            (),
        )

        if not core_groups:
            return 0.0

        coverage = (
            len(matched_core_groups)
            / len(core_groups)
        )

        return round(coverage * 25.0, 2)

    def score(self, job: Job) -> FitScoreResult:
        if job.category == JobCategory.OTHER:
            return FitScoreResult(
                score=0.0,
                explanation=(
                    "Fit score is 0 because the job is not in "
                    "a supported target category."
                ),
                matched_skills=(),
                category_matches=(),
            )

        if job.status == ApplicationStatus.FILTERED_OUT:
            return FitScoreResult(
                score=0.0,
                explanation=(
                    "Fit score is 0 because the job was filtered "
                    "out before fit scoring."
                ),
                matched_skills=(),
                category_matches=(),
            )

        text = self._normalize_text(
            f"{job.title} {job.description or ''}"
        )

        matched_skills, matched_core_groups = (
            self._find_matches(
                job.category,
                text,
            )
        )

        # 10 points simply for surviving classification into
        # one of the supported target categories.
        role_score = 10.0

        skill_score = self._skill_score(
            len(matched_skills)
        )

        category_score = self._core_category_score(
            job.category,
            matched_core_groups,
        )

        seniority_score = self.SENIORITY_SCORES.get(
            job.seniority,
            0.0,
        )

        total = min(
            100.0,
            role_score
            + skill_score
            + category_score
            + seniority_score,
        )

        total = round(total, 2)

        if matched_skills:
            skill_text = ", ".join(matched_skills)
        else:
            skill_text = "None"

        if matched_core_groups:
            core_text = ", ".join(matched_core_groups)
        else:
            core_text = "None"

        explanation = (
            f"Category: {job.category.value}. "
            f"Seniority: {job.seniority.value}. "
            f"Matched {len(matched_skills)} verified skills: "
            f"{skill_text}. "
            f"Matched category-specific groups: {core_text}. "
            f"Components — role: {role_score:.1f}, "
            f"skills: {skill_score:.1f}, "
            f"category: {category_score:.1f}, "
            f"seniority: {seniority_score:.1f}."
        )

        return FitScoreResult(
            score=total,
            explanation=explanation,
            matched_skills=matched_skills,
            category_matches=matched_core_groups,
        )

    def score_job(self, job: Job) -> Job:
        """
        Score a Job and update its existing fit fields.
        """

        result = self.score(job)

        job.fit_score = result.score
        job.fit_explanation = result.explanation

        return job