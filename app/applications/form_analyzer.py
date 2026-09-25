from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.applications.answer_resolver import (
    AnswerResolution,
    AnswerStatus,
    ApplicationAnswerResolver,
)
from app.applications.form_models import (
    ApplicationForm,
    FormField,
)


class FormSafetyStatus(str, Enum):
    """
    Overall safety decision for an inspected application form.
    """

    AUTO_ANSWERABLE = "AUTO_ANSWERABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


@dataclass(frozen=True)
class FieldAnalysis:
    """
    Safety analysis for one normalized application field.
    """

    field: FormField
    resolution: AnswerResolution

    @property
    def can_auto_answer(self) -> bool:
        return (
            self.resolution.status
            == AnswerStatus.RESOLVED
            and self.resolution.answer is not None
        )


@dataclass(frozen=True)
class FormAnalysisResult:
    """
    Structured safety analysis for an entire application form.
    """

    form: ApplicationForm
    fields: tuple[FieldAnalysis, ...]
    status: FormSafetyStatus
    reason: str

    @property
    def can_auto_fill(self) -> bool:
        """
        Whether every inspected field has a verified,
        automatically usable answer.

        This does not authorize submission.
        """
        return self.status == FormSafetyStatus.AUTO_ANSWERABLE


class ApplicationFormAnalyzer:
    """
    Runs normalized application fields through the verified-answer
    safety system.

    This class performs analysis only. It does not interact with a
    browser, fill fields, click controls, upload files, or submit
    applications.
    """

    def __init__(
        self,
        answer_resolver: ApplicationAnswerResolver,
    ) -> None:
        self.answer_resolver = answer_resolver

    def analyze(
        self,
        form: ApplicationForm,
    ) -> FormAnalysisResult:
        analyses = tuple(
            self._analyze_field(field)
            for field in form.fields
        )

        if any(
            analysis.resolution.status
            in {
                AnswerStatus.SENSITIVE,
                AnswerStatus.MANUAL,
            }
            for analysis in analyses
        ):
            return FormAnalysisResult(
                form=form,
                fields=analyses,
                status=FormSafetyStatus.MANUAL_REQUIRED,
                reason=(
                    "At least one application field requires "
                    "manual handling."
                ),
            )

        if any(
            analysis.resolution.status
            == AnswerStatus.NEEDS_REVIEW
            for analysis in analyses
        ):
            return FormAnalysisResult(
                form=form,
                fields=analyses,
                status=FormSafetyStatus.NEEDS_REVIEW,
                reason=(
                    "At least one application field requires "
                    "human review."
                ),
            )

        return FormAnalysisResult(
            form=form,
            fields=analyses,
            status=FormSafetyStatus.AUTO_ANSWERABLE,
            reason=(
                "All inspected application fields have verified "
                "automatic answers."
            ),
        )

    def _analyze_field(
        self,
        field: FormField,
    ) -> FieldAnalysis:
        resolution = self.answer_resolver.resolve(
            field.label
        )

        return FieldAnalysis(
            field=field,
            resolution=resolution,
        )