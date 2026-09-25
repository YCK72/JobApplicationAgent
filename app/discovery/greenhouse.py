from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from app.discovery.base import JobSource, RawJobPosting
from app.jobs.models import Job


class GreenhouseDiscoveryError(RuntimeError):
    """
    Raised when a Greenhouse job board cannot be retrieved or parsed.
    """


class GreenhouseJobSource(JobSource):
    """
    Discovery source for a single public Greenhouse job board.

    Responsibilities are intentionally limited to:

        1. Retrieve the public Greenhouse job-board payload.
        2. Validate the response structure.
        3. Convert postings into RawJobPosting objects.
        4. Normalize RawJobPosting objects into the common Job model.

    Classification, filtering, scoring, deduplication, persistence,
    resume selection, browser automation, and applications remain
    downstream responsibilities.
    """

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
    DEFAULT_TIMEOUT_SECONDS = 15.0

    def __init__(
        self,
        *,
        company: str,
        board_token: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        company = company.strip()
        board_token = board_token.strip()

        if not company:
            raise ValueError("company must not be empty")

        if not board_token:
            raise ValueError("board_token must not be empty")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        self.company = company
        self.board_token = board_token
        self.timeout_seconds = float(timeout_seconds)

    @staticmethod
    def _clean_description(content: Any) -> str | None:
        """
        Convert Greenhouse HTML job content into normalized plain text.

        Greenhouse commonly returns the job description as HTML. The rest of
        the application should work with readable text rather than HTML markup.

        Empty or non-string content is normalized to None.
        """
        if not isinstance(content, str) or not content.strip():
            return None

        soup = BeautifulSoup(content, "html.parser")

        text = soup.get_text(
            separator=" ",
            strip=True,
        )

        if not text:
            return None

        return " ".join(text.split())

    @property
    def source_name(self) -> str:
        return "greenhouse"

    @property
    def jobs_url(self) -> str:
        """
        Return the public Greenhouse jobs endpoint for this board.

        content=true asks Greenhouse to include the job description.
        """

        return (
            f"{self.BASE_URL}/{self.board_token}/jobs"
            "?content=true"
        )

    def _fetch_payload(self) -> dict[str, Any]:
        """
        Retrieve and decode the Greenhouse job-board JSON response.

        Network and response-format errors are converted into a stable
        GreenhouseDiscoveryError so callers do not need to understand
        urllib-specific exceptions.
        """

        request = Request(
            self.jobs_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "JobApplicationAgent/1.0",
            },
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw_body = response.read()

        except HTTPError as exc:
            raise GreenhouseDiscoveryError(
                "Greenhouse request failed with "
                f"HTTP status {exc.code} for board "
                f"'{self.board_token}'."
            ) from exc

        except URLError as exc:
            raise GreenhouseDiscoveryError(
                "Greenhouse request failed for board "
                f"'{self.board_token}': {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise GreenhouseDiscoveryError(
                "Greenhouse request timed out for board "
                f"'{self.board_token}'."
            ) from exc

        try:
            decoded_body = raw_body.decode("utf-8")
            payload = json.loads(decoded_body)

        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GreenhouseDiscoveryError(
                "Greenhouse returned an invalid JSON response for board "
                f"'{self.board_token}'."
            ) from exc

        if not isinstance(payload, dict):
            raise GreenhouseDiscoveryError(
                "Greenhouse response must be a JSON object."
            )

        return payload

    def discover(self) -> list[RawJobPosting]:
        """
        Retrieve all jobs currently exposed by the configured
        public Greenhouse board.
        """

        payload = self._fetch_payload()

        jobs = payload.get("jobs")

        if not isinstance(jobs, list):
            raise GreenhouseDiscoveryError(
                "Greenhouse response is missing a valid jobs list."
            )

        raw_jobs: list[RawJobPosting] = []

        for job_payload in jobs:
            if not isinstance(job_payload, dict):
                raise GreenhouseDiscoveryError(
                    "Greenhouse jobs list contains an invalid job payload."
                )

            raw_jobs.append(
                self.normalize_payload(job_payload)
            )

        return raw_jobs

    def normalize_payload(
        self,
        payload: dict[str, Any],
    ) -> RawJobPosting:
        """
        Convert one Greenhouse-shaped job payload into RawJobPosting.

        Missing optional information remains missing rather than being
        inferred or fabricated.
        """

        job_id = payload.get("id")
        title = payload.get("title")
        absolute_url = payload.get("absolute_url")

        if job_id is None:
            raise ValueError("Greenhouse job payload is missing id")

        if not isinstance(title, str) or not title.strip():
            raise ValueError(
                "Greenhouse job payload is missing a valid title"
            )

        if not isinstance(absolute_url, str) or not absolute_url.strip():
            raise ValueError(
                "Greenhouse job payload is missing a valid absolute_url"
            )

        location = None
        location_data = payload.get("location")

        if isinstance(location_data, dict):
            location_name = location_data.get("name")

            if isinstance(location_name, str) and location_name.strip():
                location = location_name.strip()

        description = self._clean_description(
            payload.get("content")
        )

        updated_at = payload.get("updated_at")

        date_posted = None

        if isinstance(updated_at, str) and len(updated_at) >= 10:
            date_posted = updated_at[:10]

        return RawJobPosting(
            source=self.source_name,
            company=self.company,
            title=title.strip(),
            location=location,
            url=absolute_url.strip(),
            description=description,
            external_job_id=str(job_id),
            date_posted=date_posted,
            metadata={
                "board_token": self.board_token,
            },
        )

    def normalize(
        self,
        raw_job: RawJobPosting,
    ) -> Job:
        """
        Convert a Greenhouse RawJobPosting into the common Job model.
        """

        return Job(
            company=raw_job.company,
            title=raw_job.title,
            location=raw_job.location,
            url=raw_job.url,
            source=raw_job.source,
            description=raw_job.description,
            external_job_id=raw_job.external_job_id,
            date_posted=raw_job.date_posted,
        )