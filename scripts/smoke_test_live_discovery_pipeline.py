from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys


# Allow this script to import the app package when executed directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.applications.resume_router import ResumeRouter
from app.scoring.fit_gate import FitGate
from app.discovery.greenhouse import GreenhouseJobSource
from app.discovery.runner import DiscoveryRunner
from app.jobs.classifier import RoleClassifier
from app.jobs.company_router import CompanyRouter
from app.jobs.filters import JobFilter
from app.jobs.eligibility import JobEligibilityGate
from app.jobs.pipeline import JobPipeline
from app.scoring.fit_scorer import FitScorer
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker
from app.utils.config import (
    load_candidate_config,
    load_company_rules,
    load_role_config,
)


# ============================================================
# Isolated smoke-test paths
# ============================================================

DATABASE_PATH = Path(
    "database/greenhouse_smoke_test_jobs.db"
)

EXPORT_PATH = Path(
    "data/exports/"
    "Greenhouse_Smoke_Test_Job_Application_Tracker.xlsx"
)


# ============================================================
# Live Greenhouse source
# ============================================================

COMPANY = "SingleStore"
BOARD_TOKEN = "singlestore"


# Only print a small sample to the terminal.
DISPLAY_LIMIT = 10


def remove_old_smoke_outputs() -> None:
    """
    Remove outputs from the previous live smoke-test run.

    This ensures every run starts with a fresh isolated database
    and workbook.

    Production tracking files are never touched.
    """

    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()

    if EXPORT_PATH.exists():
        EXPORT_PATH.unlink()


def build_pipeline(
    database: JobDatabase,
) -> JobPipeline:
    """
    Build the real JobPipeline using the same configuration-loading
    pattern as the existing Milestone 2 smoke test.

    The only difference is that persistence is directed to the
    isolated Greenhouse smoke-test database.
    """

    candidate_config = load_candidate_config()
    company_rules = load_company_rules()
    role_config = load_role_config()

    return JobPipeline(
        company_router=CompanyRouter(
            company_rules
        ),
        classifier=RoleClassifier(
            role_config
        ),
        job_filter=JobFilter(
            role_config
        ),
        fit_scorer=FitScorer(
            candidate_config
        ),
        fit_gate=FitGate(
            role_config
        ),
        resume_router=ResumeRouter(
            candidate_config
        ),
        database=database,
        eligibility_gate=JobEligibilityGate(candidate_config),
    )


def print_result(
    index: int,
    pipeline_result,
) -> None:
    """
    Print a compact representation of one pipeline result.
    """

    job = pipeline_result.job

    print("-" * 78)
    print(f"JOB {index}")
    print("-" * 78)

    print(
        f"Company:             "
        f"{job.company}"
    )

    print(
        f"Title:               "
        f"{job.title}"
    )

    print(
        f"Location:            "
        f"{job.location}"
    )

    print(
        f"Category:            "
        f"{job.category.value}"
    )

    print(
        f"Seniority:           "
        f"{job.seniority.value}"
    )

    print(
        f"Fit score:           "
        f"{job.fit_score}"
    )

    print(
        f"Company rule:        "
        f"{job.company_rule.value}"
    )

    print(
        f"Application method:  "
        f"{job.application_method.value}"
    )

    print(
        f"Status:              "
        f"{job.status.value}"
    )

    print(
        f"Resume:              "
        f"{job.resume_used}"
    )

    print(
        f"Pipeline outcome:    "
        f"{pipeline_result.outcome.value}"
    )

    print(
        f"Continue:            "
        f"{pipeline_result.should_continue}"
    )

    print(
        f"Reason:              "
        f"{pipeline_result.reason}"
    )

    print(
        f"URL:                 "
        f"{job.url}"
    )

    print()


def print_outcome_summary(
    run_result,
) -> None:
    """
    Print counts for each PipelineOutcome returned by the run.
    """

    outcome_counts = Counter(
        result.outcome.value
        for result in run_result.pipeline_results
    )

    print("Pipeline outcomes:")

    if not outcome_counts:
        print("  No pipeline results.")
        return

    for outcome, count in sorted(
        outcome_counts.items()
    ):
        print(
            f"  {outcome}: {count}"
        )


def main() -> None:
    print("=" * 78)
    print(
        "LIVE GREENHOUSE -> JOB PIPELINE SMOKE TEST"
    )
    print("=" * 78)
    print()

    print("SAFETY MODE")
    print("-----------")

    print(
        "This test uses an isolated SQLite database "
        "and Excel workbook."
    )

    print(
        "It does NOT use the production jobs database."
    )

    print(
        "It does NOT open Brave."
    )

    print(
        "It does NOT use Playwright."
    )

    print(
        "It does NOT fill application forms."
    )

    print(
        "It does NOT submit applications."
    )

    print()

    # --------------------------------------------------------
    # Start with completely fresh smoke-test outputs.
    # --------------------------------------------------------

    remove_old_smoke_outputs()

    # --------------------------------------------------------
    # Build isolated persistence layer.
    # --------------------------------------------------------

    database = JobDatabase(
        DATABASE_PATH
    )

    # --------------------------------------------------------
    # Build the real production pipeline.
    # --------------------------------------------------------

    pipeline = build_pipeline(
        database
    )

    # --------------------------------------------------------
    # Configure the live Greenhouse source.
    # --------------------------------------------------------

    source = GreenhouseJobSource(
        company=COMPANY,
        board_token=BOARD_TOKEN,
    )

    # --------------------------------------------------------
    # Connect discovery to the existing pipeline.
    # --------------------------------------------------------

    runner = DiscoveryRunner(
        pipeline=pipeline,
        sources=[source],
    )

    print(
        f"Company:     {COMPANY}"
    )

    print(
        f"Board token: {BOARD_TOKEN}"
    )

    print(
        f"Database:    {DATABASE_PATH}"
    )

    print(
        f"Excel:       {EXPORT_PATH}"
    )

    print()

    print(
        "Running live discovery through JobPipeline..."
    )

    print()

    # --------------------------------------------------------
    # Run live discovery.
    #
    # DiscoveryRunner records source-level discovery failures.
    # Pipeline/programming failures intentionally remain visible.
    # --------------------------------------------------------

    run_result = runner.run()

    # --------------------------------------------------------
    # Discovery summary
    # --------------------------------------------------------

    print("=" * 78)
    print("DISCOVERY SUMMARY")
    print("=" * 78)
    print()

    print(
        "Jobs sent through pipeline: "
        f"{run_result.discovered_count}"
    )

    print(
        "Source-level errors: "
        f"{run_result.error_count}"
    )

    if run_result.errors:
        print()
        print("Source errors:")

        for error in run_result.errors:
            print(
                f"  - {error}"
            )

    print()

    print_outcome_summary(
        run_result
    )

    print()

    # --------------------------------------------------------
    # Verify isolated SQLite persistence.
    # --------------------------------------------------------

    stored_jobs = database.get_all_jobs()

    print(
        "Jobs stored in isolated SQLite: "
        f"{len(stored_jobs)}"
    )

    print()

    # --------------------------------------------------------
    # Display only a limited number of jobs.
    # --------------------------------------------------------

    if run_result.pipeline_results:
        display_count = min(
            DISPLAY_LIMIT,
            len(
                run_result.pipeline_results
            ),
        )

        print("=" * 78)

        print(
            f"FIRST {display_count} "
            "PIPELINE RESULTS"
        )

        print("=" * 78)
        print()

        for index, pipeline_result in enumerate(
            run_result.pipeline_results[
                :DISPLAY_LIMIT
            ],
            start=1,
        ):
            print_result(
                index,
                pipeline_result,
            )

    # --------------------------------------------------------
    # Generate isolated Excel workbook.
    # --------------------------------------------------------

    print("=" * 78)
    print(
        "GENERATING ISOLATED EXCEL TRACKER"
    )
    print("=" * 78)
    print()

    tracker = ExcelTracker(
        database=database,
        export_path=EXPORT_PATH,
    )

    generated_path = tracker.generate()

    print(
        f"Generated: {generated_path}"
    )

    print()

    # --------------------------------------------------------
    # Final safety confirmation
    # --------------------------------------------------------

    print("=" * 78)
    print("FINAL SAFETY CHECK")
    print("=" * 78)
    print()

    print(
        "Live jobs were processed only through "
        "the existing discovery and pipeline layers."
    )

    print()

    print(
        f"SQLite output: {DATABASE_PATH}"
    )

    print(
        f"Excel output:  {EXPORT_PATH}"
    )

    print()

    print(
        "No browser automation occurred."
    )

    print(
        "No forms were filled."
    )

    print(
        "No applications were submitted."
    )


if __name__ == "__main__":
    main()