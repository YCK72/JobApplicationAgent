import pytest

from app.jobs.filters import JobFilter
from app.jobs.models import (
    ApplicationStatus,
    Job,
    JobCategory,
    SeniorityLevel,
)


@pytest.fixture
def role_config():
    return {
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
def job_filter(role_config):
    return JobFilter(
        role_config
    )


def make_job(
    title: str = "Software Engineer",
    description: str | None = None,
    category: JobCategory = JobCategory.SDE,
    location: str | None = "Seattle, WA",
) -> Job:
    return Job(
        company="Example Company",
        title=title,
        location=location,
        url="https://example.com/jobs/123",
        source="Test",
        description=description,
        category=category,
    )


def test_junior_title_is_entry_level(
    job_filter,
):
    result = job_filter.classify_seniority(
        make_job(
            "Junior Software Engineer"
        )
    )

    assert (
        result.seniority
        == SeniorityLevel.ENTRY_LEVEL
    )


def test_new_grad_title_is_entry_level(
    job_filter,
):
    result = job_filter.classify_seniority(
        make_job(
            "New Grad Software Engineer"
        )
    )

    assert (
        result.seniority
        == SeniorityLevel.ENTRY_LEVEL
    )


def test_software_engineer_i_is_entry_level(
    job_filter,
):
    result = job_filter.classify_seniority(
        make_job(
            "Software Engineer I"
        )
    )

    assert (
        result.seniority
        == SeniorityLevel.ENTRY_LEVEL
    )


def test_associate_title_is_early_career(
    job_filter,
):
    result = job_filter.classify_seniority(
        make_job(
            "Associate Data Scientist"
        )
    )

    assert (
        result.seniority
        == SeniorityLevel.EARLY_CAREER
    )


def test_senior_title_is_senior(
    job_filter,
):
    result = job_filter.classify_seniority(
        make_job(
            "Senior Software Engineer"
        )
    )

    assert (
        result.seniority
        == SeniorityLevel.SENIOR
    )


@pytest.mark.parametrize(
    "title",
    [
        "Staff Software Engineer",
        "Principal Machine Learning Engineer",
        "Lead Software Engineer",
        "Engineering Manager",
        "Engineering Director",
    ],
)
def test_excluded_titles_are_senior(
    job_filter,
    title,
):
    result = job_filter.classify_seniority(
        make_job(
            title
        )
    )

    assert (
        result.seniority
        == SeniorityLevel.SENIOR
    )


# ============================================================
# Sr / Sr. abbreviation regression tests
# ============================================================


@pytest.mark.parametrize(
    "title",
    [
        "Sr Software Engineer",
        "Sr. Software Engineer",
    ],
)
def test_sr_abbreviation_is_senior(
    job_filter,
    title,
):
    result = job_filter.classify_seniority(
        make_job(
            title
        )
    )

    assert (
        result.seniority
        == SeniorityLevel.SENIOR
    )

    assert result.matched_signal == "sr"


@pytest.mark.parametrize(
    "title",
    [
        "Sr/Principal Software Engineer",
        "Sr./Principal Software Engineer",
    ],
)
def test_sr_principal_title_is_senior(
    job_filter,
    title,
):
    result = job_filter.classify_seniority(
        make_job(
            title
        )
    )

    # Either "sr" or "principal" is valid evidence.
    # The important contract is that the job is classified
    # as senior.
    assert (
        result.seniority
        == SeniorityLevel.SENIOR
    )


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer",
        "Site Reliability Engineer",
        "Research Engineer",
    ],
)
def test_unrelated_titles_do_not_match_sr_abbreviation(
    job_filter,
    title,
):
    result = job_filter.classify_seniority(
        make_job(
            title
        )
    )

    assert (
        result.seniority
        != SeniorityLevel.SENIOR
    )


# ============================================================
# Level classification
# ============================================================


def test_level_ii_is_mid_level(
    job_filter,
):
    result = job_filter.classify_seniority(
        make_job(
            "Software Engineer II"
        )
    )

    assert (
        result.seniority
        == SeniorityLevel.MID_LEVEL
    )


# ============================================================
# Required experience
# ============================================================


def test_two_years_required_is_early_career(
    job_filter,
):
    job = make_job(
        description=(
            "Candidates must have a minimum of "
            "2 years of experience."
        )
    )

    result = job_filter.classify_seniority(
        job
    )

    assert (
        result.seniority
        == SeniorityLevel.EARLY_CAREER
    )


def test_three_years_required_is_mid_level(
    job_filter,
):
    job = make_job(
        description=(
            "Minimum 3 years of experience required."
        )
    )

    result = job_filter.classify_seniority(
        job
    )

    assert (
        result.seniority
        == SeniorityLevel.MID_LEVEL
    )


def test_five_plus_years_required_is_mid_level(
    job_filter,
):
    job = make_job(
        description=(
            "5+ years of experience required "
            "for this position."
        )
    )

    result = job_filter.classify_seniority(
        job
    )

    assert (
        result.seniority
        == SeniorityLevel.MID_LEVEL
    )


def test_preferred_experience_does_not_reject(
    job_filter,
):
    job = make_job(
        description=(
            "3+ years of experience preferred."
        )
    )

    result = job_filter.evaluate(
        job
    )

    assert result.keep is True

    assert (
        result.seniority
        == SeniorityLevel.UNKNOWN
    )


# ============================================================
# Unknown seniority
# ============================================================


def test_unknown_seniority_is_kept(
    job_filter,
):
    result = job_filter.evaluate(
        make_job(
            "Software Engineer"
        )
    )

    assert result.keep is True

    assert (
        result.seniority
        == SeniorityLevel.UNKNOWN
    )


# ============================================================
# Filtering behavior
# ============================================================


def test_senior_job_is_filtered(
    job_filter,
):
    result = job_filter.evaluate(
        make_job(
            "Senior Software Engineer"
        )
    )

    assert result.keep is False

    assert (
        result.seniority
        == SeniorityLevel.SENIOR
    )


def test_mid_level_job_is_filtered(
    job_filter,
):
    job = make_job(
        description=(
            "Minimum 4 years of experience required."
        )
    )

    result = job_filter.evaluate(
        job
    )

    assert result.keep is False

    assert (
        result.seniority
        == SeniorityLevel.MID_LEVEL
    )


def test_other_category_is_filtered(
    job_filter,
):
    job = make_job(
        title="Account Executive",
        category=JobCategory.OTHER,
    )

    result = job_filter.evaluate(
        job
    )

    assert result.keep is False
    assert "OTHER" in result.reason


# ============================================================
# Job mutation behavior
# ============================================================


def test_filter_job_updates_seniority(
    job_filter,
):
    job = make_job(
        "Junior Software Engineer"
    )

    returned_job = job_filter.filter_job(
        job
    )

    assert returned_job is job

    assert (
        job.seniority
        == SeniorityLevel.ENTRY_LEVEL
    )

    assert (
        job.status
        == ApplicationStatus.DISCOVERED
    )


def test_filter_job_marks_rejected_job_filtered(
    job_filter,
):
    job = make_job(
        "Senior Software Engineer"
    )

    job_filter.filter_job(
        job
    )

    assert (
        job.seniority
        == SeniorityLevel.SENIOR
    )

    assert (
        job.status
        == ApplicationStatus.FILTERED_OUT
    )

    assert job.notes is not None
    assert "Filter:" in job.notes


def test_existing_notes_are_preserved(
    job_filter,
):
    job = make_job(
        "Senior Software Engineer"
    )

    job.notes = (
        "Discovered from company careers page."
    )

    job_filter.filter_job(
        job
    )

    assert (
        "Discovered from company careers page."
        in job.notes
    )

    assert "Filter:" in job.notes




# ============================================================
# Location eligibility regression tests
# ============================================================


@pytest.mark.parametrize(
    "location",
    [
        "Seattle, WA",
        "Austin, TX",
        "New York, NY",
        "United States",
        "Remote - United States",
        "Remote, USA",
    ],
)
def test_us_locations_are_allowed(
    job_filter,
    location,
):
    result = job_filter.evaluate(
        make_job(
            location=location,
        )
    )

    assert result.keep is True


@pytest.mark.parametrize(
    "location",
    [
        "India",
        "Toronto, Canada",
        "London, United Kingdom",
        "EMEA",
        "APAC",
        "Worldwide",
        "Europe",
        "Australia",
    ],
)
def test_non_us_locations_are_filtered(
    job_filter,
    location,
):
    result = job_filter.evaluate(
        make_job(
            location=location,
        )
    )

    assert result.keep is False
    assert "location" in result.reason.lower()


def test_generic_remote_location_is_filtered(
    job_filter,
):
    result = job_filter.evaluate(
        make_job(
            location="Remote",
        )
    )

    assert result.keep is False
    assert "remote" in result.reason.lower()


def test_unknown_location_is_filtered(
    job_filter,
):
    result = job_filter.evaluate(
        make_job(
            location=None,
        )
    )

    assert result.keep is False
    assert "location" in result.reason.lower()


@pytest.mark.parametrize(
    "location",
    [
        "United States / India",
        "USA or Canada",
        "Remote - United States / EMEA",
    ],
)
def test_mixed_us_and_excluded_locations_are_filtered(
    job_filter,
    location,
):
    result = job_filter.evaluate(
        make_job(
            location=location,
        )
    )

    assert result.keep is False
    assert "excluded" in result.reason.lower()


def test_india_job_is_filtered_before_downstream_scoring(
    job_filter,
):
    job = make_job(
        title="Cloud Platform Engineer",
        location="India",
    )

    returned_job = job_filter.filter_job(
        job
    )

    assert returned_job is job
    assert (
        job.status
        == ApplicationStatus.FILTERED_OUT
    )
    assert job.fit_score is None
    assert job.resume_used is None
    assert job.notes is not None
    assert "Filter:" in job.notes


# ============================================================
# Configuration validation
# ============================================================


def test_invalid_configuration_rejected():
    with pytest.raises(
        ValueError
    ):
        JobFilter({})

def test_location_does_not_treat_word_in_as_indiana(
    role_config,
):
    job_filter = JobFilter(role_config)

    job = make_job(
        location="Based in office",
    )

    result = job_filter.evaluate(job)

    assert result.keep is False
    assert (
        "could not be verified as United States"
        in result.reason
    )


def test_location_does_not_treat_word_or_as_oregon(
    role_config,
):
    job_filter = JobFilter(role_config)

    job = make_job(
        location="Hybrid or onsite",
    )

    result = job_filter.evaluate(job)

    assert result.keep is False
    assert (
        "could not be verified as United States"
        in result.reason
    )