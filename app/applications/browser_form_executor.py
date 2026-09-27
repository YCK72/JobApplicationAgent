from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.applications.form_executor import (
    FormExecutionPlan,
)
from app.applications.form_models import FormFieldType
from app.browser.form_writer import BrowserFieldWriter


class BrowserExecutionStatus(str, Enum):
    """
    Outcome of attempting an authorized browser execution plan.
    """

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BrowserExecutionResult:
    """
    Result of browser-side field execution.

    Submission is never authorized by this result.
    """

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
    Execute an already-authorized FormExecutionPlan through a narrow
    BrowserFieldWriter boundary.

    This class cannot navigate, click arbitrary controls, upload files,
    bypass human verification, or submit applications.
    """

    _TEXT_FIELD_TYPES = {
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
    }

    def __init__(
        self,
        writer: BrowserFieldWriter,
    ) -> None:
        self.writer = writer

    def execute(
        self,
        plan: FormExecutionPlan,
    ) -> BrowserExecutionResult:
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
            if action.field.field_type not in self._TEXT_FIELD_TYPES:
                return BrowserExecutionResult(
                    status=BrowserExecutionStatus.BLOCKED,
                    completed_actions=completed_actions,
                    reason=(
                        "Execution plan contains an unsupported "
                        "browser field type."
                    ),
                )

            try:
                self.writer.write_text(
                    field=action.field,
                    value=action.value,
                )
            except Exception as exc:
                return BrowserExecutionResult(
                    status=BrowserExecutionStatus.FAILED,
                    completed_actions=completed_actions,
                    reason=(
                        "Browser field execution failed: "
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

    @staticmethod
    def _blocked(
        reason: str,
    ) -> BrowserExecutionResult:
        return BrowserExecutionResult(
            status=BrowserExecutionStatus.BLOCKED,
            completed_actions=0,
            reason=reason,
        )