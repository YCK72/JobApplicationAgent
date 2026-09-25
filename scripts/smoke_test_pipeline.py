from pathlib import Path
import sys

# Allow this script to import the app package when executed directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.applications.resume_router import ResumeRouter
from app.jobs.classifier import RoleClassifier
from app.jobs.company_router import CompanyRouter
from app.jobs.filters import JobFilter
from app.jobs.models import Job
from app.jobs.pipeline import JobPipeline
from app.scoring.fit_scorer import FitScorer
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker
from app.utils.config import (
    load_candidate_config,
    load_company_rules,
    load_role_config,
)


SMOKE_DB_PATH = Path("database/smoke_test_jobs.db")
SMOKE_EXCEL_PATH = Path(
    "data/exports/Smoke_Test_Job_Application_Tracker.xlsx"
)


def build_pipeline(database: JobDatabase) -> JobPipeline:
    candidate_config = load_candidate_config()
    company_rules = load_company_rules()
    role_config = load_role_config()

    return JobPipeline(
        company_router=CompanyRouter(company_rules),
        classifier=RoleClassifier(role_config),
        job_filter=JobFilter(role_config),
        fit_scorer=FitScorer(candidate_config),
        resume_router=ResumeRouter(candidate_config),
        database=database,
    )


def build_test_jobs() -> list[Job]:
    return [
        # AUTO SDE
        Job(
            company="Example Startup",
            title="Software Engineer I",
            location="Seattle, WA",
            url="https://smoke-test.local/jobs/sde-001",
            source="Smoke Test",
            description=(
                "Build Python and Java backend services using "
                "Spring Boot, REST API, Microservices, AWS, "
                "Docker, PostgreSQL, and distributed systems."
            ),
        ),

        # AUTO AI/ML
        Job(
            company="Example AI Startup",
            title="Machine Learning Engineer",
            location="San Francisco, CA",
            url="https://smoke-test.local/jobs/ml-001",
            source="Smoke Test",
            description=(
                "Build Python machine learning systems using "
                "PyTorch, MLOps, RAG, FAISS, AWS, Docker, "
                "Kubernetes, and Pandas."
            ),
        ),

        # PRIORITY / MANUAL
        Job(
            company="Microsoft Corporation",
            title="Software Engineer I",
            location="Redmond, WA",
            url="https://smoke-test.local/jobs/manual-001",
            source="Smoke Test",
            description=(
                "Develop distributed backend services using "
                "Java, Python, REST APIs, Azure, Docker, "
                "and Kubernetes."
            ),
        ),

        # SENIOR → FILTERED
        Job(
            company="Example Startup",
            title="Senior Software Engineer",
            location="Remote",
            url="https://smoke-test.local/jobs/senior-001",
            source="Smoke Test",
            description=(
                "Build Python backend services using AWS "
                "and distributed systems."
            ),
        ),

        # IRRELEVANT → OTHER → FILTERED
        Job(
            company="Example Sales Company",
            title="Account Executive",
            location="Remote",
            url="https://smoke-test.local/jobs/sales-001",
            source="Smoke Test",
            description=(
                "Manage customer accounts, sales opportunities, "
                "and commercial relationships."
            ),
        ),
    ]


def main() -> None:
    print("=" * 70)
    print("JOB APPLICATION AGENT — MILESTONE 2 SMOKE TEST")
    print("=" * 70)

    # Always start with a fresh isolated smoke-test database.
    if SMOKE_DB_PATH.exists():
        SMOKE_DB_PATH.unlink()

    if SMOKE_EXCEL_PATH.exists():
        SMOKE_EXCEL_PATH.unlink()

    database = JobDatabase(SMOKE_DB_PATH)
    pipeline = build_pipeline(database)

    jobs = build_test_jobs()

    print()
    print(f"Processing {len(jobs)} synthetic jobs...")
    print()

    for number, job in enumerate(jobs, start=1):
        result = pipeline.process(job)

        print("-" * 70)
        print(f"JOB {number}")
        print(f"Company:            {job.company}")
        print(f"Title:              {job.title}")
        print(f"Category:           {job.category.value}")
        print(f"Seniority:          {job.seniority.value}")
        print(f"Company rule:       {job.company_rule.value}")
        print(f"Application method: {job.application_method.value}")
        print(f"Status:              {job.status.value}")
        print(f"Fit score:           {job.fit_score}")
        print(f"Resume:              {job.resume_used}")
        print(f"Outcome:             {result.outcome.value}")
        print(f"Continue:            {result.should_continue}")
        print(f"Reason:              {result.reason}")

    stored_jobs = database.get_all_jobs()

    print()
    print("=" * 70)
    print("DATABASE SUMMARY")
    print("=" * 70)
    print(f"Stored jobs: {len(stored_jobs)}")

    for job in stored_jobs:
        print(
            f"{job.company} | "
            f"{job.title} | "
            f"{job.status.value} | "
            f"{job.application_method.value}"
        )

    # Generate a separate workbook so production tracking data
    # remains untouched.
    tracker = ExcelTracker(
        database=database,
        export_path=SMOKE_EXCEL_PATH,
    )

    generated_path = tracker.generate()

    print()
    print("=" * 70)
    print("SMOKE TEST COMPLETE")
    print("=" * 70)
    print(f"Database: {SMOKE_DB_PATH}")
    print(f"Excel:    {SMOKE_EXCEL_PATH}")


if __name__ == "__main__":
    main()