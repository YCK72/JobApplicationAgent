from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.applications.execution_guard import (
    ExecutionTargetAuthorization,
    ExternalExecutionGuard,
)
from app.applications.external_field_policy import (
    ExternalFieldExecutionPolicy,
)
from app.applications.form_executor import FormExecutionPlan
from app.applications.form_models import FormFieldType
from app.browser.form_writer import BrowserFieldWriter


class BrowserExecutionStatus(str, Enum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BrowserExecutionResult:
    status: BrowserExecutionStatus
    completed_actions: int
    reason: str

    @property
    def succeeded(self) -> bool:
        return self.status == BrowserExecutionStatus.COMPLETED

    @property
    def may_submit(self) -> bool:
        return False


class BrowserFormExecutor:
    """
    Executes only previously authorized browser field actions.

    External HTTP/HTTPS mutation receives an additional execution-time
    semantic field-policy check.

    Local controlled fixture execution may perform:
    - verified text-like mutation,
    - deterministic native SELECT mutation,
    - controlled native FILE attachment.

    External SELECT mutation remains prohibited unless the independent
    external field policy explicitly authorizes it.

    External FILE mutation remains prohibited because the independent
    external field policy does not authorize FILE controls.

    This executor does not navigate, arbitrarily click controls, bypass
    verification, or submit applications.
    """

    _TEXT_FIELD_TYPES = {
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
    }

    _SUPPORTED_FIELD_TYPES = (
        _TEXT_FIELD_TYPES
        | {
            FormFieldType.SELECT,
            FormFieldType.FILE,
        }
    )

    def __init__(
        self,
        writer: BrowserFieldWriter,
        external_field_policy: ExternalFieldExecutionPolicy | None = None,
    ) -> None:
        self._writer = writer
        self._external_field_policy = (
            external_field_policy
            if external_field_policy is not None
            else ExternalFieldExecutionPolicy()
        )

    def execute(
        self,
        plan: FormExecutionPlan,
        target_authorization: ExecutionTargetAuthorization,
    ) -> BrowserExecutionResult:
        if not target_authorization.may_mutate:
            return self._blocked(
                "Execution target is not authorized for browser mutation."
            )

        if target_authorization.may_submit:
            return self._blocked(
                "Execution target unexpectedly authorizes submission."
            )

        if target_authorization.target_url is None:
            return self._blocked(
                "Execution target authorization is not bound to a URL."
            )

        target_error = self._target_error(
            target_authorization.target_url
        )

        if target_error is not None:
            return self._blocked(target_error)

        if not plan.may_execute:
            return self._blocked(
                "Execution plan is not authorized."
            )

        if plan.may_submit:
            return self._blocked(
                "Execution plan unexpectedly authorizes submission."
            )

        completed_actions = 0

        for action in plan.actions:
            target_error = self._target_error(
                target_authorization.target_url
            )

            if target_error is not None:
                return BrowserExecutionResult(
                    status=BrowserExecutionStatus.BLOCKED,
                    completed_actions=completed_actions,
                    reason=target_error,
                )

            if action.field.field_type not in self._SUPPORTED_FIELD_TYPES:
                return BrowserExecutionResult(
                    status=BrowserExecutionStatus.BLOCKED,
                    completed_actions=completed_actions,
                    reason=(
                        "Execution plan contains a field type that "
                        "is not supported for browser mutation."
                    ),
                )

            if self._is_external_target(
                target_authorization.target_url
            ):
                field_authorization = (
                    self._external_field_policy.authorize(action)
                )

                if not field_authorization.may_mutate:
                    return BrowserExecutionResult(
                        status=BrowserExecutionStatus.BLOCKED,
                        completed_actions=completed_actions,
                        reason=field_authorization.reason,
                    )

                if field_authorization.may_submit:
                    return BrowserExecutionResult(
                        status=BrowserExecutionStatus.BLOCKED,
                        completed_actions=completed_actions,
                        reason=(
                            "External field policy unexpectedly "
                            "authorizes submission."
                        ),
                    )

            try:
                self._execute_action(action)
            except Exception as exc:
                return BrowserExecutionResult(
                    status=BrowserExecutionStatus.FAILED,
                    completed_actions=completed_actions,
                    reason=(
                        "Browser field mutation failed: "
                        f"{exc}"
                    ),
                )

            completed_actions += 1

        return BrowserExecutionResult(
            status=BrowserExecutionStatus.COMPLETED,
            completed_actions=completed_actions,
            reason=(
                "All authorized browser field actions completed."
            ),
        )

    def _execute_action(
        self,
        action,
    ) -> None:
        if action.field.field_type in self._TEXT_FIELD_TYPES:
            self._writer.write_text(
                field=action.field,
                value=action.value,
            )
            return

        if action.field.field_type == FormFieldType.SELECT:
            self._writer.select_option(
                field=action.field,
                value=action.value,
            )
            return

        if action.field.field_type == FormFieldType.FILE:
            self._writer.upload_file(
                field=action.field,
                file_path=action.value,
            )
            return

        raise ValueError(
            "Authorized action contains an unsupported field type."
        )

    def _target_error(
        self,
        authorized_target_url: str,
    ) -> str | None:
        try:
            current_url = ExternalExecutionGuard.normalize_target_url(
                self._writer.current_url
            )
        except (TypeError, ValueError):
            return (
                "Current browser target could not be safely normalized."
            )

        if current_url != authorized_target_url:
            return (
                "Current browser target does not match the "
                "authorized execution target."
            )

        return None

    @staticmethod
    def _is_external_target(
        target_url: str,
    ) -> bool:
        return target_url.startswith(
            ("http://", "https://")
        )

    @staticmethod
    def _blocked(
        reason: str,
    ) -> BrowserExecutionResult:
        return BrowserExecutionResult(
            status=BrowserExecutionStatus.BLOCKED,
            completed_actions=0,
            reason=reason,
        )