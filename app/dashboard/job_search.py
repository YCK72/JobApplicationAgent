from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

from app.discovery.production import (
    PersistentDiscoveryResult,
    PersistentDiscoveryRunner,
)
from app.jobs.pipeline import PipelineOutcome


DiscoveryRunnerBuilder = Callable[[str, int], PersistentDiscoveryRunner]


@dataclass(frozen=True)
class DashboardJobSearchResult:
    query: str
    processed: int
    stored_jobs: int
    expired_jobs: int
    errors: tuple[str, ...]
    outcomes: dict[str, int]
    eligible_job_ids: tuple[int, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "processed": self.processed,
            "stored_jobs": self.stored_jobs,
            "expired_jobs": self.expired_jobs,
            "errors": list(self.errors),
            "outcomes": self.outcomes,
            "eligible_job_ids": list(self.eligible_job_ids),
        }


class DashboardJobSearchService:
    """Run one bounded discovery request from the local dashboard."""

    def __init__(self, *, runner_builder: DiscoveryRunnerBuilder) -> None:
        self._runner_builder = runner_builder
        self._lock = Lock()

    def search(self, *, query: object, limit: object) -> DashboardJobSearchResult:
        if not isinstance(query, str) or not 3 <= len(query.strip()) <= 200:
            raise ValueError("Search query must contain 3-200 characters.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("Search limit must be an integer from 1 to 10.")
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A job search is already running.")
        cleaned_query = " ".join(query.split())
        try:
            result = self._runner_builder(cleaned_query, limit).run()
        finally:
            self._lock.release()
        return self._summarize(cleaned_query, result)

    @staticmethod
    def _summarize(
        query: str,
        result: PersistentDiscoveryResult,
    ) -> DashboardJobSearchResult:
        eligible_ids = tuple(
            item.job_id
            for item in result.discovery_result.pipeline_results
            if item.outcome == PipelineOutcome.AUTO_READY
            and item.job_id is not None
        )
        return DashboardJobSearchResult(
            query=query,
            processed=result.processed_count,
            stored_jobs=result.stored_job_count,
            expired_jobs=result.expired_job_count,
            errors=tuple(result.discovery_result.errors),
            outcomes=result.outcome_counts,
            eligible_job_ids=eligible_ids,
        )
