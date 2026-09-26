from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.applications.adapters.detector import (
    ATSDetector,
    ATSProvider,
)
from app.applications.form_models import (
    ApplicationForm,
)


@dataclass(frozen=True)
class FormValidationResult:
    valid: bool
    reason: str


class ApplicationFormValidator:
    """
    Validates normalized adapter output before it enters the
    application safety/answer system.

    This validator does not inspect browser state, resolve answers,
    fill fields, or submit applications.
    """

    PROVIDER_NAMES = {
        ATSProvider.GREENHOUSE: "greenhouse",
        ATSProvider.LEVER: "lever",
        ATSProvider.ASHBY: "ashby",
        ATSProvider.WORKDAY: "workday",
    }

    def validate(
        self,
        form: ApplicationForm,
        expected_provider: ATSProvider,
        expected_job_url: str,
    ) -> FormValidationResult:
        if expected_provider == ATSProvider.UNKNOWN:
            return FormValidationResult(
                valid=False,
                reason=(
                    "Cannot validate a form against an UNKNOWN "
                    "ATS provider."
                ),
            )

        expected_name = self.PROVIDER_NAMES.get(
            expected_provider
        )

        if expected_name is None:
            return FormValidationResult(
                valid=False,
                reason="Unsupported ATS provider.",
            )

        if form.provider.strip().lower() != expected_name:
            return FormValidationResult(
                valid=False,
                reason=(
                    "Adapter form provider does not match the "
                    "detected ATS provider."
                ),
            )

        form_provider = ATSDetector.detect(
            form.job_url
        )

        if form_provider != expected_provider:
            return FormValidationResult(
                valid=False,
                reason=(
                    "Adapter form URL does not match the "
                    "detected ATS provider."
                ),
            )

        if not self._same_job_location(
            expected_job_url,
            form.job_url,
        ):
            return FormValidationResult(
                valid=False,
                reason=(
                    "Adapter returned a form for a different "
                    "job URL."
                ),
            )

        return FormValidationResult(
            valid=True,
            reason="Application form identity is valid.",
        )

    @staticmethod
    def _same_job_location(
        expected_url: str,
        actual_url: str,
    ) -> bool:
        try:
            expected = urlparse(expected_url)
            actual = urlparse(actual_url)
        except ValueError:
            return False

        expected_host = (
            expected.hostname.lower()
            if expected.hostname
            else None
        )
        actual_host = (
            actual.hostname.lower()
            if actual.hostname
            else None
        )

        if expected_host != actual_host:
            return False

        expected_path = expected.path.rstrip("/")
        actual_path = actual.path.rstrip("/")

        return expected_path == actual_path