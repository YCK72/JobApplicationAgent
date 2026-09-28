from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.applications.checkbox_policy import (
    ApplicationCheckboxPolicy,
    CheckboxPolicy,
)
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

    value carries verified string data for ordinary executable fields.

    desired_checked carries an explicitly resolved boolean state for an
    authorized CHECKBOX field. Checkbox state is represented separately
    from value so boolean intent is never encoded through strings such as
    "true", "false", "yes", or "on".

    This object does not execute the action or authorize submission.
    """

    field: FormField
    value: str | None
    desired_checked: bool | None = None


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

    Supported authorization is narrowly scoped to:
    - verified text-like values,
    - deterministically resolved native SELECT values,
    - deterministically resolved native RADIO values,
    - explicitly authorized resume FILE paths,
    - explicitly resolved CHECKBOX boolean intent whose label matches the
      narrow checkbox semantic allowlist.

    FILE actions require an independently supplied resume path and must
    resolve to that exact path before execution authorization is granted.

    CHECKBOX authorization requires:
    - a CHECKBOX field,
    - no string value,
    - an explicit desired_checked boolean,
    - SAFE classification by ApplicationCheckboxPolicy.

    Checkbox authorization only permits the action to cross this planning
    boundary. It does not itself provide browser checkbox execution.

    This class performs authorization only. It does not fill fields,
    select options, attach files, toggle controls, click controls, press
    keys, bypass verification, or submit applications.

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
        FormFieldType.RADIO,
        FormFieldType.FILE,
    }

    def __init__(
        self,
        checkbox_policy: ApplicationCheckboxPolicy | None = None,
    ) -> None:
        self._checkbox_policy = (
            checkbox_policy or ApplicationCheckboxPolicy()
        )

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

            if field_plan.field.field_type == FormFieldType.CHECKBOX:
                checkbox_action = self._authorize_checkbox(
                    field_plan=field_plan,
                )

                if checkbox_action is None:
                    return self._blocked(
                        "CHECKBOX action is not explicitly authorized "
                        "for controlled browser execution."
                    )

                actions.append(checkbox_action)
                continue

            if field_plan.desired_checked is not None:
                return self._blocked(
                    "Non-CHECKBOX field contains checkbox intent."
                )

            if not field_plan.may_fill:
                return self._blocked(
                    "Verified fill action is not eligible for automatic "
                    "browser execution."
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
                    desired_checked=None,
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

    def _authorize_checkbox(
        self,
        *,
        field_plan,
    ) -> AuthorizedFieldAction | None:
        """
        Authorize one typed CHECKBOX action.

        Semantic safety and desired boolean intent are independent:
        a SAFE checkbox label never manufactures a checked state.

        This method authorizes representation only. It does not mutate
        browser state.
        """

        if field_plan.value is not None:
            return None

        if not isinstance(field_plan.desired_checked, bool):
            return None

        policy_result = self._checkbox_policy.classify(
            field_plan.field.label
        )

        if policy_result.policy != CheckboxPolicy.SAFE:
            return None

        return AuthorizedFieldAction(
            field=field_plan.field,
            value=None,
            desired_checked=field_plan.desired_checked,
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