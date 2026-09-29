"""Bounded public LinkedIn discovery through Composio, independent of chat sessions."""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.discovery.base import JobSource, RawJobPosting
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

    def __init__(self, *, client: SearchClient, query: str, max_results: int = 5) -> None:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        if type(max_results) is not int or not 1 <= max_results <= 20:
            raise ValueError("max_results must be an integer between 1 and 20")
        self.client = client
        self.query = query.strip()
        self.max_results = max_results
        self.last_candidate_count = 0
        self.last_skipped_count = 0

    @property
    def source_name(self) -> str:
        return "linkedin_composio"

    def discover(self) -> list[RawJobPosting]:
        self.last_candidate_count = self.last_skipped_count = 0
        data = _results(self.client.search("site:linkedin.com/jobs/view " + self.query))
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
        if "no longer accepting applications" in text.casefold():
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
        return RawJobPosting(source=self.source_name, url=url,
                             company=fields["company"], title=fields["title"],
                             location=fields.get("location"), description=text.strip(),
                             external_job_id=url.rsplit("/", 1)[-1],
                             metadata={"discovery_provider": "composio_search",
                                       "content_kind": "extracted_page_text",
                                       "tool_version": ComposioSearchClient.TOOL_VERSION,
                                       "freshness_verified": False})

    def normalize(self, raw_job: RawJobPosting) -> Job:
        return Job(company=raw_job.company, title=raw_job.title,
                   location=raw_job.location, url=raw_job.url, source=raw_job.source,
                   description=raw_job.description, external_job_id=raw_job.external_job_id,
                   date_posted=raw_job.date_posted)
