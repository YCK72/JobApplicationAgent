from pathlib import Path

from app.applications.validator import (
    ApplicationValidator,
)
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)


def make_job(
    *,
    company_rule=CompanyRule.AUTO,
    application_method=ApplicationMethod.AUTO,
    status=ApplicationStatus.NEEDS_APPLICATION,
    resume_used=None,
):
    return Job(
        company="Example Company",
        title="Software Engineer",
        location="Seattle, WA",
        url="https://job-boards.greenhouse.io/example/jobs/123",
        source="test",
        company_rule=company_rule,
        application_method=application_method,
        status=status,
        resume_used=resume_used,
    )


def test_valid_auto_job_is_ready(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    result = validator.validate(
        make_job(
            resume_used=str(resume),
        )
    )

    assert result.ready is True


def test_prepare_sets_ready_to_apply(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    job = make_job(
        resume_used=str(resume),
    )

    returned_job = validator.prepare(job)

    assert returned_job is job
    assert (
        job.status
        == ApplicationStatus.READY_TO_APPLY
    )


def test_missing_resume_assignment_requires_review():
    validator = ApplicationValidator()

    job = make_job(
        resume_used=None,
    )

    result = validator.validate(job)

    assert result.ready is False

    validator.prepare(job)

    assert (
        job.status
        == ApplicationStatus.NEEDS_REVIEW
    )


def test_missing_resume_file_requires_review(
    tmp_path,
):
    missing_resume = (
        tmp_path / "does_not_exist.pdf"
    )

    validator = ApplicationValidator()

    job = make_job(
        resume_used=str(missing_resume),
    )

    result = validator.validate(job)

    assert result.ready is False

    validator.prepare(job)

    assert (
        job.status
        == ApplicationStatus.NEEDS_REVIEW
    )


def test_manual_company_cannot_become_ready(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    job = make_job(
        company_rule=CompanyRule.MANUAL,
        application_method=ApplicationMethod.MANUAL,
        resume_used=str(resume),
    )

    validator.prepare(job)

    assert (
        job.status
        == ApplicationStatus.NEEDS_REVIEW
    )


def test_review_method_cannot_become_ready(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    job = make_job(
        application_method=ApplicationMethod.REVIEW,
        resume_used=str(resume),
    )

    validator.prepare(job)

    assert (
        job.status
        == ApplicationStatus.NEEDS_REVIEW
    )


def test_wrong_starting_status_cannot_become_ready(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    job = make_job(
        status=ApplicationStatus.DISCOVERED,
        resume_used=str(resume),
    )

    validator.prepare(job)

    assert (
            job.status
            == ApplicationStatus.DISCOVERED
    )


def test_failed_validation_adds_reason_to_notes():
    validator = ApplicationValidator()

    job = make_job(
        resume_used=None,
    )

    validator.prepare(job)

    assert job.notes is not None
    assert "Application validation:" in job.notes
    assert "No resume" in job.notes


def test_existing_notes_are_preserved():
    validator = ApplicationValidator()

    job = make_job(
        resume_used=None,
    )
    job.notes = "Existing pipeline note."

    validator.prepare(job)

    assert "Existing pipeline note." in job.notes
    assert "Application validation:" in job.notes

def test_filtered_out_status_is_not_overwritten(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    job = make_job(
        status=ApplicationStatus.FILTERED_OUT,
        resume_used=str(resume),
    )

    validator.prepare(job)

    assert (
        job.status
        == ApplicationStatus.FILTERED_OUT
    )


def test_applied_status_is_not_overwritten(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    job = make_job(
        status=ApplicationStatus.APPLIED,
        resume_used=str(resume),
    )

    validator.prepare(job)

    assert (
        job.status
        == ApplicationStatus.APPLIED
    )


def test_rejected_status_is_not_overwritten(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    job = make_job(
        status=ApplicationStatus.REJECTED,
        resume_used=str(resume),
    )

    validator.prepare(job)

    assert (
        job.status
        == ApplicationStatus.REJECTED
    )


def test_offer_status_is_not_overwritten(
    tmp_path,
):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test resume")

    validator = ApplicationValidator()

    job = make_job(
        status=ApplicationStatus.OFFER,
        resume_used=str(resume),
    )

    validator.prepare(job)

    assert (
        job.status
        == ApplicationStatus.OFFER
    )
