from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.applications.resume_router import ResumeRouter
from app.jobs.classifier import RoleClassifier
from app.jobs.company_router import CompanyRouter
from app.jobs.deduplicator import (
    DuplicateReason,
    JobDeduplicator,
)
from app.jobs.filters import JobFilter
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)
from app.scoring.fit_gate import FitGate, FitTier
from app.scoring.fit_scorer import FitScorer
from app.tracking.database import JobDatabase


class PipelineOutcome(str, Enum):
    """
    Final outcome of processing one discovered job.
    """

    DUPLICATE = "DUPLICATE"
    FILTERED_OUT = "FILTERED_OUT"
    BLOCKED = "BLOCKED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    AUTO_READY = "AUTO_READY"


@dataclass(frozen=True)
class PipelineResult:
    """
    Structured result returned after processing one job.
    """

    job: Job
    outcome: PipelineOutcome
    reason: str
    job_id: Optional[int] = None
    duplicate_reason: Optional[DuplicateReason] = None

    @property
    def should_continue(self) -> bool:
        """
        Whether this job may later continue into the automatic
        application workflow.
        """

        return self.outcome == PipelineOutcome.AUTO_READY


class JobPipeline:
    """
    Deterministic job-processing and routing pipeline.

    Processing order:

        1. Company normalization/routing
        2. Duplicate detection
        3. Role classification
        4. Seniority / eligibility filtering
        5. Blocked-company protection
        6. Fit scoring
        7. Manual-company protection
        8. Fit-score gating for AUTO companies
        9. Resume routing for HIGH-fit AUTO jobs
        10. SQLite persistence

    This pipeline does NOT open a browser, fill application forms,
    or submit applications.
    """

    def __init__(
        self,
        *,
        company_router: CompanyRouter,
        classifier: RoleClassifier,
        job_filter: JobFilter,
        fit_scorer: FitScorer,
        fit_gate: FitGate,
        resume_router: ResumeRouter,
        database: JobDatabase,
    ) -> None:
        self.company_router = company_router
        self.classifier = classifier
        self.job_filter = job_filter
        self.fit_scorer = fit_scorer
        self.fit_gate = fit_gate
        self.resume_router = resume_router
        self.database = database

    @staticmethod
    def _append_note(
        job: Job,
        note: str,
    ) -> None:
        """
        Append a pipeline note without destroying existing notes.
        """

        if job.notes:
            job.notes = f"{job.notes}\n{note}"
        else:
            job.notes = note

    def _persist(
        self,
        job: Job,
    ) -> int:
        """
        Persist the fully processed job.

        SQLite remains the authoritative source of truth.
        """

        return self.database.add_job(job)

    def _find_duplicate(
        self,
        job: Job,
    ):
        """
        Compare the incoming job with jobs already stored in SQLite.
        """

        existing_jobs = self.database.get_all_jobs()

        return JobDeduplicator.find_duplicate(
            job,
            existing_jobs,
        )

    def process(
        self,
        job: Job,
    ) -> PipelineResult:
        """
        Process one discovered job through the complete
        deterministic intelligence and routing pipeline.
        """

        # -----------------------------------------------------
        # 1. Company normalization and routing
        # -----------------------------------------------------

        self.company_router.route_job(job)

        # -----------------------------------------------------
        # 2. Duplicate detection
        # -----------------------------------------------------

        duplicate_result = self._find_duplicate(job)

        if duplicate_result.is_duplicate:
            reason_text = (
                duplicate_result.reason.value
                if duplicate_result.reason
                else "UNKNOWN"
            )

            return PipelineResult(
                job=job,
                outcome=PipelineOutcome.DUPLICATE,
                reason=(
                    "Job matches an existing database record. "
                    f"Duplicate reason: {reason_text}."
                ),
                job_id=None,
                duplicate_reason=duplicate_result.reason,
            )

        # -----------------------------------------------------
        # 3. Role classification
        # -----------------------------------------------------

        self.classifier.classify_job(job)

        # -----------------------------------------------------
        # 4. Seniority / eligibility filtering
        # -----------------------------------------------------

        self.job_filter.filter_job(job)

        if job.status == ApplicationStatus.FILTERED_OUT:
            # A filtered job is still valuable tracking data.
            # Persist it rather than silently discarding it.
            job.resume_used = None

            job_id = self._persist(job)

            return PipelineResult(
                job=job,
                outcome=PipelineOutcome.FILTERED_OUT,
                reason=(
                    "Job was filtered out by role, seniority, "
                    "or location eligibility rules."
                ),
                job_id=job_id,
            )

        # -----------------------------------------------------
        # 5. Independent blocked-company protection
        # -----------------------------------------------------

        if job.company_rule == CompanyRule.BLOCKED:
            job.resume_used = None
            job.application_method = ApplicationMethod.UNKNOWN

            self._append_note(
                job,
                "Pipeline: blocked company; application workflow stopped.",
            )

            job_id = self._persist(job)

            return PipelineResult(
                job=job,
                outcome=PipelineOutcome.BLOCKED,
                reason=(
                    "Company rule is BLOCKED. "
                    "Application processing stopped."
                ),
                job_id=job_id,
            )

        # -----------------------------------------------------
        # 6. Fit scoring
        # -----------------------------------------------------

        self.fit_scorer.score_job(job)

        if job.fit_score is None:
            raise RuntimeError(
                "Fit scorer completed without assigning a fit score."
            )

        # -----------------------------------------------------
        # 7. Manual / priority company protection
        # -----------------------------------------------------

        if (
            job.company_rule == CompanyRule.MANUAL
            or job.priority_company
            or job.application_method == ApplicationMethod.MANUAL
        ):
            # Run through ResumeRouter as a second protection layer.
            # It must return no automatic resume for these jobs.
            resume_result = self.resume_router.route(job)

            if resume_result.resume_path is not None:
                raise RuntimeError(
                    "Safety violation: manual/priority company "
                    "received an automatic resume."
                )

            job.resume_used = None
            job.application_method = ApplicationMethod.MANUAL

            # NEEDS_REVIEW makes the job visible to the manual queue
            # while clearly preventing automatic application.
            job.status = ApplicationStatus.NEEDS_REVIEW

            self._append_note(
                job,
                "Pipeline: manual resume tailoring and application required.",
            )

            job_id = self._persist(job)

            return PipelineResult(
                job=job,
                outcome=PipelineOutcome.MANUAL_REVIEW,
                reason=(
                    "Priority/manual company saved for manual "
                    "resume tailoring and application."
                ),
                job_id=job_id,
            )

        # -----------------------------------------------------
        # 8. Fit-score gating for AUTO companies
        # -----------------------------------------------------

        if job.company_rule != CompanyRule.AUTO:
            raise RuntimeError(
                "Unexpected company rule reached fit gating: "
                f"{job.company_rule.value}"
            )

        fit_tier = self.fit_gate.evaluate(job.fit_score)

        if fit_tier == FitTier.LOW:
            job.resume_used = None
            job.application_method = ApplicationMethod.UNKNOWN
            job.status = ApplicationStatus.FILTERED_OUT

            self._append_note(
                job,
                (
                    "Pipeline: fit score below manual-review "
                    "threshold; automatic workflow stopped."
                ),
            )

            job_id = self._persist(job)

            return PipelineResult(
                job=job,
                outcome=PipelineOutcome.FILTERED_OUT,
                reason=(
                    f"Fit score {job.fit_score:.2f} is below the "
                    "manual-review threshold."
                ),
                job_id=job_id,
            )

        if fit_tier == FitTier.REVIEW:
            job.resume_used = None
            job.application_method = ApplicationMethod.REVIEW
            job.status = ApplicationStatus.NEEDS_REVIEW

            self._append_note(
                job,
                (
                    "Pipeline: fit score requires human review "
                    "before application routing."
                ),
            )

            job_id = self._persist(job)

            return PipelineResult(
                job=job,
                outcome=PipelineOutcome.MANUAL_REVIEW,
                reason=(
                    f"Fit score {job.fit_score:.2f} requires "
                    "human review before application."
                ),
                job_id=job_id,
            )

        if fit_tier != FitTier.HIGH:
            raise RuntimeError(
                f"Unexpected fit tier: {fit_tier.value}"
            )

        # -----------------------------------------------------
        # 9. HIGH-fit AUTO resume routing
        # -----------------------------------------------------

        if job.application_method != ApplicationMethod.AUTO:
            raise RuntimeError(
                "HIGH-fit AUTO company does not have AUTO "
                "application method."
            )

        self.resume_router.route_job(job)

        if not job.resume_used:
            raise RuntimeError(
                "HIGH-fit AUTO job reached application routing "
                "without an assigned resume."
            )

        # Browser automation does not exist in this milestone yet.
        # This means "ready for the future application workflow",
        # not "submitted".
        job.status = ApplicationStatus.NEEDS_APPLICATION

        self._append_note(
            job,
            (
                "Pipeline: HIGH-fit qualified AUTO job ready "
                "for application workflow."
            ),
        )

        # -----------------------------------------------------
        # 10. Persist final state
        # -----------------------------------------------------

        job_id = self._persist(job)

        return PipelineResult(
            job=job,
            outcome=PipelineOutcome.AUTO_READY,
            reason=(
                "HIGH-fit qualified AUTO job saved and ready "
                "for the future application workflow."
            ),
            job_id=job_id,
        )