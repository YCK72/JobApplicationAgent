from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.applications.form_models import (
    FormField,
    FormFieldType,
)
from app.applications.form_plan import (
    FieldAction,
    FormAnswerPlan,
    FormPlanStatus,
)


class ExecutionPlanStatus(str, Enum):
    """
    Overall authorization status for browser-side form execution.
    """

    AUTHORIZED = "AUTHORIZED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class AuthorizedFieldAction:
    """
    One field action explicitly authorized to cross the browser-mutation
    boundary.

    This object does not execute the action.
    """

    field: FormField
    value: str


@dataclass(frozen=True)
class FormExecutionPlan:
    """
    Validated execution authorization derived from a FormAnswerPlan.

    authorized_resume_path records the exact normalized resume path that
    FILE execution is permitted to use. It remains None when the plan
    contains no authorized resume upload.

    This object does not interact with a browser and never authorizes
    application submission.
    """

    actions: tuple[AuthorizedFieldAction, ...]
    status: ExecutionPlanStatus
    reason: str
    authorized_resume_path: str | None = None

    @property
    def may_execute(self) -> bool:
        return self.status == ExecutionPlanStatus.AUTHORIZED

    @property
    def may_submit(self) -> bool:
        """
        Submission remains prohibited at this layer.
        """
        return False


class ApplicationFormExecutor:
    """
    Validate whether a FormAnswerPlan may cross the browser execution
    boundary.

    Supported actions remain narrowly scoped to:
    - verified text-like values,
    - deterministically resolved native SELECT values,
    - explicitly authorized resume FILE paths.

    FILE actions require an independently supplied resume path and must
    resolve to that exact path before execution authorization is granted.

    This class performs authorization only. It does not fill fields,
    select options, attach files, click controls, press keys, bypass
    verification, or submit applications.

    External targets receive additional execution-time policy checks
    before mutation. FILE mutation therefore remains blocked externally
    unless an independent external policy explicitly authorizes it.

    Unknown, unsupported, review, and manual cases fail closed.
    """

    _SUPPORTED_FIELD_TYPES = {
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
        FormFieldType.SELECT,
        FormFieldType.FILE,
    }

    def authorize(
        self,
        plan: FormAnswerPlan,
        *,
        authorized_resume_path: str | None = None,
    ) -> FormExecutionPlan:
        if plan.status != FormPlanStatus.AUTO_FILL_ALLOWED:
            return self._blocked(
                "Form plan does not authorize automatic filling."
            )

        if not plan.may_auto_fill:
            return self._blocked(
                "Form plan does not permit automatic filling."
            )

        if plan.may_submit:
            return self._blocked(
                "Form plan unexpectedly authorizes submission."
            )

        actions: list[AuthorizedFieldAction] = []
        normalized_resume_path: str | None = None

        for field_plan in plan.fields:
            if field_plan.action != FieldAction.FILL_VERIFIED:
                return self._blocked(
                    "Form contains a field that is not explicitly "
                    "authorized for verified automatic filling."
                )

            if not field_plan.may_fill:
                return self._blocked(
                    "Verified fill action does not contain an "
                    "authorized value."
                )

            if field_plan.value is None:
                return self._blocked(
                    "Verified fill action is missing its value."
                )

            if field_plan.field.field_type not in (
                self._SUPPORTED_FIELD_TYPES
            ):
                return self._blocked(
                    "Form contains a field type that is not yet "
                    "supported for browser execution."
                )

            if field_plan.field.field_type == FormFieldType.FILE:
                if authorized_resume_path is None:
                    return self._blocked(
                        "FILE action does not have an independently "
                        "authorized resume path."
                    )

                try:
                    requested_path = self._normalize_path(
                        field_plan.value
                    )
                    permitted_path = self._normalize_path(
                        authorized_resume_path
                    )
                except (TypeError, ValueError, OSError):
                    return self._blocked(
                        "Resume path could not be safely normalized."
                    )

                if requested_path != permitted_path:
                    return self._blocked(
                        "FILE action does not match the independently "
                        "authorized resume path."
                    )

                normalized_resume_path = permitted_path

            actions.append(
                AuthorizedFieldAction(
                    field=field_plan.field,
                    value=field_plan.value,
                )
            )

        return FormExecutionPlan(
            actions=tuple(actions),
            status=ExecutionPlanStatus.AUTHORIZED,
            reason=(
                "All planned field actions are verified and supported "
                "for controlled browser execution."
            ),
            authorized_resume_path=normalized_resume_path,
        )

    @staticmethod
    def _normalize_path(
        value: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError("Resume path must be a string.")

        cleaned = value.strip()

        if not cleaned:
            raise ValueError("Resume path must not be empty.")

        return str(
            Path(cleaned).expanduser().resolve(strict=False)
        )

    @staticmethod
    def _blocked(
        reason: str,
    ) -> FormExecutionPlan:
        return FormExecutionPlan(
            actions=(),
            status=ExecutionPlanStatus.BLOCKED,
            reason=reason,
            authorized_resume_path=None,
        )