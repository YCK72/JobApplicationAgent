from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.applications.answer_resolver import AnswerStatus
from app.applications.form_analyzer import (
    FieldAnalysis,
    FormAnalysisResult,
    FormSafetyStatus,
)
from app.applications.form_models import FormField


class FieldAction(str, Enum):
    """
    Explicit action permitted for one application field.
    """

    FILL_VERIFIED = "FILL_VERIFIED"
    SKIP_REVIEW = "SKIP_REVIEW"
    SKIP_MANUAL = "SKIP_MANUAL"


class FormPlanStatus(str, Enum):
    """
    Overall execution status of an application answer plan.
    """

    AUTO_FILL_ALLOWED = "AUTO_FILL_ALLOWED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


@dataclass(frozen=True)
class FieldPlan:
    """
    Browser-independent instruction for one application field.

    value carries verified string data for ordinary fields.

    desired_checked carries an explicitly resolved boolean state for a
    CHECKBOX field. It is modeled separately so checkbox state is never
    encoded through ambiguous strings such as "true", "false", "yes",
    or "on".

    This model represents planning intent only. A checkbox intent does
    not by itself authorize browser mutation or submission.
    """

    field: FormField
    action: FieldAction
    value: Optional[str]
    reason: str
    desired_checked: Optional[bool] = None

    @property
    def may_fill(self) -> bool:
        return (
            self.action == FieldAction.FILL_VERIFIED
            and self.value is not None
        )


@dataclass(frozen=True)
class FormAnswerPlan:
    """
    Complete browser-independent plan for an inspected form.

    This plan does not authorize submission.
    """

    fields: tuple[FieldPlan, ...]
    status: FormPlanStatus
    reason: str

    @property
    def may_auto_fill(self) -> bool:
        return self.status == FormPlanStatus.AUTO_FILL_ALLOWED

    @property
    def may_submit(self) -> bool:
        """
        Submission is deliberately prohibited at this layer.
        """
        return False


class ApplicationFormPlanner:
    """
    Converts analyzed application fields into explicit,
    deterministic field actions.

    The planner does not inspect raw questions, generate answers,
    interact with a browser, upload files, click controls, or
    submit applications.
    """

    def build_plan(
        self,
        analysis: FormAnalysisResult,
    ) -> FormAnswerPlan:
        field_plans = tuple(
            self._build_field_plan(field_analysis)
            for field_analysis in analysis.fields
        )

        status = self._map_form_status(
            analysis.status
        )

        return FormAnswerPlan(
            fields=field_plans,
            status=status,
            reason=analysis.reason,
        )

    def _build_field_plan(
        self,
        analysis: FieldAnalysis,
    ) -> FieldPlan:
        resolution = analysis.resolution

        if resolution.status == AnswerStatus.RESOLVED:
            if resolution.answer is None:
                return FieldPlan(
                    field=analysis.field,
                    action=FieldAction.SKIP_REVIEW,
                    value=None,
                    reason=(
                        "Resolved field has no verified answer; "
                        "automatic filling is not permitted."
                    ),
                )

            return FieldPlan(
                field=analysis.field,
                action=FieldAction.FILL_VERIFIED,
                value=resolution.answer,
                reason=resolution.reason,
            )

        if resolution.status == AnswerStatus.NEEDS_REVIEW:
            return FieldPlan(
                field=analysis.field,
                action=FieldAction.SKIP_REVIEW,
                value=None,
                reason=resolution.reason,
            )

        if resolution.status in {
            AnswerStatus.SENSITIVE,
            AnswerStatus.MANUAL,
        }:
            return FieldPlan(
                field=analysis.field,
                action=FieldAction.SKIP_MANUAL,
                value=None,
                reason=resolution.reason,
            )

        # Fail closed if a future AnswerStatus is introduced but
        # this planner has not yet been updated to understand it.
        return FieldPlan(
            field=analysis.field,
            action=FieldAction.SKIP_MANUAL,
            value=None,
            reason=(
                "Unknown answer-resolution status; manual "
                "handling is required."
            ),
        )

    def _map_form_status(
        self,
        status: FormSafetyStatus,
    ) -> FormPlanStatus:
        if status == FormSafetyStatus.AUTO_ANSWERABLE:
            return FormPlanStatus.AUTO_FILL_ALLOWED

        if status == FormSafetyStatus.NEEDS_REVIEW:
            return FormPlanStatus.REVIEW_REQUIRED

        return FormPlanStatus.MANUAL_REQUIRED