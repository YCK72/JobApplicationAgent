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
    FormFieldType,
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

        This does not authorize browser mutation or submission.
        """
        return self.status == FormSafetyStatus.AUTO_ANSWERABLE


class ApplicationFormAnalyzer:
    """
    Runs normalized application fields through the verified-answer
    safety system.

    For SELECT controls, a resolved verified answer is considered
    automatically usable only when it matches exactly one inspected
    option after conservative text normalization.

    This class performs analysis only. It does not interact with a
    browser, fill fields, select options, click controls, upload files,
    or submit applications.
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

        if (
            field.field_type == FormFieldType.SELECT
            and resolution.status == AnswerStatus.RESOLVED
        ):
            resolution = self._validate_select_resolution(
                field=field,
                resolution=resolution,
            )

        return FieldAnalysis(
            field=field,
            resolution=resolution,
        )

    @classmethod
    def _validate_select_resolution(
        cls,
        *,
        field: FormField,
        resolution: AnswerResolution,
    ) -> AnswerResolution:
        """
        Validate a resolved answer against inspected SELECT options.

        Matching is intentionally conservative:
        - surrounding whitespace is ignored,
        - internal whitespace is collapsed,
        - comparison is case-insensitive,
        - otherwise the option text must match exactly.

        No aliases, abbreviations, fuzzy matching, or semantic guessing
        are permitted.

        A successful match preserves the exact inspected option text.
        This does not authorize selecting the option in a browser.
        """
        if resolution.answer is None:
            return AnswerResolution(
                status=AnswerStatus.NEEDS_REVIEW,
                answer=None,
                reason=(
                    "SELECT field has no verified answer; "
                    "human review is required."
                ),
            )

        if not field.options:
            return AnswerResolution(
                status=AnswerStatus.NEEDS_REVIEW,
                answer=None,
                reason=(
                    "SELECT field has no inspected options; "
                    "deterministic option resolution is not possible."
                ),
            )

        normalized_answer = cls._normalize_option_text(
            resolution.answer
        )

        matches = [
            option
            for option in field.options
            if cls._normalize_option_text(option)
            == normalized_answer
        ]

        if len(matches) == 1:
            return AnswerResolution(
                status=AnswerStatus.RESOLVED,
                answer=matches[0],
                reason=(
                    "Verified answer matched exactly one inspected "
                    "SELECT option."
                ),
            )

        if not matches:
            return AnswerResolution(
                status=AnswerStatus.NEEDS_REVIEW,
                answer=None,
                reason=(
                    "Verified answer does not exactly match any "
                    "inspected SELECT option; human review is required."
                ),
            )

        return AnswerResolution(
            status=AnswerStatus.NEEDS_REVIEW,
            answer=None,
            reason=(
                "Verified answer matches multiple inspected SELECT "
                "options after normalization; human review is required."
            ),
        )

    @staticmethod
    def _normalize_option_text(
        value: str,
    ) -> str:
        """
        Normalize SELECT text only for conservative equality checking.
        """
        return " ".join(value.split()).casefold()