from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.applications.external_field_policy import (
    ExternalFieldExecutionPolicy,
)
from app.applications.form_executor import (
    AuthorizedFieldAction,
    ApplicationFormExecutor,
    ExecutionPlanStatus,
    FormExecutionPlan,
)
from app.applications.form_models import ApplicationForm
from app.applications.form_plan import (
    FieldAction,
    FormAnswerPlan,
)


class DryRunFieldStatus(str, Enum):
    WOULD_FILL = "WOULD_FILL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"
    BLOCKED_EXTERNAL_POLICY = "BLOCKED_EXTERNAL_POLICY"


@dataclass(frozen=True)
class DryRunFieldResult:
    field_id: str
    label: str
    field_type: str
    required: bool
    status: DryRunFieldStatus
    value: Optional[str]
    reason: str

    @property
    def would_fill(self) -> bool:
        return self.status == DryRunFieldStatus.WOULD_FILL


@dataclass(frozen=True)
class ApplicationDryRunReport:
    provider: str
    job_url: str
    fields: tuple[DryRunFieldResult, ...]
    execution_status: ExecutionPlanStatus
    execution_reason: str

    @property
    def would_execute(self) -> bool:
        return self.execution_status == ExecutionPlanStatus.AUTHORIZED

    @property
    def may_submit(self) -> bool:
        return False

    @property
    def would_fill_count(self) -> int:
        return sum(
            field.would_fill
            for field in self.fields
        )


class ApplicationDryRunReporter:
    """
    Build a deterministic, browser-independent report describing what
    the existing application pipeline would permit.

    The reporter does not navigate, inspect DOM state, fill fields,
    click controls, select options, upload files, bypass verification,
    mutate persistence, or submit applications.

    Whole-form execution authorization remains authoritative. Per-field
    WOULD_FILL results are diagnostic only and must never be interpreted
    as permission to partially execute a blocked form.
    """

    def __init__(
        self,
        form_executor: ApplicationFormExecutor | None = None,
        external_field_policy: ExternalFieldExecutionPolicy | None = None,
    ) -> None:
        self._form_executor = (
            form_executor
            if form_executor is not None
            else ApplicationFormExecutor()
        )
        self._external_field_policy = (
            external_field_policy
            if external_field_policy is not None
            else ExternalFieldExecutionPolicy()
        )

    def build_report(
        self,
        form: ApplicationForm,
        plan: FormAnswerPlan,
    ) -> ApplicationDryRunReport:
        execution_plan = self._form_executor.authorize(plan)

        field_results = tuple(
            self._build_field_result(field_plan)
            for field_plan in plan.fields
        )

        return ApplicationDryRunReport(
            provider=str(form.provider),
            job_url=str(form.job_url),
            fields=field_results,
            execution_status=execution_plan.status,
            execution_reason=execution_plan.reason,
        )

    def _build_field_result(
        self,
        field_plan,
    ) -> DryRunFieldResult:
        field = field_plan.field

        if field_plan.action == FieldAction.SKIP_MANUAL:
            return self._result(
                field_plan=field_plan,
                status=DryRunFieldStatus.MANUAL_REQUIRED,
                value=None,
            )

        if field_plan.action == FieldAction.SKIP_REVIEW:
            return self._result(
                field_plan=field_plan,
                status=DryRunFieldStatus.REVIEW_REQUIRED,
                value=None,
            )

        if (
            field_plan.action != FieldAction.FILL_VERIFIED
            or not field_plan.may_fill
            or field_plan.value is None
        ):
            return self._result(
                field_plan=field_plan,
                status=DryRunFieldStatus.MANUAL_REQUIRED,
                value=None,
                reason=(
                    "Field does not contain an explicit verified "
                    "fill action."
                ),
            )

        action = AuthorizedFieldAction(
            field=field,
            value=field_plan.value,
        )

        external_authorization = (
            self._external_field_policy.authorize(action)
        )

        if not external_authorization.may_mutate:
            return self._result(
                field_plan=field_plan,
                status=DryRunFieldStatus.BLOCKED_EXTERNAL_POLICY,
                value=None,
                reason=external_authorization.reason,
            )

        if external_authorization.may_submit:
            return self._result(
                field_plan=field_plan,
                status=DryRunFieldStatus.BLOCKED_EXTERNAL_POLICY,
                value=None,
                reason=(
                    "External field policy unexpectedly "
                    "authorizes submission."
                ),
            )

        return self._result(
            field_plan=field_plan,
            status=DryRunFieldStatus.WOULD_FILL,
            value=field_plan.value,
        )

    @staticmethod
    def _result(
        *,
        field_plan,
        status: DryRunFieldStatus,
        value: Optional[str],
        reason: Optional[str] = None,
    ) -> DryRunFieldResult:
        field = field_plan.field

        return DryRunFieldResult(
            field_id=field.field_id,
            label=field.label,
            field_type=field.field_type.value,
            required=field.required,
            status=status,
            value=value,
            reason=reason or field_plan.reason,
        )