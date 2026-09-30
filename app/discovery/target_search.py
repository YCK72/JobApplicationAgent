from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from app.applications.adapters.detector import ATSProvider
from app.applications.target_resolver import (
    ApplicationTargetResolver,
    ApplicationTargetStatus,
)


class TargetSearchClient(Protocol):
    def search(self, query: str) -> dict[str, Any]: ...


class TargetSearchStatus(str, Enum):
    RESOLVED = "RESOLVED"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class TargetSearchResult:
    status: TargetSearchStatus
    reason: str
    application_url: str | None = None
    provider: ATSProvider = ATSProvider.UNKNOWN


class ApplicationTargetSearchResolver:
    """Find one exact, supported ATS target from bounded search evidence.

    Search summaries are treated only as candidate evidence. A result is
    accepted when its visible title contains both the complete normalized
    company name and job title and its URL passes the existing strict ATS
    target validator. Multiple exact matches fail closed.
    """

    def __init__(self, *, client: TargetSearchClient) -> None:
        self._client = client
        self._target_resolver = ApplicationTargetResolver()

    def resolve(self, *, company: str, title: str) -> TargetSearchResult:
        if not isinstance(company, str) or not company.strip():
            raise ValueError("company must not be empty")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title must not be empty")

        query = f'"{title.strip()}" "{company.strip()}" apply'
        try:
            payload = self._client.search(query)
        except Exception:
            return TargetSearchResult(
                status=TargetSearchStatus.UNAVAILABLE,
                reason="Application-target search was unavailable.",
            )

        citations = self._citations(payload)
        if citations is None:
            return TargetSearchResult(
                status=TargetSearchStatus.UNAVAILABLE,
                reason="Application-target search returned an invalid response.",
            )

        company_key = self._normalize(company)
        title_key = self._normalize(title)
        matches: dict[str, ATSProvider] = {}
        for item in citations:
            if not isinstance(item, dict):
                continue
            evidence = " ".join(
                value
                for value in (
                    item.get("title"),
                    item.get("name"),
                    item.get("snippet"),
                    item.get("description"),
                )
                if isinstance(value, str)
            )
            evidence_key = self._normalize(evidence)
            if company_key not in evidence_key or title_key not in evidence_key:
                continue
            target = self._target_resolver.resolve(
                [item.get("url") or item.get("id") or item.get("link")]
            )
            if (
                target.status == ApplicationTargetStatus.RESOLVED
                and target.application_url is not None
            ):
                matches[target.application_url] = target.provider

        if len(matches) == 1:
            application_url, provider = next(iter(matches.items()))
            return TargetSearchResult(
                status=TargetSearchStatus.RESOLVED,
                reason=(
                    "One exact company-and-title match was validated on a "
                    "supported ATS host."
                ),
                application_url=application_url,
                provider=provider,
            )
        if len(matches) > 1:
            return TargetSearchResult(
                status=TargetSearchStatus.AMBIGUOUS,
                reason=(
                    "Multiple exact supported application targets were found; "
                    "manual review is required."
                ),
            )
        return TargetSearchResult(
            status=TargetSearchStatus.MISSING,
            reason=(
                "No exact company-and-title match on a supported ATS host "
                "was found."
            ),
        )

    @staticmethod
    def _citations(payload: object) -> list[object] | None:
        if not isinstance(payload, dict):
            return None
        result = payload.get("results", payload)
        if not isinstance(result, dict):
            return None
        citations = result.get("citations")
        if citations in (None, []) and "organic_results" in result:
            citations = result["organic_results"]
        return citations if isinstance(citations, list) else None

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
