from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.applications.adapters.detector import ATSProvider
from app.applications.target_resolver import (
    ApplicationTargetResolver,
    ApplicationTargetStatus,
)


_INACTIVE_STATUSES = {
    "APPLIED",
    "REJECTED",
    "OFFER",
    "WITHDRAWN",
    "FILTERED_OUT",
}


def build_review_queue_item(
    job: Mapping[str, Any],
) -> dict[str, bool | str | None]:
    """Return a deterministic, display-safe review summary for one job."""

    status = _text(job.get("status"))
    application_method = _text(job.get("application_method"))
    company_rule = _text(job.get("company_rule"))
    application_url = job.get("application_url")

    if status in _INACTIVE_STATUSES:
        return _not_required()

    if status == "SUBMISSION_UNCONFIRMED":
        return _required(
            "SUBMISSION_UNCONFIRMED",
            "Submission needs independent confirmation evidence before "
            "the application can be marked applied.",
        )

    if status == "FORM_STARTED":
        return _required(
            "FORM_REVIEW",
            "Application fields were filled. Review the form and submit manually.",
        )

    if status == "ERROR":
        return _required(
            "APPLICATION_ERROR",
            "Application processing failed. Review the recorded error before retrying.",
        )

    if status == "NEEDS_REVIEW":
        if not isinstance(application_url, str) or not application_url.strip():
            return _required(
                "TARGET_REQUIRED",
                "A verified application target is missing. Review the source "
                "listing and assign an exact supported ATS application URL.",
            )

        target = ApplicationTargetResolver().resolve([application_url])
        if target.status != ApplicationTargetStatus.RESOLVED:
            return _required(
                "INVALID_TARGET",
                "The saved application URL is not a valid supported ATS target. "
                "Review and replace it before continuing.",
            )

        if target.provider == ATSProvider.WORKDAY:
            return _required(
                "WORKDAY_MULTI_STEP",
                "Workday hides later application steps. Complete and review this "
                "application manually.",
            )

        if company_rule == "MANUAL" or application_method == "MANUAL":
            return _required(
                "MANUAL_APPLICATION",
                "Company policy requires this application to be handled manually.",
            )

        return _required(
            "PIPELINE_REVIEW",
            "The application pipeline requires review. Check the job notes "
            "before continuing.",
        )

    if company_rule == "MANUAL" or application_method == "MANUAL":
        return _required(
            "MANUAL_APPLICATION",
            "Company policy requires this application to be handled manually.",
        )

    return _not_required()


def _text(value: Any) -> str:
    return value.strip().upper() if isinstance(value, str) else ""


def _required(kind: str, reason: str) -> dict[str, bool | str | None]:
    return {
        "review_required": True,
        "review_kind": kind,
        "review_reason": reason,
    }


def _not_required() -> dict[str, bool | str | None]:
    return {
        "review_required": False,
        "review_kind": None,
        "review_reason": None,
    }
