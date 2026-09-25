import pytest

from app.jobs.models import (
    ApplicationStatus,
    Job,
    JobCategory,
    SeniorityLevel,
)
from app.scoring.fit_scorer import FitScorer


@pytest.fixture
def candidate_config():
    return {
        "candidate": {
            "skills": {
                "languages": [
                    "Java",
                    "Python",
                    "JavaScript",
                    "TypeScript",
                    "SQL",
                    "C++",
                    "Bash",
                    "R",
                ],
                "backend_systems": [
                    "Spring Boot",
                    "FastAPI",
                    "Node.js",
                    "REST API",
                    "Kafka",
                    "Redis",
                    "WebSockets",
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
                    "DynamoDB",
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
                    "GitHub Actions",
                    "CI/CD",
                    "Linux",
                    "Helm",
                ],
                "observability_reliability": [
                    "Prometheus",
                    "Grafana",
                    "Fault Tolerance",
                    "Incident Response",
                ],
                "machine_learning": [
                    "PyTorch",
                    "TensorFlow",
                    "Scikit-Learn",
                    "XGBoost",
                    "SHAP",
                    "MLOps",
                    "Machine Learning",
                    "Deep Learning",
                ],
                "nlp_llm": [
                    "NLP",
                    "LLM",
                    "RAG",
                    "FAISS",
                    "Prompt Engineering",
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
                    "Agile",
                    "Git",
                ],
            }
        }
    }


@pytest.fixture
def scorer(candidate_config):
    return FitScorer(candidate_config)


def make_job(
    *,
    title="Software Engineer",
    description="",
    category=JobCategory.SDE,
    seniority=SeniorityLevel.ENTRY_LEVEL,
    status=ApplicationStatus.DISCOVERED,
):
    return Job(
        company="Example Company",
        title=title,
        location="Seattle, WA",
        url="https://example.com/jobs/123",
        source="Test",
        description=description,
        category=category,
        seniority=seniority,
        status=status,
    )


def test_strong_sde_job_scores_high(scorer):
    job = make_job(
        description=(
            "Build Python and Java backend services using "
            "Spring Boot, REST API, Microservices, AWS, "
            "Docker, PostgreSQL, React, and System Design."
        )
    )

    result = scorer.score(job)

    assert result.score >= 75
    assert "Python" in result.matched_skills
    assert "Spring Boot" in result.matched_skills


def test_strong_ai_ml_job_scores_high(scorer):
    job = make_job(
        title="Machine Learning Engineer",
        category=JobCategory.AI_ML,
        description=(
            "Build Python machine learning systems using "
            "PyTorch, TensorFlow, MLOps, RAG, FAISS, AWS, "
            "Docker, Kubernetes, and Pandas."
        ),
    )

    result = scorer.score(job)

    assert result.score >= 75
    assert "PyTorch" in result.matched_skills
    assert "RAG" in result.matched_skills


def test_strong_data_science_job_scores_high(scorer):
    job = make_job(
        title="Data Scientist",
        category=JobCategory.DATA_SCIENCE,
        description=(
            "Use Python, SQL, Pandas, NumPy, Scikit-Learn, "
            "XGBoost, Feature Engineering, Statistical Testing, "
            "and PostgreSQL."
        ),
    )

    result = scorer.score(job)

    assert result.score >= 75
    assert "Pandas" in result.matched_skills


def test_strong_it_job_scores_high(scorer):
    job = make_job(
        title="Cloud Engineer",
        category=JobCategory.IT,
        description=(
            "Operate AWS infrastructure with Docker, Kubernetes, "
            "Terraform, Linux, Prometheus, Grafana, CI/CD, "
            "and incident response."
        ),
    )

    result = scorer.score(job)

    assert result.score >= 75
    assert "Terraform" in result.matched_skills


def test_weak_job_scores_lower_than_strong_job(scorer):
    weak = make_job(
        description="Help maintain internal software systems."
    )

    strong = make_job(
        description=(
            "Build Python Java REST API Microservices using "
            "Spring Boot, AWS, Docker, PostgreSQL, React, "
            "and System Design."
        )
    )

    assert scorer.score(weak).score < scorer.score(strong).score


def test_entry_level_gets_full_seniority_points(scorer):
    job = make_job(
        seniority=SeniorityLevel.ENTRY_LEVEL,
    )

    result = scorer.score(job)

    assert result.score == 25.0


def test_early_career_gets_full_seniority_points(scorer):
    job = make_job(
        seniority=SeniorityLevel.EARLY_CAREER,
    )

    result = scorer.score(job)

    assert result.score == 25.0


def test_unknown_seniority_is_not_rejected(scorer):
    job = make_job(
        seniority=SeniorityLevel.UNKNOWN,
    )

    result = scorer.score(job)

    assert result.score == 18.0


def test_other_category_scores_zero(scorer):
    job = make_job(
        category=JobCategory.OTHER,
    )

    result = scorer.score(job)

    assert result.score == 0.0
    assert result.matched_skills == ()


def test_filtered_job_scores_zero(scorer):
    job = make_job(
        status=ApplicationStatus.FILTERED_OUT,
    )

    result = scorer.score(job)

    assert result.score == 0.0


def test_score_never_exceeds_100(scorer):
    job = make_job(
        description=(
            "Java Python JavaScript TypeScript SQL C++ Bash R "
            "Spring Boot FastAPI Node.js REST API Kafka Redis "
            "WebSockets Microservices Distributed Systems "
            "System Design React PostgreSQL MySQL MongoDB "
            "DynamoDB AWS Azure Docker Kubernetes Terraform "
            "GitHub Actions CI/CD Linux Helm Prometheus Grafana "
            "Fault Tolerance Incident Response TDD OOP "
            "Data Structures Algorithms Code Review Agile Git"
        )
    )

    result = scorer.score(job)

    assert result.score <= 100.0


def test_score_job_updates_job(scorer):
    job = make_job(
        description=(
            "Python REST API AWS Docker PostgreSQL"
        )
    )

    returned = scorer.score_job(job)

    assert returned is job
    assert job.fit_score is not None
    assert job.fit_explanation is not None


def test_score_job_does_not_change_status(scorer):
    job = make_job(
        description="Python AWS Docker"
    )

    original_status = job.status

    scorer.score_job(job)

    assert job.status == original_status


def test_r_does_not_match_required(scorer):
    job = make_job(
        description=(
            "Experience required for this engineering role."
        )
    )

    result = scorer.score(job)

    assert "R" not in result.matched_skills


def test_git_does_not_match_digital(scorer):
    job = make_job(
        description=(
            "Build digital software products."
        )
    )

    result = scorer.score(job)

    assert "Git" not in result.matched_skills


def test_duplicate_skill_across_groups_counted_once(scorer):
    job = make_job(
        description="Redis"
    )

    result = scorer.score(job)

    assert result.matched_skills.count("Redis") == 1


def test_explanation_contains_score_components(scorer):
    job = make_job(
        description="Python AWS Docker"
    )

    result = scorer.score(job)

    assert "Category:" in result.explanation
    assert "Seniority:" in result.explanation
    assert "Components" in result.explanation


def test_missing_candidate_section_rejected():
    with pytest.raises(ValueError):
        FitScorer({})


def test_missing_skills_rejected():
    with pytest.raises(ValueError):
        FitScorer(
            {
                "candidate": {}
            }
        )


def test_non_list_skill_group_rejected():
    with pytest.raises(ValueError):
        FitScorer(
            {
                "candidate": {
                    "skills": {
                        "languages": "Python"
                    }
                }
            }
        )
