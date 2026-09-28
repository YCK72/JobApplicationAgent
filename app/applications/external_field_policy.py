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

    Ordinary profile-information questions may pass only when they are
    classified SAFE by ApplicationQuestionPolicy and use supported
    text-like, native SELECT, or native RADIO controls.

    FILE controls use a separate, narrower authorization path. Only
    controls whose semantic label identifies the candidate resume or CV
    exactly may pass this policy. Other uploads remain blocked.

    Unknown, review, sensitive, manual, and unsupported fields fail
    closed.

    This class does not generate answers, inspect pages, navigate, mutate
    browser controls, choose files, validate local files, bypass
    verification, or submit forms.
    """

    _SUPPORTED_FIELD_TYPES = {
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
        FormFieldType.SELECT,
        FormFieldType.RADIO,
    }

    _RESUME_FILE_LABELS = {
        "resume",
        "cv",
        "curriculum vitae",
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

        if field.field_type == FormFieldType.FILE:
            return self._authorize_resume_file(field.label)

        if field.field_type not in self._SUPPORTED_FIELD_TYPES:
            return self._blocked(
                "Field type is not permitted for external browser mutation."
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
                "External field uses a supported control type and is "
                "classified as safe ordinary candidate profile "
                "information."
            ),
        )

    def _authorize_resume_file(
        self,
        label: str,
    ) -> ExternalFieldPolicyResult:
        normalized_label = self._normalize_label(label)

        if normalized_label not in self._RESUME_FILE_LABELS:
            return self._blocked(
                "External FILE field is not explicitly identified as "
                "a resume or CV upload."
            )

        return ExternalFieldPolicyResult(
            status=ExternalFieldPolicyStatus.ALLOWED,
            reason=(
                "External FILE field is explicitly identified as a "
                "resume or CV upload."
            ),
        )

    @staticmethod
    def _normalize_label(
        value: str,
    ) -> str:
        """
        Normalize semantic labels only for conservative exact matching.

        Surrounding whitespace is ignored, internal whitespace is
        collapsed, and comparison is case-insensitive. No fuzzy,
        substring, alias expansion, or semantic guessing is performed.
        """
        return " ".join(value.split()).casefold()

    @staticmethod
    def _blocked(
        reason: str,
    ) -> ExternalFieldPolicyResult:
        return ExternalFieldPolicyResult(
            status=ExternalFieldPolicyStatus.BLOCKED,
            reason=reason,
        )