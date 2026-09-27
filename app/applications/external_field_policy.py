from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.applications.form_executor import AuthorizedFieldAction
from app.applications.form_models import FormFieldType
from app.applications.question_policy import (
    ApplicationQuestionPolicy,
    QuestionPolicy,
)


class ExternalFieldPolicyStatus(str, Enum):
    """
    Execution-time policy result for one external form field.
    """

    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ExternalFieldPolicyResult:
    """
    Result of checking whether one already-authorized field action may
    cross the external browser-mutation boundary.

    This result never authorizes submission.
    """

    status: ExternalFieldPolicyStatus
    reason: str

    @property
    def may_mutate(self) -> bool:
        return self.status == ExternalFieldPolicyStatus.ALLOWED

    @property
    def may_submit(self) -> bool:
        return False


class ExternalFieldExecutionPolicy:
    """
    Defense-in-depth policy for external browser field mutation.

    The normal planning pipeline must already have resolved values from
    verified candidate data. This policy independently rechecks the
    semantic field label immediately before external mutation.

    Only ordinary profile-information questions that are classified SAFE
    by ApplicationQuestionPolicy and use supported text-like controls may
    pass.

    Unknown, review, sensitive, manual, and unsupported fields fail closed.

    This class does not generate answers, inspect pages, navigate, click,
    select options, upload files, bypass verification, or submit forms.
    """

    _SUPPORTED_FIELD_TYPES = {
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
    }

    def __init__(
        self,
        question_policy: ApplicationQuestionPolicy | None = None,
    ) -> None:
        self._question_policy = (
            question_policy
            if question_policy is not None
            else ApplicationQuestionPolicy()
        )

    def authorize(
        self,
        action: AuthorizedFieldAction,
    ) -> ExternalFieldPolicyResult:
        field = action.field

        if field.field_type not in self._SUPPORTED_FIELD_TYPES:
            return self._blocked(
                "Field type is not permitted for external browser mutation."
            )

        if not isinstance(action.value, str):
            return self._blocked(
                "External field value must be a verified string."
            )

        if not action.value.strip():
            return self._blocked(
                "External field value must not be empty."
            )

        if not isinstance(field.label, str):
            return self._blocked(
                "External field label must be a string."
            )

        if not field.label.strip():
            return self._blocked(
                "External field label is missing."
            )

        try:
            policy_result = self._question_policy.classify(
                field.label
            )
        except (TypeError, ValueError):
            return self._blocked(
                "External field label could not be safely classified."
            )

        if policy_result.policy != QuestionPolicy.SAFE:
            return self._blocked(
                "External field is not classified as safe ordinary "
                "candidate profile information."
            )

        return ExternalFieldPolicyResult(
            status=ExternalFieldPolicyStatus.ALLOWED,
            reason=(
                "External field is a supported text-like control "
                "classified as safe ordinary candidate profile "
                "information."
            ),
        )

    @staticmethod
    def _blocked(
        reason: str,
    ) -> ExternalFieldPolicyResult:
        return ExternalFieldPolicyResult(
            status=ExternalFieldPolicyStatus.BLOCKED,
            reason=reason,
        )