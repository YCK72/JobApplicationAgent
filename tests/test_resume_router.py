import pytest

from app.applications.resume_router import ResumeRouter
from app.jobs.models import (
    ApplicationMethod,
    CompanyRule,
    Job,
    JobCategory,
)


@pytest.fixture
def candidate_config():
    return {
        "candidate": {
            "resumes": {
                "master_cv": "data/resumes/master_cv.pdf",
                "sde": "data/resumes/sde_resume.pdf",
                "ai_ml": "data/resumes/aiml_resume.pdf",
                "data_science": (
                    "data/resumes/data_science_resume.pdf"
                ),
                "it": "data/resumes/it_resume.pdf",
            }
        }
    }


@pytest.fixture
def router(candidate_config):
    return ResumeRouter(candidate_config)


def make_job(
    *,
    company="Example Company",
    category=JobCategory.SDE,
    company_rule=CompanyRule.AUTO,
    priority_company=False,
    application_method=ApplicationMethod.AUTO,
):
    return Job(
        company=company,
        title="Software Engineer",
        location="Seattle, WA",
        url="https://example.com/jobs/123",
        source="Test",
        category=category,
        company_rule=company_rule,
        priority_company=priority_company,
        application_method=application_method,
    )


def test_sde_routes_to_sde_resume(router):
    result = router.route(
        make_job(category=JobCategory.SDE)
    )

    assert result.resume_key == "sde"
    assert (
        result.resume_path
        == "data/resumes/sde_resume.pdf"
    )
    assert result.manual_tailoring_required is False


def test_ai_ml_routes_to_ai_ml_resume(router):
    result = router.route(
        make_job(category=JobCategory.AI_ML)
    )

    assert result.resume_key == "ai_ml"
    assert (
        result.resume_path
        == "data/resumes/aiml_resume.pdf"
    )


def test_data_science_routes_to_data_science_resume(
    router,
):
    result = router.route(
        make_job(category=JobCategory.DATA_SCIENCE)
    )

    assert result.resume_key == "data_science"
    assert (
        result.resume_path
        == "data/resumes/data_science_resume.pdf"
    )


def test_it_routes_to_it_resume(router):
    result = router.route(
        make_job(category=JobCategory.IT)
    )

    assert result.resume_key == "it"
    assert (
        result.resume_path
        == "data/resumes/it_resume.pdf"
    )


def test_other_category_gets_no_resume(router):
    result = router.route(
        make_job(category=JobCategory.OTHER)
    )

    assert result.resume_path is None
    assert result.resume_key is None
    assert result.manual_tailoring_required is False


def test_manual_company_gets_no_automatic_resume(router):
    job = make_job(
        company="Microsoft",
        company_rule=CompanyRule.MANUAL,
        application_method=ApplicationMethod.MANUAL,
    )

    result = router.route(job)

    assert result.resume_path is None
    assert result.resume_key is None
    assert result.manual_tailoring_required is True


def test_priority_company_gets_no_automatic_resume(router):
    job = make_job(
        company="Google",
        priority_company=True,
    )

    result = router.route(job)

    assert result.resume_path is None
    assert result.manual_tailoring_required is True


def test_manual_application_method_protects_job(router):
    job = make_job(
        application_method=ApplicationMethod.MANUAL,
    )

    result = router.route(job)

    assert result.resume_path is None
    assert result.manual_tailoring_required is True


def test_blocked_company_gets_no_resume(router):
    job = make_job(
        company_rule=CompanyRule.BLOCKED,
    )

    result = router.route(job)

    assert result.resume_path is None
    assert result.resume_key is None
    assert result.manual_tailoring_required is False


def test_route_job_updates_resume_used(router):
    job = make_job(
        category=JobCategory.SDE
    )

    returned = router.route_job(job)

    assert returned is job
    assert (
        job.resume_used
        == "data/resumes/sde_resume.pdf"
    )


def test_route_job_clears_resume_for_manual_job(router):
    job = make_job(
        company_rule=CompanyRule.MANUAL,
    )

    job.resume_used = "old_resume.pdf"

    router.route_job(job)

    assert job.resume_used is None


def test_missing_candidate_section_rejected():
    with pytest.raises(ValueError):
        ResumeRouter({})


def test_missing_resumes_rejected():
    with pytest.raises(ValueError):
        ResumeRouter(
            {
                "candidate": {}
            }
        )


def test_non_string_resume_path_rejected():
    with pytest.raises(ValueError):
        ResumeRouter(
            {
                "candidate": {
                    "resumes": {
                        "sde": 123
                    }
                }
            }
        )


def test_empty_resume_path_rejected():
    with pytest.raises(ValueError):
        ResumeRouter(
            {
                "candidate": {
                    "resumes": {
                        "sde": "   "
                    }
                }
            }
        )


def test_missing_category_resume_raises_error():
    router = ResumeRouter(
        {
            "candidate": {
                "resumes": {
                    "ai_ml": "ai_ml.pdf"
                }
            }
        }
    )

    job = make_job(
        category=JobCategory.SDE
    )

    with pytest.raises(ValueError):
        router.route(job)