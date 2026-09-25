from pathlib import Path

import pytest

from app.applications.resume_router import ResumeRouter
from app.applications.router import (
    ApplicationPreparationService,
    PreparationOutcome,
)
from app.applications.validator import ApplicationValidator
from app.jobs.classifier import RoleClassifier
from app.jobs.company_router import CompanyRouter
from app.jobs.filters import JobFilter
from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.jobs.pipeline import (
    JobPipeline,
    PipelineOutcome,
)
from app.scoring.fit_gate import FitGate
from app.scoring.fit_scorer import FitScorer
from app.tracking.database import JobDatabase


@pytest.fixture
def company_rules():
    return {
        "default_rule": "AUTO",
        "companies": {
            "Microsoft": {
                "rule": "MANUAL",
                "priority": True,
                "aliases": [
                    "Microsoft Corporation",
                    "Microsoft Corp",
                ],
            },
        },
    }


@pytest.fixture
def roles_config():
    return {
        "fit_scoring": {
            "auto_ready_minimum": 70,
            "manual_review_minimum": 50,
        },
        "location": {
            "allowed_country": "United States",
            "country_aliases": [
                "United States",
                "USA",
                "U.S.",
                "U.S.A.",
            ],
            "allow_us_states": True,
            "allow_remote_us": True,
            "allow_unknown": False,
            "excluded_location_signals": [
                "Global",
                "International",
                "Worldwide",
                "EMEA",
                "Europe",
                "European Union",
                "APAC",
                "Asia",
                "India",
                "Portugal",
                "Canada",
                "Mexico",
                "United Kingdom",
                "UK",
                "Australia",
            ],
        },
        "categories": {
            "SDE": {
                "enabled": True,
                "titles": [
                    "Software Engineer",
                    "Software Engineer I",
                    "Software Developer",
                    "Junior Software Engineer",
                ],
                "keywords": [
                    "software engineering",
                    "backend",
                    "distributed systems",
                    "microservices",
                    "REST API",
                    "Java",
                    "Python",
                ],
            },
            "AI_ML": {
                "enabled": True,
                "titles": [
                    "Machine Learning Engineer",
                    "ML Engineer",
                    "AI Engineer",
                ],
                "keywords": [
                    "machine learning",
                    "deep learning",
                    "PyTorch",
                    "TensorFlow",
                    "MLOps",
                    "RAG",
                ],
            },
            "DATA_SCIENCE": {
                "enabled": True,
                "titles": [
                    "Data Scientist",
                    "Data Scientist I",
                    "Data Analyst",
                ],
                "keywords": [
                    "data science",
                    "statistics",
                    "Python",
                    "SQL",
                    "Pandas",
                    "machine learning",
                ],
            },
            "IT": {
                "enabled": True,
                "titles": [
                    "IT Engineer",
                    "Cloud Engineer",
                    "DevOps Engineer",
                    "Systems Engineer",
                ],
                "keywords": [
                    "AWS",
                    "Azure",
                    "Linux",
                    "Docker",
                    "Kubernetes",
                    "Terraform",
                ],
            },
        },
        "classification_exclusions": {
            "non_target_title_signals": [
                "account executive",
            ],
            "non_job_title_signals": [
                "talent community",
                "talent network",
                "general application",
                "future opportunities",
            ],
        },
        "seniority": {
            "preferred": [
                "entry level",
                "new grad",
                "new graduate",
                "early career",
                "junior",
                "associate",
                "level i",
            ],
            "usually_exclude": [
                "senior",
                "staff",
                "principal",
                "lead",
                "manager",
                "director",
            ],
            "experience": {
                "do_not_reject_preferred_experience_automatically": True,
            },
        },
    }


@pytest.fixture
def database(tmp_path: Path) -> JobDatabase:
    return JobDatabase(
        tmp_path / "integration_test.db"
    )


@pytest.fixture
def resume_file(tmp_path: Path) -> Path:
    path = tmp_path / "sde_resume.pdf"
    path.write_bytes(b"test resume")
    return path


@pytest.fixture
def candidate_config(resume_file: Path):
    return {
        "candidate": {
            "skills": {
                "languages": [
                    "Java",
                    "Python",
                    "SQL",
                ],
                "backend_systems": [
                    "REST API",
                    "Microservices",
                    "Distributed Systems",
                ],
                "databases": [
                    "PostgreSQL",
                    "Redis",
                ],
                "cloud": [
                    "AWS",
                ],
                "devops_infrastructure": [
                    "Docker",
                ],
            },
            "resumes": {
                "sde": str(resume_file),
                "ai_ml": str(resume_file),
                "data_science": str(resume_file),
                "it": str(resume_file),
            },
        },
    }


@pytest.fixture
def pipeline(
    company_rules,
    roles_config,
    candidate_config,
    database,
):
    return JobPipeline(
        company_router=CompanyRouter(
            company_rules
        ),
        classifier=RoleClassifier(
            roles_config
        ),
        job_filter=JobFilter(
            roles_config
        ),
        fit_scorer=FitScorer(
            candidate_config
        ),
        fit_gate=FitGate(
            roles_config
        ),
        resume_router=ResumeRouter(
            candidate_config
        ),
        database=database,
    )


@pytest.fixture
def preparation_service(
    database,
):
    return ApplicationPreparationService(
        validator=ApplicationValidator(),
        database=database,
    )


def make_high_fit_job(
    *,
    company="Example Startup",
    url="https://example.com/jobs/integration-1",
):
    return Job(
        company=company,
        title="Software Engineer I",
        description=(
            "Build Python and Java backend services using "
            "REST API, Microservices, Distributed Systems, "
            "AWS, Docker, PostgreSQL, and Redis."
        ),
        location="Seattle, WA",
        url=url,
        source="Integration Test",
    )


def test_auto_ready_pipeline_job_reaches_persisted_ready_to_apply(
    pipeline,
    preparation_service,
    database,
):
    job = make_high_fit_job()

    pipeline_result = pipeline.process(job)

    assert (
        pipeline_result.outcome
        == PipelineOutcome.AUTO_READY
    )
    assert pipeline_result.should_continue is True
    assert pipeline_result.job_id is not None

    assert (
        job.status
        == ApplicationStatus.NEEDS_APPLICATION
    )

    stored_before = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored_before is not None
    assert (
        stored_before.status
        == ApplicationStatus.NEEDS_APPLICATION
    )

    preparation_result = preparation_service.prepare(
        pipeline_result
    )

    assert (
        preparation_result.outcome
        == PreparationOutcome.READY
    )
    assert preparation_result.should_continue is True

    assert (
        job.status
        == ApplicationStatus.READY_TO_APPLY
    )

    stored_after = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored_after is not None
    assert (
        stored_after.status
        == ApplicationStatus.READY_TO_APPLY
    )


def test_manual_company_never_enters_preparation(
    pipeline,
    preparation_service,
    database,
):
    job = make_high_fit_job(
        company="Microsoft Corporation",
        url="https://example.com/jobs/manual-integration",
    )

    pipeline_result = pipeline.process(job)

    assert (
        pipeline_result.outcome
        == PipelineOutcome.MANUAL_REVIEW
    )
    assert pipeline_result.should_continue is False

    original_status = job.status

    preparation_result = preparation_service.prepare(
        pipeline_result
    )

    assert (
        preparation_result.outcome
        == PreparationOutcome.NOT_ELIGIBLE
    )
    assert preparation_result.should_continue is False

    assert job.status == original_status
    assert job.status == ApplicationStatus.NEEDS_REVIEW

    stored = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW


def test_filtered_job_never_enters_preparation(
    pipeline,
    preparation_service,
    database,
):
    job = Job(
        company="Example Startup",
        title="Senior Software Engineer",
        description=(
            "Build Python backend systems using AWS."
        ),
        location="Seattle, WA",
        url="https://example.com/jobs/senior-integration",
        source="Integration Test",
    )

    pipeline_result = pipeline.process(job)

    assert (
        pipeline_result.outcome
        == PipelineOutcome.FILTERED_OUT
    )

    preparation_result = preparation_service.prepare(
        pipeline_result
    )

    assert (
        preparation_result.outcome
        == PreparationOutcome.NOT_ELIGIBLE
    )

    assert (
        job.status
        == ApplicationStatus.FILTERED_OUT
    )

    stored = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored is not None
    assert (
        stored.status
        == ApplicationStatus.FILTERED_OUT
    )


def test_resume_removed_after_pipeline_requires_review(
    pipeline,
    preparation_service,
    database,
):
    job = make_high_fit_job(
        url="https://example.com/jobs/resume-disappears",
    )

    pipeline_result = pipeline.process(job)

    assert (
        pipeline_result.outcome
        == PipelineOutcome.AUTO_READY
    )

    assert job.resume_used is not None

    resume_path = Path(job.resume_used)

    assert resume_path.is_file()

    resume_path.unlink()

    preparation_result = preparation_service.prepare(
        pipeline_result
    )

    assert (
        preparation_result.outcome
        == PreparationOutcome.NEEDS_REVIEW
    )
    assert preparation_result.should_continue is False

    assert (
        job.status
        == ApplicationStatus.NEEDS_REVIEW
    )

    stored = database.get_job_by_id(
        pipeline_result.job_id
    )

    assert stored is not None
    assert (
        stored.status
        == ApplicationStatus.NEEDS_REVIEW
    )