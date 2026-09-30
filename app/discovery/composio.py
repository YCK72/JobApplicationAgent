"""Bounded public LinkedIn discovery through Composio, independent of chat sessions."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import html
import math
import os
import re
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bs4 import BeautifulSoup

from app.discovery.base import JobSource, RawJobPosting
from app.applications.target_resolver import ApplicationTargetResolver
from app.discovery.target_search import (
    ApplicationTargetSearchResolver,
    TargetSearchStatus,
)
from app.jobs.models import Job


class ComposioDiscoveryError(RuntimeError):
    """A sanitized transport or response-contract failure."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the project API key to a redirected host.
        return None


class SearchClient(Protocol):
    def search(self, query: str) -> dict[str, Any]: ...
    def fetch(self, urls: list[str]) -> dict[str, Any]: ...


class LinkedInAvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    CLOSED = "CLOSED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class LinkedInAvailabilityResult:
    status: LinkedInAvailabilityStatus
    reason: str


class LinkedInAvailabilityChecker(Protocol):
    def check(self, url: str) -> LinkedInAvailabilityResult: ...


_CLOSED_POSTING_MARKERS = (
    "no longer accepting applications",
    "this job is no longer available",
    "this job posting is no longer available",
    "applications are closed",
    "application deadline has passed",
    "position has been filled",
)


def _contains_closed_posting_marker(value: str) -> bool:
    normalized = html.unescape(value).casefold()
    return any(marker in normalized for marker in _CLOSED_POSTING_MARKERS)


class LinkedInPublicAvailabilityChecker:
    """Read one public job URL and preserve its exact numeric identity."""

    MAX_RESPONSE_BYTES = 1_000_000

    def __init__(self, *, timeout_seconds: float = 20, opener=None) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self._timeout = timeout_seconds
        self._opener = opener if opener is not None else build_opener()

    def check(self, url: str) -> LinkedInAvailabilityResult:
        canonical = canonical_linkedin_job_url(url)
        if canonical is None:
            return LinkedInAvailabilityResult(
                LinkedInAvailabilityStatus.UNVERIFIED,
                "LinkedIn availability requires a valid job-detail URL.",
            )
        request = Request(
            canonical,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                final_url = response.geturl()
                body = response.read(self.MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if exc.code in {404, 410}:
                return LinkedInAvailabilityResult(
                    LinkedInAvailabilityStatus.CLOSED,
                    f"LinkedIn returned HTTP {exc.code} for the posting.",
                )
            return self._unverified()
        except (URLError, TimeoutError, OSError):
            return self._unverified()

        final = urlsplit(final_url)
        if "expired_jd_redirect" in final.query.casefold():
            return LinkedInAvailabilityResult(
                LinkedInAvailabilityStatus.CLOSED,
                "LinkedIn redirected the expired posting.",
            )
        final_canonical = canonical_linkedin_job_url(final_url)
        if final_canonical != canonical:
            return LinkedInAvailabilityResult(
                LinkedInAvailabilityStatus.UNVERIFIED,
                "LinkedIn redirected away from the exact job-detail page.",
            )
        if len(body) > self.MAX_RESPONSE_BYTES:
            return self._unverified()
        text = body.decode("utf-8", errors="replace")
        if _contains_closed_posting_marker(text):
            return LinkedInAvailabilityResult(
                LinkedInAvailabilityStatus.CLOSED,
                "LinkedIn reports that the posting is closed.",
            )
        return LinkedInAvailabilityResult(
            LinkedInAvailabilityStatus.AVAILABLE,
            "LinkedIn retained the exact public job-detail page.",
        )

    @staticmethod
    def _unverified() -> LinkedInAvailabilityResult:
        return LinkedInAvailabilityResult(
            LinkedInAvailabilityStatus.UNVERIFIED,
            "LinkedIn availability could not be verified.",
        )


class ComposioSearchClient:
    """Two read-only tools over the documented REST API; no SDK dependency.

    This project key is separate from the hosted ChatGPT connector. The
    no-auth search toolkit needs no LinkedIn account or browser cookies.
    """

    BASE_URL = "https://backend.composio.dev/api/v3/tools/execute/"
    TOOL_VERSION = "20260903_00"
    MAX_RESPONSE_BYTES = 2_000_000

    def __init__(self, *, api_key: str, timeout_seconds: float = 30,
                 user_id: str = "job-application-agent", opener=None) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Set COMPOSIO_API_KEY in the local environment.")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must not be empty")
        self._api_key = api_key.strip()
        self._user_id = user_id.strip()
        self._timeout = timeout_seconds
        self._opener = opener if opener is not None else build_opener(_NoRedirects())

    @classmethod
    def from_environment(cls) -> ComposioSearchClient:
        # Loading .env belongs to the entry point, never to module import.
        return cls(api_key=os.environ.get("COMPOSIO_API_KEY", ""),
                   user_id=os.environ.get("COMPOSIO_USER_ID", "job-application-agent"))

    def search(self, query: str) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        return self._execute("COMPOSIO_SEARCH_WEB", {"query": query})

    def fetch(self, urls: list[str]) -> dict[str, Any]:
        if not 1 <= len(urls) <= 20 or any(canonical_linkedin_job_url(u) is None for u in urls):
            raise ValueError("Fetch requires 1-20 public LinkedIn job-detail URLs")
        return self._execute("COMPOSIO_SEARCH_FETCH_URL_CONTENT", {
            "urls": urls, "text": True, "max_characters": 20000,
        })

    def _execute(self, slug: str, arguments: dict) -> dict[str, Any]:
        request = Request(self.BASE_URL + slug, method="POST", headers={
            "x-api-key": self._api_key, "Content-Type": "application/json",
            "Accept": "application/json",
        }, data=json.dumps({"arguments": arguments, "version": self.TOOL_VERSION,
                            "user_id": self._user_id}).encode("utf-8"))
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                body = response.read(self.MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise ComposioDiscoveryError(f"Composio returned HTTP {exc.code}.") from None
        except (URLError, TimeoutError, OSError):
            raise ComposioDiscoveryError("Composio request failed or timed out.") from None
        if len(body) > self.MAX_RESPONSE_BYTES:
            raise ComposioDiscoveryError("Composio response exceeded the size limit.")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise ComposioDiscoveryError("Composio returned invalid JSON.") from None
        if (not isinstance(payload, dict) or payload.get("successful") is not True
                or payload.get("error") or not isinstance(payload.get("data"), dict)):
            raise ComposioDiscoveryError("Composio tool failed or returned an invalid response.")
        return payload["data"]


class LinkedInGuestSearchClient:
    """Read live public LinkedIn result cards, then delegate page fetches."""

    BASE_URL = (
        "https://www.linkedin.com/jobs-guest/jobs/api/"
        "seeMoreJobPostings/search"
    )
    MAX_RESPONSE_BYTES = 1_000_000

    def __init__(
        self,
        *,
        fetch_client: SearchClient,
        max_results: int = 5,
        timeout_seconds: float = 20,
        default_location: str = "United States",
        opener=None,
    ) -> None:
        if type(max_results) is not int or not 1 <= max_results <= 20:
            raise ValueError("max_results must be an integer between 1 and 20")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if not isinstance(default_location, str) or not default_location.strip():
            raise ValueError("default_location must not be empty")
        self._fetch_client = fetch_client
        self._max_results = max_results
        self._timeout = timeout_seconds
        self._default_location = default_location.strip()
        self._opener = opener if opener is not None else build_opener()
        self._dates: dict[str, str] = {}

    def search(self, query: str) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        keywords, location, recency = self._criteria(query)
        selected: dict[str, dict[str, str]] = {}
        self._dates = {}
        for start in range(0, self._max_results, 10):
            parameters = {
                "keywords": keywords,
                "location": location,
                "start": str(start),
            }
            if recency is not None:
                parameters["f_TPR"] = recency
            request = Request(
                f"{self.BASE_URL}?{urlencode(parameters)}",
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    body = response.read(self.MAX_RESPONSE_BYTES + 1)
            except (HTTPError, URLError, TimeoutError, OSError):
                raise ComposioDiscoveryError(
                    "LinkedIn public job search failed or timed out."
                ) from None
            if len(body) > self.MAX_RESPONSE_BYTES:
                raise ComposioDiscoveryError(
                    "LinkedIn public job search response exceeded the size limit."
                )
            self._collect_cards(body, selected)
            if len(selected) >= self._max_results:
                break
        return {"citations": list(selected.values())[:self._max_results]}

    def fetch(self, urls: list[str]) -> dict[str, Any]:
        payload = deepcopy(self._fetch_client.fetch(urls))
        pages = payload.get("results")
        if isinstance(pages, list):
            for page in pages:
                if not isinstance(page, dict):
                    continue
                canonical = canonical_linkedin_job_url(
                    page.get("url") or page.get("id")
                )
                if canonical in self._dates:
                    page["date_posted"] = self._dates[canonical]
        return payload

    def _collect_cards(
        self,
        body: bytes,
        selected: dict[str, dict[str, str]],
    ) -> None:
        soup = BeautifulSoup(
            body.decode("utf-8", errors="replace"),
            "html.parser",
        )
        for card in soup.select("[data-entity-urn]"):
            link = card.select_one("a.base-card__full-link[href]")
            canonical = canonical_linkedin_job_url(
                link.get("href") if link is not None else None
            )
            if canonical is None or canonical in selected:
                continue
            title_element = card.select_one(".base-search-card__title")
            title = (
                title_element.get_text(" ", strip=True)
                if title_element is not None
                else "LinkedIn job posting"
            )
            selected[canonical] = {"url": canonical, "title": title}
            time_element = card.select_one("time[datetime]")
            date_posted = (
                time_element.get("datetime")
                if time_element is not None
                else None
            )
            if isinstance(date_posted, str) and re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                date_posted,
            ):
                self._dates[canonical] = date_posted
            if len(selected) >= self._max_results:
                return

    def _criteria(self, query: str) -> tuple[str, str, str | None]:
        value = re.sub(
            r"^site:linkedin\.com/jobs/view\s+",
            "",
            query.strip(),
            flags=re.IGNORECASE,
        )
        recency = None
        recency_patterns = (
            (
                r"\b(?:posted\s+)?(?:in\s+)?(?:the\s+)?"
                r"(?:past|last)\s+24\s+hours?\b",
                "r86400",
            ),
            (r"\b(?:posted\s+)?today\b", "r86400"),
            (
                r"\b(?:posted\s+)?(?:in\s+)?(?:the\s+)?"
                r"(?:past|last)\s+week\b",
                "r604800",
            ),
        )
        for pattern, value_code in recency_patterns:
            updated, count = re.subn(
                pattern,
                " ",
                value,
                flags=re.IGNORECASE,
            )
            if count:
                value = updated
                recency = value_code
                break
        location = self._default_location
        location_match = re.search(
            r"\s+(?:in|near)\s+([^,;]+(?:,\s*[^,;]+)?)\s*$",
            value,
            re.IGNORECASE,
        )
        if location_match is not None:
            location = location_match.group(1).strip()
            value = value[:location_match.start()]
        keywords = re.sub(
            r"\bentry[-\s]level\b",
            "entry level",
            value,
            flags=re.IGNORECASE,
        )
        keywords = " ".join(keywords.strip(" ,;-").split())
        if not keywords:
            raise ValueError("query must include job keywords")
        return keywords, location, recency


def canonical_linkedin_job_url(value: Any) -> str | None:
    """Keep a numeric posting identity, never search/profile or lookalike URLs."""
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (parsed.scheme not in {"http", "https"}
                or not (host == "linkedin.com" or host.endswith(".linkedin.com"))
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in {None, 80 if parsed.scheme == "http" else 443}):
            return None
        match = re.fullmatch(r"/jobs/view/(?:[A-Za-z0-9%_-]+-)?([0-9]+)/?", parsed.path)
        if match is None:
            return None
        return "https://www.linkedin.com/jobs/view/" + match[1]
    except ValueError:
        return None


def _results(data: dict) -> dict:
    result = data.get("results", data)
    if not isinstance(result, dict):
        raise ComposioDiscoveryError("Search response has no valid results object.")
    return result


class LinkedInComposioJobSource(JobSource):
    """One search and at most one bounded fetch per run.

    Parse explicit LinkedIn page titles and require a matching H1 in fetched
    text. Unrecognized, expired, unavailable, and incomplete pages are skipped.
    No inference from generated answers, relative dates, or URL slugs. The
    existing pipeline retains all classification, scoring and persistence.
    """

    def __init__(
        self,
        *,
        client: SearchClient,
        query: str,
        max_results: int = 5,
        availability_checker: LinkedInAvailabilityChecker | None = None,
        application_target_search: (
            ApplicationTargetSearchResolver | None
        ) = None,
    ) -> None:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        if type(max_results) is not int or not 1 <= max_results <= 20:
            raise ValueError("max_results must be an integer between 1 and 20")
        self.client = client
        self.query = query.strip()
        self.max_results = max_results
        self.availability_checker = availability_checker
        self.application_target_search = application_target_search
        self.last_candidate_count = 0
        self.last_skipped_count = 0

    @property
    def source_name(self) -> str:
        return "linkedin_composio"

    def discover(self) -> list[RawJobPosting]:
        self.last_candidate_count = self.last_skipped_count = 0
        data = _results(self.client.search(self.query))
        citations = data.get("citations")
        if citations in (None, []) and "organic_results" in data:
            citations = data["organic_results"]
        if not isinstance(citations, list):
            raise ComposioDiscoveryError("Search response has no valid citations list.")
        selected = {}
        for item in citations:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("id") or item.get("link")
            canonical = canonical_linkedin_job_url(url)
            if canonical and canonical not in selected:
                parts = urlsplit(url)
                selected[canonical] = urlunsplit(("https", parts.hostname, parts.path, "", ""))
                if len(selected) == self.max_results:
                    break
        self.last_candidate_count = len(selected)
        if not selected:
            return []
        fetched = self.client.fetch(list(selected.values()))
        pages = fetched.get("results")
        if not isinstance(pages, list):
            raise ComposioDiscoveryError("Fetch response has no valid results list.")
        statuses = fetched.get("statuses", [])
        if not isinstance(statuses, list):
            raise ComposioDiscoveryError("Fetch response has invalid statuses.")
        failed = {canonical_linkedin_job_url(s.get("id")) for s in statuses
                  if isinstance(s, dict) and s.get("status") != "success"}
        jobs = {}
        for page in pages:
            if not isinstance(page, dict):
                continue
            canonical = canonical_linkedin_job_url(page.get("url") or page.get("id"))
            if canonical not in selected or canonical in failed or canonical in jobs:
                continue
            raw = self._posting(page, canonical)
            if raw is not None:
                jobs[canonical] = raw
        self.last_skipped_count = len(selected) - len(jobs)
        return list(jobs.values())

    def _posting(self, page: dict, url: str) -> RawJobPosting | None:
        title, text = page.get("title"), page.get("text")
        if not isinstance(title, str) or not isinstance(text, str) or not text.strip():
            return None
        if _contains_closed_posting_marker(text):
            return None
        match = re.fullmatch(r"(?P<company>.+?) hiring (?P<title>.+?) in (?P<location>.+?) \| LinkedIn(?: Jobs)?", title.strip())
        if match is None:
            match = re.fullmatch(r"(?P<title>.+?) at (?P<company>.+?) \u2014 (?P<location>.+?) \| LinkedIn(?: Jobs)?", title.strip())
        if match is None:
            match = re.fullmatch(r"(?P<company>.+?) hiring (?P<title>.+?) \| LinkedIn(?: Jobs)?", title.strip())
        if match is None:
            return None
        fields = {key: value.strip() for key, value in match.groupdict().items()}
        if not all(fields.values()):
            return None
        headings = re.findall(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
        if fields["title"] not in headings or fields["company"] not in text:
            return None
        availability = None
        if self.availability_checker is not None:
            availability = self.availability_checker.check(url)
            if availability.status != LinkedInAvailabilityStatus.AVAILABLE:
                return None
        target = ApplicationTargetResolver().resolve(
            self._explicit_application_targets(page)
        )
        target_status = target.status.value
        target_reason = target.reason
        application_url = target.application_url
        if (
            application_url is None
            and self.application_target_search is not None
        ):
            searched = self.application_target_search.resolve(
                company=fields["company"],
                title=fields["title"],
            )
            target_status = searched.status.value
            target_reason = searched.reason
            if searched.status == TargetSearchStatus.RESOLVED:
                application_url = searched.application_url
        return RawJobPosting(source=self.source_name, url=url,
                             application_url=application_url,
                             company=fields["company"], title=fields["title"],
                             location=fields.get("location"), description=text.strip(),
                             external_job_id=url.rsplit("/", 1)[-1],
                             date_posted=(
                                 page.get("date_posted")
                                 if isinstance(page.get("date_posted"), str)
                                 and re.fullmatch(
                                     r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                                     page["date_posted"],
                                 )
                                 else None
                             ),
                             metadata={
                                       "discovery_provider": (
                                           "linkedin_public_search_composio_fetch"
                                       ),
                                       "content_kind": "extracted_page_text",
                                       "tool_version": ComposioSearchClient.TOOL_VERSION,
                                       "freshness_verified": availability is not None,
                                       "availability_reason": (
                                           availability.reason
                                           if availability is not None
                                           else None
                                       ),
                                       "application_target_status": target_status,
                                       "application_target_reason": target_reason})

    @staticmethod
    def _explicit_application_targets(page: dict) -> list[object]:
        candidates: list[object] = [
            page.get("application_url"),
            page.get("apply_url"),
        ]
        links = page.get("links")
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                label = link.get("label") or link.get("title") or link.get("text")
                if isinstance(label, str) and label.strip().casefold() in {
                    "apply", "apply now", "application",
                }:
                    candidates.append(link.get("href") or link.get("url"))
        return candidates

    def normalize(self, raw_job: RawJobPosting) -> Job:
        return Job(company=raw_job.company, title=raw_job.title,
                   location=raw_job.location, url=raw_job.url,
                   application_url=raw_job.application_url, source=raw_job.source,
                   description=raw_job.description, external_job_id=raw_job.external_job_id,
                   date_posted=raw_job.date_posted,
                   notes=(raw_job.metadata.get("application_target_reason")
                          if raw_job.application_url is None else None))
