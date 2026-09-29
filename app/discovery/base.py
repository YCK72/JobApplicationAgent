from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.jobs.models import Job


@dataclass
class RawJobPosting:
    """
    Represents a job posting exactly as it was discovered from an external
    source, before it is converted into the application's normalized Job model.

    Source adapters should populate as much information as they can without
    inventing missing values.
    """

    source: str
    company: str
    title: str
    url: str
    application_url: str | None = None

    location: str | None = None
    description: str | None = None
    external_job_id: str | None = None
    date_posted: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


class JobSource(ABC):
    """
    Base interface for every job-discovery source.

    Examples of future implementations:

    - Greenhouse
    - Lever
    - Ashby
    - Workday
    - company career sites
    - job boards

    Discovery sources are responsible only for discovering and normalizing
    postings. They must not classify jobs, score jobs, choose resumes,
    fill applications, or submit applications.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the stable name used to identify this job source."""
        raise NotImplementedError

    @abstractmethod
    def discover(self) -> list[RawJobPosting]:
        """
        Discover job postings from the external source.

        Implementations should return raw postings and should not interact
        with the application pipeline directly.
        """
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_job: RawJobPosting) -> Job:
        """
        Convert a source-specific raw posting into the common Job model.

        Missing information must remain missing rather than being inferred
        or fabricated.
        """
        raise NotImplementedError

    def discover_jobs(self) -> list[Job]:
        """
        Convenience method that discovers raw postings and normalizes each
        posting into the application's common Job model.
        """
        raw_jobs = self.discover()

        return [
            self.normalize(raw_job)
            for raw_job in raw_jobs
        ]
