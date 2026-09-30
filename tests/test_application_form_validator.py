import pytest

from app.applications.adapters.detector import (
    ATSProvider,
)
from app.applications.form_models import (
    ApplicationForm,
)
from app.applications.form_validator import (
    ApplicationFormValidator,
)


@pytest.fixture
def validator():
    return ApplicationFormValidator()


def make_form(
    *,
    provider="Greenhouse",
    url="https://boards.greenhouse.io/example/jobs/123",
):
    return ApplicationForm(
        provider=provider,
        job_url=url,
    )


def test_matching_form_is_valid(
    validator,
):
    result = validator.validate(
        form=make_form(),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is True


def test_matching_tiktok_form_is_valid(validator):
    url = "https://careers.tiktok.com/resume/7668557209047894325/apply"
    result = validator.validate(
        form=make_form(provider="TikTok", url=url),
        expected_provider=ATSProvider.TIKTOK,
        expected_job_url=url,
    )

    assert result.valid is True


def test_provider_name_is_case_insensitive(
    validator,
):
    result = validator.validate(
        form=make_form(
            provider="greenHOUSE"
        ),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is True


def test_provider_name_mismatch_is_rejected(
    validator,
):
    result = validator.validate(
        form=make_form(
            provider="Lever"
        ),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is False


def test_form_url_provider_mismatch_is_rejected(
    validator,
):
    result = validator.validate(
        form=make_form(
            url="https://jobs.lever.co/example/123"
        ),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is False


def test_different_job_path_is_rejected(
    validator,
):
    result = validator.validate(
        form=make_form(
            url=(
                "https://boards.greenhouse.io/"
                "example/jobs/456"
            )
        ),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is False


def test_query_string_difference_is_allowed(
    validator,
):
    result = validator.validate(
        form=make_form(
            url=(
                "https://boards.greenhouse.io/"
                "example/jobs/123?gh_src=linkedin"
            )
        ),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is True


def test_fragment_difference_is_allowed(
    validator,
):
    result = validator.validate(
        form=make_form(
            url=(
                "https://boards.greenhouse.io/"
                "example/jobs/123#application"
            )
        ),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is True


def test_trailing_slash_difference_is_allowed(
    validator,
):
    result = validator.validate(
        form=make_form(
            url=(
                "https://boards.greenhouse.io/"
                "example/jobs/123/"
            )
        ),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is True


def test_unknown_expected_provider_is_rejected(
    validator,
):
    result = validator.validate(
        form=make_form(),
        expected_provider=ATSProvider.UNKNOWN,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is False


def test_spoofed_form_hostname_is_rejected(
    validator,
):
    result = validator.validate(
        form=make_form(
            url=(
                "https://boards.greenhouse.io."
                "evil.example/example/jobs/123"
            )
        ),
        expected_provider=ATSProvider.GREENHOUSE,
        expected_job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    assert result.valid is False
