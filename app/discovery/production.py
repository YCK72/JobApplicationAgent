from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.discovery.composio import (
    ComposioSearchClient,
    LinkedInAvailabilityChecker,
    LinkedInAvailabilityStatus,
    LinkedInComposioJobSource,
    LinkedInGuestSearchClient,
    LinkedInPublicAvailabilityChecker,
    SearchClient,
)
from app.discovery.runner import DiscoveryRunResult, DiscoveryRunner
from app.discovery.target_search import (
    ApplicationTargetSearchResolver,
    TargetSearchClient,
)
from app.jobs.composition import build_job_pipeline
from app.jobs.models import ApplicationStatus
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "database" / "jobs.db"
DEFAULT_EXPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "exports"
    / "Job_Application_Tracker.xlsx"
)


@dataclass(frozen=True)
class PersistentDiscoveryResult:
    """Summary of one persistent discovery and tracker-refresh run."""

    discovery_result: DiscoveryRunResult
    export_path: Path
    stored_job_count: int
    expired_job_ids: tuple[int, ...] = ()

    @property
    def processed_count(self) -> int:
        return self.discovery_result.discovered_count

    @property
    def error_count(self) -> int:
        return self.discovery_result.error_count

    @property
    def expired_job_count(self) -> int:
        return len(self.expired_job_ids)

    @property
    def outcome_counts(self) -> dict[str, int]:
        counts = Counter(
            result.outcome.value
            for result in self.discovery_result.pipeline_results
        )
        return dict(sorted(counts.items()))


class PersistentDiscoveryRunner:
    """Run discovery into SQLite, then regenerate the Excel report.

    Discovery and JobPipeline own all job decisions and persistence. This
    layer only sequences discovery and export. It has no application workflow,
    browser, form-filling, submission, or confirmation capability.
    """

    def __init__(
        self,
        *,
        discovery_runner: DiscoveryRunner,
        database: JobDatabase,
        tracker: ExcelTracker,
        availability_checker: LinkedInAvailabilityChecker | None = None,
        max_revalidations: int = 20,
    ) -> None:
        if type(max_revalidations) is not int or not 0 <= max_revalidations <= 20:
            raise ValueError("max_revalidations must be an integer from 0 to 20")
        self.discovery_runner = discovery_runner
        self.database = database
        self.tracker = tracker
        self.availability_checker = availability_checker
        self.max_revalidations = max_revalidations

    def run(self) -> PersistentDiscoveryResult:
        expired_job_ids = self._expire_closed_linkedin_jobs()
        discovery_result = self.discovery_runner.run()
        export_path = self.tracker.generate()
        stored_job_count = len(self.database.get_all_jobs())

        return PersistentDiscoveryResult(
            discovery_result=discovery_result,
            export_path=export_path,
            stored_job_count=stored_job_count,
            expired_job_ids=expired_job_ids,
        )

    def _expire_closed_linkedin_jobs(self) -> tuple[int, ...]:
        if self.availability_checker is None or self.max_revalidations == 0:
            return ()
        eligible_statuses = {
            ApplicationStatus.DISCOVERED,
            ApplicationStatus.NEEDS_REVIEW,
            ApplicationStatus.NEEDS_APPLICATION,
            ApplicationStatus.READY_TO_APPLY,
        }
        candidates = [
            (job_id, job)
            for job_id, job in self.database.get_jobs_with_ids()
            if job.source == "linkedin_composio"
            and job.status in eligible_statuses
        ][:self.max_revalidations]
        expired: list[int] = []
        for job_id, job in candidates:
            availability = self.availability_checker.check(
                job.url.encoded_string()
            )
            if availability.status != LinkedInAvailabilityStatus.CLOSED:
                continue
            note = (
                "LinkedIn availability revalidation filtered this posting: "
                f"{availability.reason}"
            )
            job.status = ApplicationStatus.FILTERED_OUT
            job.notes = (
                f"{job.notes.rstrip()}\n{note}"
                if job.notes and job.notes.strip()
                else note
            )
            self.database.update_job(job_id, job)
            expired.append(job_id)
        return tuple(expired)


def build_persistent_discovery_runner(
    *,
    query: str,
    max_results: int = 3,
    database_path: Path | str = DEFAULT_DATABASE_PATH,
    export_path: Path | str = DEFAULT_EXPORT_PATH,
    client: SearchClient | None = None,
    availability_checker: LinkedInAvailabilityChecker | None = None,
    target_search_client: TargetSearchClient | None = None,
) -> PersistentDiscoveryRunner:
    """Compose the persistent LinkedIn/Composio discovery boundary."""

    resolved_client = client
    resolved_target_search_client = target_search_client
    if resolved_client is None:
        composio_client = ComposioSearchClient.from_environment()
        resolved_client = LinkedInGuestSearchClient(
            fetch_client=composio_client,
            max_results=max_results,
        )
        if resolved_target_search_client is None:
            resolved_target_search_client = composio_client
    resolved_availability_checker = (
        availability_checker
        if availability_checker is not None
        else LinkedInPublicAvailabilityChecker()
    )
    source = LinkedInComposioJobSource(
        client=resolved_client,
        query=query,
        max_results=max_results,
        availability_checker=resolved_availability_checker,
        application_target_search=(
            ApplicationTargetSearchResolver(
                client=resolved_target_search_client,
            )
            if resolved_target_search_client is not None
            else None
        ),
    )
    database = JobDatabase(Path(database_path))
    pipeline = build_job_pipeline(database=database)

    return PersistentDiscoveryRunner(
        discovery_runner=DiscoveryRunner(
            pipeline=pipeline,
            sources=[source],
        ),
        database=database,
        tracker=ExcelTracker(
            database=database,
            export_path=Path(export_path),
        ),
        availability_checker=resolved_availability_checker,
    )
