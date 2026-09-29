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
from app.jobs.eligibility import JobEligibilityGate, EligibilityStatus
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
        6. Candidate eligibility (stop mismatches or unresolved requirements)
        7. Fit scoring
        8. Manual-company protection
        9. Fit-score gating for AUTO companies
        10. Resume routing for HIGH-fit AUTO jobs
        11. SQLite persistence

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
        eligibility_gate: JobEligibilityGate | None = None,
    ) -> None:
        self.company_router = company_router
        self.classifier = classifier
        self.job_filter = job_filter
        self.fit_scorer = fit_scorer
        self.fit_gate = fit_gate
        self.resume_router = resume_router
        self.database = database
        self.eligibility_gate = (
            eligibility_gate
            if eligibility_gate is not None
            else JobEligibilityGate()
        )

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
        existing_job_id: int | None = None,
    ) -> int:
        """
        Persist the fully processed job.

        SQLite remains the authoritative source of truth.
        """

        if existing_job_id is None:
            return self.database.add_job(job)
        self.database.update_job(existing_job_id, job)
        return existing_job_id

    def _find_duplicate(
        self,
        job: Job,
        existing_job_id: int | None = None,
    ):
        """
        Compare the incoming job with jobs already stored in SQLite.
        """

        existing_jobs = [
            existing_job
            for job_id, existing_job in self.database.get_jobs_with_ids()
            if job_id != existing_job_id
        ]

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

        return self._process(job, existing_job_id=None)

    def reprocess(self, job_id: int, job: Job) -> PipelineResult:
        """Run a reviewed persisted job again without creating a new row."""

        if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
            raise ValueError("job_id must be a positive integer")
        stored = self.database.get_job_by_id(job_id)
        if stored is None:
            raise ValueError(f"Job ID {job_id} does not exist.")
        if stored.url.encoded_string() != job.url.encoded_string():
            raise ValueError("Reprocessed job URL does not match the persisted job.")

        job.status = ApplicationStatus.DISCOVERED
        job.fit_score = None
        job.fit_explanation = None
        job.resume_used = None
        return self._process(job, existing_job_id=job_id)

    def _process(
        self,
        job: Job,
        *,
        existing_job_id: int | None,
    ) -> PipelineResult:
        """Process a new record or replace one explicitly selected record."""

        # -----------------------------------------------------
        # 1. Company normalization and routing
        # -----------------------------------------------------

        self.company_router.route_job(job)

        # -----------------------------------------------------
        # 2. Duplicate detection
        # -----------------------------------------------------

        duplicate_result = self._find_duplicate(job, existing_job_id)

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

            job_id = self._persist(job, existing_job_id)

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

            job_id = self._persist(job, existing_job_id)

            return PipelineResult(
                job=job,
                outcome=PipelineOutcome.BLOCKED,
                reason=(
                    "Company rule is BLOCKED. "
                    "Application processing stopped."
                ),
                job_id=job_id,
            )

        eligibility = self.eligibility_gate.evaluate(job)
        if eligibility.status != EligibilityStatus.CLEAR:
            job.resume_used = None
            job.fit_score = None
            job.fit_explanation = None
            review = eligibility.status == EligibilityStatus.NEEDS_REVIEW
            job.status = (
                ApplicationStatus.NEEDS_REVIEW
                if review
                else ApplicationStatus.FILTERED_OUT
            )
            job.application_method = (
                ApplicationMethod.REVIEW
                if review
                else ApplicationMethod.UNKNOWN
            )
            self._append_note(job, f"Eligibility: {eligibility.reason}")
            return PipelineResult(
                job=job,
                outcome=(
                    PipelineOutcome.MANUAL_REVIEW
                    if review
                    else PipelineOutcome.FILTERED_OUT
                ),
                reason=eligibility.reason,
                job_id=self._persist(job, existing_job_id),
            )

        # LinkedIn is a discovery page, not an application endpoint.  Keep
        # unresolved listings visible, but stop before scoring and resume
        # routing until an explicit supported ATS target has been verified.
        if job.source == "linkedin_composio" and job.application_url is None:
            job.resume_used = None
            job.fit_score = None
            job.fit_explanation = None
            job.status = ApplicationStatus.NEEDS_REVIEW
            job.application_method = ApplicationMethod.REVIEW
            reason = (
                "No verified supported ATS application target was found for "
                "this LinkedIn listing."
            )
            self._append_note(job, f"Application target: {reason}")
            return PipelineResult(
                job=job,
                outcome=PipelineOutcome.MANUAL_REVIEW,
                reason=reason,
                job_id=self._persist(job, existing_job_id),
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

            job_id = self._persist(job, existing_job_id)

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

            job_id = self._persist(job, existing_job_id)

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

            job_id = self._persist(job, existing_job_id)

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

        job_id = self._persist(job, existing_job_id)

        return PipelineResult(
            job=job,
            outcome=PipelineOutcome.AUTO_READY,
            reason=(
                "HIGH-fit qualified AUTO job saved and ready "
                "for the future application workflow."
            ),
            job_id=job_id,
        )
