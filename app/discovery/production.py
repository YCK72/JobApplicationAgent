from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.discovery.composio import (
    ComposioSearchClient,
    LinkedInComposioJobSource,
    SearchClient,
)
from app.discovery.runner import DiscoveryRunResult, DiscoveryRunner
from app.jobs.composition import build_job_pipeline
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

    @property
    def processed_count(self) -> int:
        return self.discovery_result.discovered_count

    @property
    def error_count(self) -> int:
        return self.discovery_result.error_count

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
    ) -> None:
        self.discovery_runner = discovery_runner
        self.database = database
        self.tracker = tracker

    def run(self) -> PersistentDiscoveryResult:
        discovery_result = self.discovery_runner.run()
        export_path = self.tracker.generate()
        stored_job_count = len(self.database.get_all_jobs())

        return PersistentDiscoveryResult(
            discovery_result=discovery_result,
            export_path=export_path,
            stored_job_count=stored_job_count,
        )


def build_persistent_discovery_runner(
    *,
    query: str,
    max_results: int = 3,
    database_path: Path | str = DEFAULT_DATABASE_PATH,
    export_path: Path | str = DEFAULT_EXPORT_PATH,
    client: SearchClient | None = None,
) -> PersistentDiscoveryRunner:
    """Compose the persistent LinkedIn/Composio discovery boundary."""

    resolved_client = (
        client
        if client is not None
        else ComposioSearchClient.from_environment()
    )
    source = LinkedInComposioJobSource(
        client=resolved_client,
        query=query,
        max_results=max_results,
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
    )
