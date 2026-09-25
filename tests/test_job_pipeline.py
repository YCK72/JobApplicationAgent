from pathlib import Path

import pytest

from app.applications.resume_router import ResumeRouter
from app.jobs.classifier import RoleClassifier
from app.jobs.company_router import CompanyRouter
from app.jobs.deduplicator import DuplicateReason
from app.jobs.filters import JobFilter
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
    JobCategory,
)
from app.jobs.pipeline import (
    JobPipeline,
    PipelineOutcome,
)
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
            "Google": {
                "rule": "MANUAL",
                "priority": True,
                "aliases": [
                    "Google LLC",
                ],
            },
            "Blocked Corp": {
                "rule": "BLOCKED",
                "priority": False,
                "aliases": [],
            },
        },
    }


@pytest.fixture
def roles_config():
    return {
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
        "seniority": {
            "preferred": [
                "entry level",
                "new grad",
                "new graduate",
                "university graduate",
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
def candidate_config():
    return {
        "candidate": {
            "skills": {
                "languages": [
                    "Java",
                    "Python",
                    "SQL",
                ],
                "backend_systems": [
                    "Spring Boot",
                    "FastAPI",
                    "REST API",
                    "Kafka",
                    "Redis",
                    "Microservices",
                    "Distributed Systems",
                    "System Design",
                ],
                "frontend": [
                    "React",
                ],
                "databases": [
                    "PostgreSQL",
                    "MySQL",
                    "MongoDB",
                    "Redis",
                ],
                "cloud": [
                    "AWS",
                    "Azure",
                ],
                "devops_infrastructure": [
                    "Docker",
                    "Kubernetes",
                    "Terraform",
                    "CI/CD",
                    "Linux",
                ],
                "observability_reliability": [
                    "Prometheus",
                    "Grafana",
                    "Incident Response",
                ],
                "machine_learning": [
                    "PyTorch",
                    "TensorFlow",
                    "Scikit-Learn",
                    "Machine Learning",
                    "Deep Learning",
                    "MLOps",
                ],
                "nlp_llm": [
                    "NLP",
                    "LLM",
                    "RAG",
                    "FAISS",
                ],
                "data": [
                    "Pandas",
                    "NumPy",
                    "ETL",
                    "Feature Engineering",
                    "Statistical Testing",
                ],
                "engineering_practices": [
                    "TDD",
                    "OOP",
                    "System Design",
                    "Data Structures",
                    "Algorithms",
                    "Code Review",
                    "Git",
                ],
            },
            "resumes": {
                "master_cv": "data/resumes/master_cv.pdf",
                "sde": "data/resumes/sde_resume.pdf",
                "ai_ml": "data/resumes/aiml_resume.pdf",
                "data_science": (
                    "data/resumes/data_science_resume.pdf"
                ),
                "it": "data/resumes/it_resume.pdf",
            },
        }
    }


@pytest.fixture
def database(tmp_path):
    return JobDatabase(
        tmp_path / "pipeline_test.db"
    )


@pytest.fixture
def pipeline(
    company_rules,
    roles_config,
    candidate_config,
    database,
):
    return JobPipeline(
        company_router=CompanyRouter(company_rules),
        classifier=RoleClassifier(roles_config),
        job_filter=JobFilter(roles_config),
        fit_scorer=FitScorer(candidate_config),
        resume_router=ResumeRouter(candidate_config),
        database=database,
    )


def make_job(
    *,
    company="Example Startup",
    title="Software Engineer I",
    description=(
        "Build Python backend services using REST API, "
        "Microservices, AWS, Docker, and PostgreSQL."
    ),
    url="https://example.com/jobs/123",
    location="Seattle, WA",
    external_job_id=None,
):
    return Job(
        company=company,
        title=title,
        description=description,
        location=location,
        url=url,
        source="Test",
        external_job_id=external_job_id,
    )


def test_auto_sde_job_becomes_ready(
    pipeline,
    database,
):
    job = make_job()

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.AUTO_READY
    assert result.should_continue is True

    assert job.category == JobCategory.SDE
    assert job.company_rule == CompanyRule.AUTO
    assert job.application_method == ApplicationMethod.AUTO
    assert job.status == ApplicationStatus.NEEDS_APPLICATION

    assert job.resume_used == "data/resumes/sde_resume.pdf"
    assert job.fit_score is not None
    assert job.fit_score > 0

    assert result.job_id is not None

    stored = database.get_job_by_id(result.job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_APPLICATION
    assert stored.resume_used == "data/resumes/sde_resume.pdf"


def test_auto_ai_ml_job_uses_ai_ml_resume(
    pipeline,
):
    job = make_job(
        title="Machine Learning Engineer",
        description=(
            "Build Python machine learning systems with "
            "PyTorch, MLOps, RAG, AWS, Docker, and Kubernetes."
        ),
        url="https://example.com/jobs/ml-1",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.AUTO_READY
    assert job.category == JobCategory.AI_ML
    assert job.resume_used == "data/resumes/aiml_resume.pdf"


def test_auto_data_science_job_uses_data_resume(
    pipeline,
):
    job = make_job(
        title="Data Scientist I",
        description=(
            "Use Python, SQL, Pandas, NumPy, machine learning, "
            "Feature Engineering, and PostgreSQL."
        ),
        url="https://example.com/jobs/ds-1",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.AUTO_READY
    assert job.category == JobCategory.DATA_SCIENCE
    assert (
        job.resume_used
        == "data/resumes/data_science_resume.pdf"
    )


def test_auto_it_job_uses_it_resume(
    pipeline,
):
    job = make_job(
        title="Cloud Engineer",
        description=(
            "Operate AWS infrastructure using Docker, "
            "Kubernetes, Terraform, Linux, Prometheus, "
            "and Grafana."
        ),
        url="https://example.com/jobs/it-1",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.AUTO_READY
    assert job.category == JobCategory.IT
    assert job.resume_used == "data/resumes/it_resume.pdf"


def test_priority_company_goes_to_manual_review(
    pipeline,
    database,
):
    job = make_job(
        company="Microsoft Corporation",
        url="https://careers.microsoft.com/jobs/123",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.MANUAL_REVIEW
    assert result.should_continue is False

    assert job.company == "Microsoft"
    assert job.priority_company is True
    assert job.company_rule == CompanyRule.MANUAL
    assert job.application_method == ApplicationMethod.MANUAL
    assert job.status == ApplicationStatus.NEEDS_REVIEW

    assert job.resume_used is None
    assert job.fit_score is not None

    stored = database.get_job_by_id(result.job_id)

    assert stored is not None
    assert stored.resume_used is None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW


def test_google_alias_is_manual(
    pipeline,
):
    job = make_job(
        company="Google LLC",
        title="Data Scientist I",
        description=(
            "Python SQL Pandas machine learning statistics."
        ),
        url="https://careers.google.com/jobs/456",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.MANUAL_REVIEW
    assert job.company == "Google"
    assert job.resume_used is None


def test_blocked_company_stops_pipeline(
    pipeline,
    database,
):
    job = make_job(
        company="Blocked Corp",
        url="https://blocked.example/jobs/1",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.BLOCKED
    assert result.should_continue is False

    assert job.company_rule == CompanyRule.BLOCKED
    assert job.application_method == ApplicationMethod.UNKNOWN
    assert job.resume_used is None
    assert job.fit_score is None

    stored = database.get_job_by_id(result.job_id)

    assert stored is not None
    assert stored.company_rule == CompanyRule.BLOCKED


def test_senior_job_is_filtered(
    pipeline,
    database,
):
    job = make_job(
        title="Senior Software Engineer",
        url="https://example.com/jobs/senior-1",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.FILTERED_OUT
    assert result.should_continue is False

    assert job.status == ApplicationStatus.FILTERED_OUT
    assert job.resume_used is None
    assert job.fit_score is None

    stored = database.get_job_by_id(result.job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.FILTERED_OUT


def test_mid_level_required_experience_is_filtered(
    pipeline,
):
    job = make_job(
        title="Software Engineer",
        description=(
            "Minimum 4 years of experience required. "
            "Build Python backend systems."
        ),
        url="https://example.com/jobs/mid-1",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.FILTERED_OUT
    assert job.status == ApplicationStatus.FILTERED_OUT
    assert job.fit_score is None


def test_other_role_is_filtered(
    pipeline,
):
    job = make_job(
        title="Account Executive",
        description=(
            "Manage customer relationships and sales accounts."
        ),
        url="https://example.com/jobs/sales-1",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.FILTERED_OUT
    assert job.category == JobCategory.OTHER
    assert job.status == ApplicationStatus.FILTERED_OUT
    assert job.resume_used is None


def test_exact_url_duplicate_is_not_inserted_twice(
    pipeline,
    database,
):
    first = make_job(
        url="https://example.com/jobs/duplicate"
    )

    first_result = pipeline.process(first)

    assert first_result.outcome == PipelineOutcome.AUTO_READY

    second = make_job(
        url="https://example.com/jobs/duplicate"
    )

    second_result = pipeline.process(second)

    assert second_result.outcome == PipelineOutcome.DUPLICATE
    assert second_result.job_id is None
    assert (
        second_result.duplicate_reason
        == DuplicateReason.URL
    )

    assert len(database.get_all_jobs()) == 1


def test_tracking_parameter_duplicate_is_detected(
    pipeline,
    database,
):
    first = make_job(
        url=(
            "https://example.com/jobs/777"
            "?utm_source=linkedin"
        )
    )

    pipeline.process(first)

    second = make_job(
        url=(
            "https://example.com/jobs/777"
            "?utm_source=google"
        )
    )

    result = pipeline.process(second)

    assert result.outcome == PipelineOutcome.DUPLICATE
    assert result.duplicate_reason == DuplicateReason.URL
    assert len(database.get_all_jobs()) == 1


def test_external_job_id_duplicate_is_detected(
    pipeline,
    database,
):
    first = make_job(
        external_job_id="ABC-123",
        url="https://example.com/jobs/a",
    )

    pipeline.process(first)

    second = make_job(
        external_job_id="abc-123",
        url="https://example.com/jobs/b",
    )

    result = pipeline.process(second)

    assert result.outcome == PipelineOutcome.DUPLICATE
    assert (
        result.duplicate_reason
        == DuplicateReason.EXTERNAL_JOB_ID
    )

    assert len(database.get_all_jobs()) == 1


def test_company_title_location_duplicate_is_detected(
    pipeline,
    database,
):
    first = make_job(
        url="https://example.com/jobs/first",
        location="Seattle, WA",
    )

    pipeline.process(first)

    second = make_job(
        url="https://example.com/jobs/second",
        location="Seattle WA",
    )

    result = pipeline.process(second)

    assert result.outcome == PipelineOutcome.DUPLICATE
    assert (
        result.duplicate_reason
        == DuplicateReason.COMPANY_TITLE_LOCATION
    )

    assert len(database.get_all_jobs()) == 1


def test_different_locations_are_not_false_duplicates(
    pipeline,
    database,
):
    first = make_job(
        url="https://example.com/jobs/location-1",
        location="Seattle, WA",
    )

    second = make_job(
        url="https://example.com/jobs/location-2",
        location="Austin, TX",
    )

    first_result = pipeline.process(first)
    second_result = pipeline.process(second)

    assert first_result.outcome == PipelineOutcome.AUTO_READY
    assert second_result.outcome == PipelineOutcome.AUTO_READY

    assert len(database.get_all_jobs()) == 2


def test_filtered_job_is_still_persisted(
    pipeline,
    database,
):
    job = make_job(
        title="Director of Software Engineering",
        url="https://example.com/jobs/director",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.FILTERED_OUT
    assert result.job_id is not None
    assert len(database.get_all_jobs()) == 1


def test_manual_job_never_gets_auto_resume(
    pipeline,
):
    job = make_job(
        company="Microsoft",
        url="https://microsoft.example/jobs/safety",
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.MANUAL_REVIEW
    assert job.resume_used is None
    assert result.should_continue is False


def test_pipeline_never_marks_job_applied(
    pipeline,
):
    job = make_job(
        url="https://example.com/jobs/not-applied"
    )

    result = pipeline.process(job)

    assert result.outcome == PipelineOutcome.AUTO_READY
    assert job.status == ApplicationStatus.NEEDS_APPLICATION
    assert job.status != ApplicationStatus.APPLIED


def test_existing_notes_are_preserved(
    pipeline,
):
    job = make_job(
        url="https://example.com/jobs/notes"
    )

    job.notes = "Discovered from test source."

    pipeline.process(job)

    assert "Discovered from test source." in job.notes
    assert "Pipeline:" in job.notes


def test_pipeline_result_returns_same_job_object(
    pipeline,
):
    job = make_job(
        url="https://example.com/jobs/object"
    )

    result = pipeline.process(job)

    assert result.job is job