from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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
    One field action explicitly authorized to cross the future
    browser-mutation boundary.

    This object does not execute the action.
    """

    field: FormField
    value: str


@dataclass(frozen=True)
class FormExecutionPlan:
    """
    Validated execution authorization derived from a FormAnswerPlan.

    This object does not interact with a browser and never authorizes
    application submission.
    """

    actions: tuple[AuthorizedFieldAction, ...]
    status: ExecutionPlanStatus
    reason: str

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
    Validate whether a FormAnswerPlan may cross the future browser
    execution boundary.

    This milestone performs authorization only. It does not fill,
    select, click, upload files, press keys, bypass verification,
    or submit applications.

    Unknown, unsupported, review, and manual cases fail closed.
    """

    _SUPPORTED_FIELD_TYPES = {
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
    }

    def authorize(
        self,
        plan: FormAnswerPlan,
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
                "for future browser execution."
            ),
        )

    @staticmethod
    def _blocked(
        reason: str,
    ) -> FormExecutionPlan:
        return FormExecutionPlan(
            actions=(),
            status=ExecutionPlanStatus.BLOCKED,
            reason=reason,
        )