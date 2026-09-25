import pytest

from app.jobs.classifier import RoleClassifier
from app.jobs.models import Job, JobCategory


@pytest.fixture
def role_config():
    return {
        "categories": {
            "SDE": {
                "enabled": True,
                "titles": [
                    "Software Engineer",
                    "Software Engineer I",
                    "Backend Engineer",
                    "Full Stack Engineer",
                ],
                "keywords": [
                    "software engineering",
                    "backend",
                    "distributed systems",
                    "microservices",
                    "Java",
                    "Python",
                ],
                "resume": "sde",
            },
            "AI_ML": {
                "enabled": True,
                "titles": [
                    "Machine Learning Engineer",
                    "ML Engineer",
                    "AI Engineer",
                    "Applied AI Engineer",
                    "AI Software Engineer",
                ],
                "keywords": [
                    "machine learning",
                    "deep learning",
                    "PyTorch",
                    "TensorFlow",
                    "NLP",
                    "LLM",
                    "RAG",
                ],
                "resume": "ai_ml",
            },
            "DATA_SCIENCE": {
                "enabled": True,
                "titles": [
                    "Data Scientist",
                    "Data Analyst",
                    "Applied Scientist",
                ],
                "keywords": [
                    "data science",
                    "statistics",
                    "Python",
                    "SQL",
                    "Pandas",
                    "machine learning",
                ],
                "resume": "data_science",
            },
            "IT": {
                "enabled": True,
                "titles": [
                    "IT Engineer",
                    "Cloud Engineer",
                    "DevOps Engineer",
                    "Site Reliability Engineer",
                ],
                "keywords": [
                    "AWS",
                    "Azure",
                    "Linux",
                    "Docker",
                    "Kubernetes",
                    "Terraform",
                ],
                "resume": "it",
            },
        }
    }


@pytest.fixture
def classifier(role_config):
    return RoleClassifier(role_config)


def make_job(
    title: str,
    description: str | None = None,
) -> Job:
    return Job(
        company="Example Company",
        title=title,
        location="Seattle, WA",
        url="https://example.com/jobs/123",
        source="Test",
        description=description,
    )


def test_exact_sde_title(classifier):
    result = classifier.classify(
        make_job("Software Engineer")
    )

    assert result.category == JobCategory.SDE
    assert result.confidence == 1.0


def test_exact_ai_ml_title(classifier):
    result = classifier.classify(
        make_job("Machine Learning Engineer")
    )

    assert result.category == JobCategory.AI_ML


def test_exact_data_science_title(classifier):
    result = classifier.classify(
        make_job("Data Scientist")
    )

    assert result.category == JobCategory.DATA_SCIENCE


def test_exact_it_title(classifier):
    result = classifier.classify(
        make_job("Cloud Engineer")
    )

    assert result.category == JobCategory.IT


def test_title_matching_is_case_insensitive(classifier):
    result = classifier.classify(
        make_job("SOFTWARE ENGINEER")
    )

    assert result.category == JobCategory.SDE


def test_longer_title_can_match_configured_title(classifier):
    result = classifier.classify(
        make_job("Senior Machine Learning Engineer")
    )

    assert result.category == JobCategory.AI_ML
    assert result.confidence == 0.9


def test_specific_title_beats_generic_overlap(classifier):
    result = classifier.classify(
        make_job("AI Software Engineer")
    )

    assert result.category == JobCategory.AI_ML
    assert result.confidence == 1.0


def test_keyword_fallback_can_classify_ai_ml(classifier):
    job = make_job(
        "Research Engineer",
        (
            "Build machine learning systems using "
            "PyTorch and deep learning."
        ),
    )

    result = classifier.classify(job)

    assert result.category == JobCategory.AI_ML
    assert "machine learning" in result.matched_keywords
    assert "PyTorch" in result.matched_keywords


def test_keyword_fallback_can_classify_it(classifier):
    job = make_job(
        "Infrastructure Specialist",
        (
            "Operate Linux environments using "
            "Docker, Kubernetes, and Terraform."
        ),
    )

    result = classifier.classify(job)

    assert result.category == JobCategory.IT


def test_single_generic_keyword_is_not_enough(classifier):
    job = make_job(
        "Business Analyst",
        "The candidate should have experience with Python.",
    )

    result = classifier.classify(job)

    assert result.category == JobCategory.OTHER


def test_irrelevant_job_becomes_other(classifier):
    result = classifier.classify(
        make_job(
            "Account Executive",
            "Manage enterprise customer relationships.",
        )
    )

    assert result.category == JobCategory.OTHER


def test_ambiguous_keyword_tie_becomes_other(classifier):
    job = make_job(
        "Technical Associate",
        (
            "Work with backend distributed systems "
            "and machine learning deep learning."
        ),
    )

    result = classifier.classify(job)

    assert result.category == JobCategory.OTHER
    assert "Ambiguous" in result.reason


def test_classify_job_updates_job_category(classifier):
    job = make_job("Backend Engineer")

    returned_job = classifier.classify_job(job)

    assert returned_job is job
    assert job.category == JobCategory.SDE


def test_disabled_category_is_ignored(role_config):
    role_config["categories"]["AI_ML"]["enabled"] = False

    classifier = RoleClassifier(role_config)

    job = make_job("Machine Learning Engineer")

    result = classifier.classify(job)

    assert result.category == JobCategory.OTHER


def test_invalid_category_rejected():
    config = {
        "categories": {
            "INVALID_CATEGORY": {
                "enabled": True,
                "titles": [],
                "keywords": [],
            }
        }
    }

    with pytest.raises(ValueError):
        RoleClassifier(config)