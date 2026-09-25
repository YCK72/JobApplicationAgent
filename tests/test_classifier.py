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
        },
        "classification_exclusions": {
            "non_target_title_signals": [
                "account executive",
                "sales",
                "sales representative",
                "sales development representative",
                "business development representative",
                "marketing",
                "recruiter",
                "recruiting",
                "talent acquisition",
                "human resources",
                "executive assistant",
                "customer success",
                "finance",
                "financial analyst",
                "legal",
                "counsel",
            ],
            "non_job_title_signals": [
                "talent community",
                "talent network",
                "join our talent community",
                "general application",
                "general interest",
                "open application",
                "future opportunities",
                "future opportunity",
                "expression of interest",
                "don't see a fit",
            ],
        },
    }


@pytest.fixture
def classifier(role_config):
    return RoleClassifier(
        role_config
    )


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


# ============================================================
# Exact title classification
# ============================================================


def test_exact_sde_title(classifier):
    result = classifier.classify(
        make_job(
            "Software Engineer"
        )
    )

    assert result.category == JobCategory.SDE
    assert result.confidence == 1.0


def test_exact_ai_ml_title(classifier):
    result = classifier.classify(
        make_job(
            "Machine Learning Engineer"
        )
    )

    assert result.category == JobCategory.AI_ML


def test_exact_data_science_title(classifier):
    result = classifier.classify(
        make_job(
            "Data Scientist"
        )
    )

    assert (
        result.category
        == JobCategory.DATA_SCIENCE
    )


def test_exact_it_title(classifier):
    result = classifier.classify(
        make_job(
            "Cloud Engineer"
        )
    )

    assert result.category == JobCategory.IT


def test_title_matching_is_case_insensitive(
    classifier,
):
    result = classifier.classify(
        make_job(
            "SOFTWARE ENGINEER"
        )
    )

    assert result.category == JobCategory.SDE


# ============================================================
# Contained title classification
# ============================================================


def test_longer_title_can_match_configured_title(
    classifier,
):
    result = classifier.classify(
        make_job(
            "Senior Machine Learning Engineer"
        )
    )

    assert result.category == JobCategory.AI_ML
    assert result.confidence == 0.9


def test_specific_title_beats_generic_overlap(
    classifier,
):
    result = classifier.classify(
        make_job(
            "AI Software Engineer"
        )
    )

    assert result.category == JobCategory.AI_ML
    assert result.confidence == 1.0


# ============================================================
# Keyword fallback
# ============================================================


def test_keyword_fallback_can_classify_ai_ml(
    classifier,
):
    job = make_job(
        "Research Engineer",
        (
            "Build machine learning systems using "
            "PyTorch and deep learning."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.AI_ML

    assert (
        "machine learning"
        in result.matched_keywords
    )

    assert (
        "PyTorch"
        in result.matched_keywords
    )


def test_keyword_fallback_can_classify_it(
    classifier,
):
    job = make_job(
        "Infrastructure Specialist",
        (
            "Operate Linux environments using "
            "Docker, Kubernetes, and Terraform."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.IT


def test_single_generic_keyword_is_not_enough(
    classifier,
):
    job = make_job(
        "Business Analyst",
        (
            "The candidate should have "
            "experience with Python."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.OTHER


def test_irrelevant_job_becomes_other(
    classifier,
):
    result = classifier.classify(
        make_job(
            "Account Executive",
            (
                "Manage enterprise customer "
                "relationships."
            ),
        )
    )

    assert result.category == JobCategory.OTHER


def test_ambiguous_keyword_tie_becomes_other(
    classifier,
):
    job = make_job(
        "Technical Associate",
        (
            "Work with backend distributed systems "
            "and machine learning deep learning."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.OTHER
    assert "Ambiguous" in result.reason


# ============================================================
# Job mutation
# ============================================================


def test_classify_job_updates_job_category(
    classifier,
):
    job = make_job(
        "Backend Engineer"
    )

    returned_job = classifier.classify_job(
        job
    )

    assert returned_job is job
    assert job.category == JobCategory.SDE


# ============================================================
# Enabled / disabled categories
# ============================================================


def test_disabled_category_is_ignored(
    role_config,
):
    role_config["categories"]["AI_ML"][
        "enabled"
    ] = False

    classifier = RoleClassifier(
        role_config
    )

    job = make_job(
        "Machine Learning Engineer"
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.OTHER


# ============================================================
# Non-target occupation protection
# ============================================================


def test_account_executive_cannot_become_data_science(
    classifier,
):
    """
    Regression test for the live SingleStore false positive.

    A sales posting may discuss Python, SQL, machine learning,
    statistics, or data science because the company sells a
    technical product. That does not make the occupation a
    Data Science role.
    """

    job = make_job(
        "Strategic Account Executive",
        (
            "Work with customers using data science, "
            "statistics, Python, SQL, and machine "
            "learning technologies."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.OTHER
    assert result.confidence == 1.0

    assert (
        result.matched_title
        == "account executive"
    )

    assert (
        "non-target"
        in result.reason.lower()
    )


@pytest.mark.parametrize(
    "title",
    [
        "Enterprise Account Executive",
        "Strategic Account Executive",
        "Sales Representative",
        "Sales Development Representative",
        "Marketing Manager",
        "Technical Recruiter",
        "Talent Acquisition Specialist",
        "Executive Assistant",
        "Customer Success Manager",
    ],
)
def test_non_target_titles_are_other(
    classifier,
    title,
):
    job = make_job(
        title,
        (
            "The role works with Python, SQL, "
            "machine learning, AWS, Docker, "
            "Kubernetes, and data science."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.OTHER


# ============================================================
# Technical title priority over non-target occupations
# ============================================================


def test_technical_title_beats_customer_success_signal(
    classifier,
):
    job = make_job(
        "Software Engineer, Customer Success Platform",
        (
            "Build backend software and "
            "distributed systems."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.SDE

    assert (
        result.matched_title
        == "Software Engineer"
    )


def test_data_scientist_marketing_title_remains_data_science(
    classifier,
):
    job = make_job(
        "Data Scientist, Marketing Analytics",
        (
            "Build statistical models using "
            "Python and SQL."
        ),
    )

    result = classifier.classify(
        job
    )

    assert (
        result.category
        == JobCategory.DATA_SCIENCE
    )

    assert (
        result.matched_title
        == "Data Scientist"
    )


def test_machine_learning_engineer_sales_platform_remains_ai_ml(
    classifier,
):
    job = make_job(
        "Machine Learning Engineer, Sales Platform",
        (
            "Build machine learning models using "
            "PyTorch."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.AI_ML

    assert (
        result.matched_title
        == "Machine Learning Engineer"
    )


# ============================================================
# Generic / non-job posting protection
# ============================================================


@pytest.mark.parametrize(
    "title",
    [
        "Engineering Talent Community",
        "Join Our Talent Community",
        "Engineering Talent Network",
        "General Application",
        "General Interest",
        "Open Application",
        "Future Opportunities",
        "Software Engineering - Future Opportunities",
        "Expression of Interest",
        "Don't See a Fit? Submit a General Application",
    ],
)
def test_generic_non_job_postings_are_other(
    classifier,
    title,
):
    job = make_job(
        title,
        (
            "Candidates may work with Python, SQL, "
            "AWS, Docker, Kubernetes, machine learning, "
            "distributed systems, and data science."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.OTHER
    assert result.confidence == 1.0

    assert (
        "generic"
        in result.reason.lower()
        or "non-specific"
        in result.reason.lower()
    )


def test_technical_title_does_not_override_talent_community(
    classifier,
):
    job = make_job(
        "Software Engineer Talent Community",
        (
            "Build Python backend services and "
            "distributed systems."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.OTHER

    assert (
        result.matched_title
        == "talent community"
    )


def test_technical_title_does_not_override_future_opportunities(
    classifier,
):
    job = make_job(
        "Machine Learning Engineer - Future Opportunities",
        (
            "Build machine learning models using "
            "PyTorch and deep learning."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.OTHER

    assert (
        result.matched_title
        == "future opportunities"
    )


def test_normal_technical_job_is_not_blocked_as_generic(
    classifier,
):
    job = make_job(
        "Software Engineer",
        (
            "Build Python backend services and "
            "distributed systems."
        ),
    )

    result = classifier.classify(
        job
    )

    assert result.category == JobCategory.SDE


# ============================================================
# Configuration validation
# ============================================================


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

    with pytest.raises(
        ValueError
    ):
        RoleClassifier(
            config
        )


def test_missing_classification_exclusions_is_allowed(
    role_config,
):
    role_config.pop(
        "classification_exclusions"
    )

    classifier = RoleClassifier(
        role_config
    )

    result = classifier.classify(
        make_job(
            "Account Executive",
            (
                "Manage enterprise customer "
                "relationships."
            ),
        )
    )

    assert result.category == JobCategory.OTHER


def test_invalid_classification_exclusions_rejected(
    role_config,
):
    role_config[
        "classification_exclusions"
    ] = []

    with pytest.raises(
        ValueError
    ):
        RoleClassifier(
            role_config
        )


def test_invalid_non_target_title_signals_rejected(
    role_config,
):
    role_config[
        "classification_exclusions"
    ][
        "non_target_title_signals"
    ] = "account executive"

    with pytest.raises(
        ValueError
    ):
        RoleClassifier(
            role_config
        )


def test_invalid_non_job_title_signals_rejected(
    role_config,
):
    role_config[
        "classification_exclusions"
    ][
        "non_job_title_signals"
    ] = "talent community"

    with pytest.raises(
        ValueError
    ):
        RoleClassifier(
            role_config
        )