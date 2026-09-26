from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.applications.adapters.detector import (
    ATSDetector,
    ATSProvider,
)
from app.applications.adapters.registry import (
    AdapterNotAvailableError,
    ApplicationAdapterRegistry,
)
from app.applications.form_analyzer import (
    ApplicationFormAnalyzer,
)
from app.applications.form_models import (
    ApplicationForm,
)
from app.applications.form_plan import (
    ApplicationFormPlanner,
    FormAnswerPlan,
    FormPlanStatus,
)
from app.applications.form_validator import (
    ApplicationFormValidator,
)
from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.tracking.database import JobDatabase


class InspectionOutcome(str, Enum):
    INSPECTED = "INSPECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


@dataclass(frozen=True)
class InspectionResult:
    job: Job
    outcome: InspectionOutcome
    reason: str

    provider: ATSProvider = ATSProvider.UNKNOWN
    form: Optional[ApplicationForm] = None
    plan: Optional[FormAnswerPlan] = None

    @property
    def inspection_succeeded(self) -> bool:
        return (
            self.outcome == InspectionOutcome.INSPECTED
            and self.form is not None
            and self.plan is not None
        )


class ApplicationInspectionService:
    """
    Orchestrates application-form inspection and persists review
    transitions.

    Responsibilities:
        1. Require READY_TO_APPLY lifecycle state.
        2. Require a persisted job ID.
        3. Detect the ATS from the requested job URL.
        4. Select an explicitly registered adapter.
        5. Inspect and normalize the application form.
        6. Validate adapter output against the requested job.
        7. Run validated form data through the safety analyzer.
        8. Build a deterministic answer plan.
        9. Persist NEEDS_REVIEW when automatic continuation is
           not permitted.

    This service does not fill fields, upload files, click controls,
    bypass human verification, or submit applications.
    """

    def __init__(
        self,
        registry: ApplicationAdapterRegistry,
        analyzer: ApplicationFormAnalyzer,
        planner: ApplicationFormPlanner,
        database: JobDatabase,
        form_validator: ApplicationFormValidator,
    ) -> None:
        self.registry = registry
        self.analyzer = analyzer
        self.planner = planner
        self.database = database
        self.form_validator = form_validator

    def inspect(
        self,
        job: Job,
        job_id: Optional[int],
    ) -> InspectionResult:
        if job.status != ApplicationStatus.READY_TO_APPLY:
            return InspectionResult(
                job=job,
                outcome=InspectionOutcome.NOT_ELIGIBLE,
                reason=(
                    "Job must be READY_TO_APPLY before "
                    "application inspection."
                ),
            )

        if job_id is None:
            return InspectionResult(
                job=job,
                outcome=InspectionOutcome.NOT_ELIGIBLE,
                reason=(
                    "Persisted job ID is required before "
                    "application inspection."
                ),
            )

        provider = ATSDetector.detect(
            str(job.url)
        )

        if provider == ATSProvider.UNKNOWN:
            reason = (
                "Application ATS could not be identified safely."
            )

            self._move_to_review(
                job=job,
                job_id=job_id,
                reason=reason,
            )

            return InspectionResult(
                job=job,
                outcome=InspectionOutcome.NEEDS_REVIEW,
                reason=reason,
                provider=provider,
            )

        try:
            adapter = self.registry.get(provider)

        except AdapterNotAvailableError as exc:
            reason = str(exc)

            self._move_to_review(
                job=job,
                job_id=job_id,
                reason=reason,
            )

            return InspectionResult(
                job=job,
                outcome=InspectionOutcome.NEEDS_REVIEW,
                reason=reason,
                provider=provider,
            )

        form = adapter.inspect()

        validation = self.form_validator.validate(
            form=form,
            expected_provider=provider,
            expected_job_url=str(job.url),
        )

        if not validation.valid:
            reason = validation.reason

            self._move_to_review(
                job=job,
                job_id=job_id,
                reason=reason,
            )

            return InspectionResult(
                job=job,
                outcome=InspectionOutcome.NEEDS_REVIEW,
                reason=reason,
                provider=provider,
                form=form,
            )

        analysis = self.analyzer.analyze(form)

        plan = self.planner.build_plan(
            analysis
        )

        if plan.status in {
            FormPlanStatus.REVIEW_REQUIRED,
            FormPlanStatus.MANUAL_REQUIRED,
        }:
            reason = (
                "Application form requires human review before "
                "automatic continuation."
            )

            self._move_to_review(
                job=job,
                job_id=job_id,
                reason=reason,
            )

            return InspectionResult(
                job=job,
                outcome=InspectionOutcome.NEEDS_REVIEW,
                reason=reason,
                provider=provider,
                form=form,
                plan=plan,
            )

        return InspectionResult(
            job=job,
            outcome=InspectionOutcome.INSPECTED,
            reason=(
                "Application form was inspected, validated, "
                "and all fields are eligible for verified "
                "automatic filling."
            ),
            provider=provider,
            form=form,
            plan=plan,
        )

    def _move_to_review(
        self,
        job: Job,
        job_id: int,
        reason: str,
    ) -> None:
        original_status = job.status
        original_notes = job.notes

        new_notes = self._append_note(
            existing=original_notes,
            message=reason,
        )

        job.status = ApplicationStatus.NEEDS_REVIEW
        job.notes = new_notes

        try:
            self.database.update_application_state(
                job_id=job_id,
                status=job.status,
                notes=job.notes,
            )

        except Exception:
            job.status = original_status
            job.notes = original_notes
            raise

    @staticmethod
    def _append_note(
        existing: Optional[str],
        message: str,
    ) -> str:
        if existing and existing.strip():
            return (
                f"{existing.rstrip()}\n"
                f"{message}"
            )

        return message