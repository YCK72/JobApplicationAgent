from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from app.applications.adapters.detector import ATSDetector, ATSProvider
from app.jobs.models import Job


class ApplicationTargetStatus(str, Enum):
    RESOLVED = "RESOLVED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    UNSUPPORTED = "UNSUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ApplicationTargetResult:
    status: ApplicationTargetStatus
    reason: str
    application_url: str | None = None
    provider: ATSProvider = ATSProvider.UNKNOWN


class ApplicationTargetResolver:
    """Validate explicit ATS application targets and fail closed.

    Resolution never follows redirects or searches arbitrary page text.  Only
    exact, HTTPS URLs on enabled ATS hosts are candidates.
    """

    def __init__(
        self,
        supported_providers: Iterable[ATSProvider] | None = None,
    ) -> None:
        self.supported_providers = frozenset(
            supported_providers
            if supported_providers is not None
            else {
                ATSProvider.GREENHOUSE,
                ATSProvider.LEVER,
                ATSProvider.ASHBY,
                ATSProvider.WORKDAY,
            }
        )

    def resolve(self, candidates: Iterable[object]) -> ApplicationTargetResult:
        supplied = [
            candidate
            for candidate in candidates
            if candidate is not None and candidate != ""
        ]
        if not supplied:
            return ApplicationTargetResult(
                status=ApplicationTargetStatus.MISSING,
                reason="No explicit application target was provided.",
            )

        valid: dict[str, ATSProvider] = {}
        saw_invalid = False
        saw_unsupported = False
        unsupported_provider = ATSProvider.UNKNOWN

        for candidate in supplied:
            canonical = self._canonical_url(candidate)
            if canonical is None:
                saw_invalid = True
                continue
            provider = ATSDetector.detect(canonical)
            if provider == ATSProvider.UNKNOWN:
                saw_invalid = True
                continue
            if (
                provider == ATSProvider.ASHBY
                and not self._is_ashby_application_path(canonical)
            ):
                saw_invalid = True
                continue
            if (
                provider == ATSProvider.WORKDAY
                and not self._is_workday_manual_application_path(canonical)
            ):
                saw_invalid = True
                continue
            if provider not in self.supported_providers:
                saw_unsupported = True
                unsupported_provider = provider
                continue
            valid[canonical] = provider

        if len(valid) > 1:
            return ApplicationTargetResult(
                status=ApplicationTargetStatus.AMBIGUOUS,
                reason="Multiple supported application targets were provided.",
            )
        if len(valid) == 1:
            application_url, provider = next(iter(valid.items()))
            return ApplicationTargetResult(
                status=ApplicationTargetStatus.RESOLVED,
                reason="Application target was validated.",
                application_url=application_url,
                provider=provider,
            )
        if saw_unsupported:
            return ApplicationTargetResult(
                status=ApplicationTargetStatus.UNSUPPORTED,
                reason="The application target uses an ATS that is not enabled.",
                provider=unsupported_provider,
            )
        if saw_invalid:
            return ApplicationTargetResult(
                status=ApplicationTargetStatus.INVALID,
                reason="The application target is invalid or is not a recognized ATS URL.",
            )
        return ApplicationTargetResult(
            status=ApplicationTargetStatus.MISSING,
            reason="No explicit application target was provided.",
        )

    @staticmethod
    def _canonical_url(value: object) -> str | None:
        if not isinstance(value, str) or not value.strip() or any(
            character.isspace() for character in value
        ):
            return None
        try:
            parsed = urlsplit(value.strip())
            if (
                parsed.scheme.lower() != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in {None, 443}
                or not parsed.path
                or parsed.path == "/"
            ):
                return None
        except ValueError:
            return None

        hostname = parsed.hostname.lower().rstrip(".")
        netloc = hostname
        return urlunsplit(("https", netloc, parsed.path, "", ""))

    @staticmethod
    def _is_ashby_application_path(url: str) -> bool:
        path_segments = [
            segment
            for segment in urlsplit(url).path.split("/")
            if segment
        ]
        return (
            len(path_segments) == 3
            and path_segments[-1].lower() == "application"
        )

    @staticmethod
    def _is_workday_manual_application_path(url: str) -> bool:
        path_segments = [
            segment
            for segment in urlsplit(url).path.split("/")
            if segment
        ]
        lowered = [segment.lower() for segment in path_segments]
        return (
            len(path_segments) >= 6
            and "job" in lowered[:-2]
            and lowered[-2:] == ["apply", "applymanually"]
        )


def resolve_job_application_target(job: Job) -> ApplicationTargetResult:
    """Resolve a job's dedicated target with safe known-ATS compatibility."""

    candidates: list[object] = []
    application_url = (
        job.application_url
        if isinstance(job, Job)
        else None
    )
    if isinstance(application_url, str):
        candidates.append(application_url)
    elif hasattr(application_url, "encoded_string"):
        candidates.append(application_url.encoded_string())
    else:
        source_url = getattr(job, "url", "")
        if hasattr(source_url, "encoded_string"):
            source_url = source_url.encoded_string()
        else:
            source_url = str(source_url)
        if ATSDetector.detect(source_url) != ATSProvider.UNKNOWN:
            candidates.append(source_url)
    return ApplicationTargetResolver().resolve(candidates)
