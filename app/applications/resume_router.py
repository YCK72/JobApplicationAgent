from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.jobs.models import (
    ApplicationMethod,
    CompanyRule,
    Job,
    JobCategory,
)


@dataclass(frozen=True)
class ResumeRoutingResult:
    """
    Result of determining which resume should be used for a job.
    """

    resume_path: Optional[str]
    resume_key: Optional[str]
    manual_tailoring_required: bool
    reason: str


class ResumeRouter:
    """
    Selects the appropriate resume for a job.

    Priority/manual companies are intentionally prevented from
    receiving an automatically selected submission resume.
    """

    CATEGORY_TO_RESUME = {
        JobCategory.SDE: "sde",
        JobCategory.AI_ML: "ai_ml",
        JobCategory.DATA_SCIENCE: "data_science",
        JobCategory.IT: "it",
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

        resumes = candidate.get("resumes")

        if not isinstance(resumes, dict) or not resumes:
            raise ValueError(
                "candidate.yaml must contain a non-empty "
                "'candidate.resumes' dictionary."
            )

        self.resumes = self._validate_resumes(resumes)

    @staticmethod
    def _validate_resumes(
        resumes: dict[str, Any],
    ) -> dict[str, str]:
        validated: dict[str, str] = {}

        for key, value in resumes.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"Resume path '{key}' must be a string."
                )

            cleaned = value.strip()

            if not cleaned:
                raise ValueError(
                    f"Resume path '{key}' cannot be empty."
                )

            validated[key] = cleaned

        return validated

    def _get_resume_path(
        self,
        resume_key: str,
    ) -> str:
        resume_path = self.resumes.get(resume_key)

        if not resume_path:
            raise ValueError(
                f"No resume configured for '{resume_key}'."
            )

        return resume_path

    def route(
        self,
        job: Job,
    ) -> ResumeRoutingResult:
        """
        Determine the resume routing decision without modifying the job.
        """

        # Safety rule:
        # MANUAL companies must be manually tailored.
        if (
            job.company_rule == CompanyRule.MANUAL
            or job.priority_company
            or job.application_method == ApplicationMethod.MANUAL
        ):
            return ResumeRoutingResult(
                resume_path=None,
                resume_key=None,
                manual_tailoring_required=True,
                reason=(
                    "Manual/priority company requires resume "
                    "tailoring before application."
                ),
            )

        # BLOCKED companies should never receive a resume.
        if job.company_rule == CompanyRule.BLOCKED:
            return ResumeRoutingResult(
                resume_path=None,
                resume_key=None,
                manual_tailoring_required=False,
                reason=(
                    "Company is blocked from the application workflow."
                ),
            )

        resume_key = self.CATEGORY_TO_RESUME.get(
            job.category
        )

        if resume_key is None:
            return ResumeRoutingResult(
                resume_path=None,
                resume_key=None,
                manual_tailoring_required=False,
                reason=(
                    f"No automatic resume route exists for "
                    f"category {job.category.value}."
                ),
            )

        resume_path = self._get_resume_path(
            resume_key
        )

        return ResumeRoutingResult(
            resume_path=resume_path,
            resume_key=resume_key,
            manual_tailoring_required=False,
            reason=(
                f"Selected '{resume_key}' resume for "
                f"{job.category.value} role."
            ),
        )

    def route_job(
        self,
        job: Job,
    ) -> Job:
        """
        Apply resume routing to a Job.

        Manual, blocked, and unsupported jobs receive no automatic
        resume assignment.
        """

        result = self.route(job)

        job.resume_used = result.resume_path

        return job

    def resume_exists(
        self,
        job: Job,
    ) -> bool:
        """
        Check whether the automatically routed resume exists locally.

        This does not apply to manual-tailoring jobs.
        """

        result = self.route(job)

        if result.resume_path is None:
            return False

        return Path(result.resume_path).is_file()