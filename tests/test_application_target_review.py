from pathlib import Path
from unittest.mock import MagicMock

from app.applications.target_review import (
    ApplicationTargetReviewService,
    TargetReviewStatus,
)
from app.jobs.eligibility import EligibilityStatus
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)
from app.jobs.pipeline import JobPipeline, PipelineOutcome
from app.scoring.fit_gate import FitTier
from app.tracking.database import JobDatabase


SOURCE_URL = "https://www.linkedin.com/jobs/view/12345"
TARGET_URL = "https://job-boards.greenhouse.io/example/jobs/123"


def unresolved_job() -> Job:
    return Job(
        company="Example",
        title="Software Engineer I",
        location="Seattle, WA",
        url=SOURCE_URL,
        source="linkedin_composio",
        status=ApplicationStatus.NEEDS_REVIEW,
        application_method=ApplicationMethod.REVIEW,
        notes="Application target requires review.",
    )


def test_review_service_validates_reprocesses_and_refreshes_tracker(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = database.add_job(unresolved_job())
    pipeline = MagicMock()
    tracker = MagicMock()

    def reprocess(existing_id, job):
        assert existing_id == job_id
        assert job.application_url.encoded_string() == TARGET_URL
        database.update_job(existing_id, job)
        return MagicMock(
            job=job,
            outcome=PipelineOutcome.AUTO_READY,
            reason="Reprocessed.",
            job_id=existing_id,
        )

    pipeline.reprocess.side_effect = reprocess
    tracker.generate.return_value = tmp_path / "tracker.xlsx"
    service = ApplicationTargetReviewService(
        database=database,
        pipeline=pipeline,
        tracker=tracker,
    )

    result = service.assign(
        job_id=job_id,
        application_url=TARGET_URL + "?gh_src=review#apply",
    )

    assert result.status == TargetReviewStatus.UPDATED
    assert result.application_url == TARGET_URL
    assert result.pipeline_outcome == PipelineOutcome.AUTO_READY
    stored = database.get_job_by_id(job_id)
    assert stored.application_url.encoded_string() == TARGET_URL
    assert "reviewed application target" in stored.notes.lower()
    tracker.generate.assert_called_once_with()


def test_review_service_rejects_unsupported_target_without_mutation(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = database.add_job(unresolved_job())
    pipeline = MagicMock()
    tracker = MagicMock()
    service = ApplicationTargetReviewService(
        database=database,
        pipeline=pipeline,
        tracker=tracker,
    )

    result = service.assign(
        job_id=job_id,
        application_url="https://jobs.lever.co/example/123",
    )

    assert result.status == TargetReviewStatus.INVALID_TARGET
    assert database.get_job_by_id(job_id).application_url is None
    pipeline.reprocess.assert_not_called()
    tracker.generate.assert_not_called()


def test_review_service_rejects_ineligible_record(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job = unresolved_job()
    job.status = ApplicationStatus.APPLIED
    job_id = database.add_job(job)
    service = ApplicationTargetReviewService(
        database=database,
        pipeline=MagicMock(),
        tracker=MagicMock(),
    )

    result = service.assign(job_id=job_id, application_url=TARGET_URL)

    assert result.status == TargetReviewStatus.NOT_ELIGIBLE
    assert database.get_job_by_id(job_id).application_url is None


def test_review_service_reports_blocked_reprocessing_without_mutation(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = database.add_job(unresolved_job())
    pipeline = MagicMock()
    pipeline.reprocess.return_value = MagicMock(
        outcome=PipelineOutcome.DUPLICATE,
        reason="Duplicate.",
        job_id=None,
    )
    tracker = MagicMock()
    service = ApplicationTargetReviewService(
        database=database,
        pipeline=pipeline,
        tracker=tracker,
    )

    result = service.assign(job_id=job_id, application_url=TARGET_URL)

    assert result.status == TargetReviewStatus.REPROCESS_BLOCKED
    assert database.get_job_by_id(job_id).application_url is None
    tracker.generate.assert_not_called()


def test_pipeline_reprocesses_same_row_without_duplicate(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job = unresolved_job()
    job_id = database.add_job(job)
    job = Job.model_validate({
        **job.model_dump(),
        "application_url": TARGET_URL,
    })

    company_router = MagicMock()
    company_router.route_job.side_effect = lambda item: (
        setattr(item, "company_rule", CompanyRule.AUTO),
        setattr(item, "application_method", ApplicationMethod.AUTO),
        item,
    )[-1]
    classifier = MagicMock()
    job_filter = MagicMock()
    eligibility_gate = MagicMock()
    eligibility_gate.evaluate.return_value = MagicMock(
        status=EligibilityStatus.CLEAR
    )
    fit_scorer = MagicMock()
    fit_scorer.score_job.side_effect = lambda item: setattr(
        item, "fit_score", 90.0
    )
    fit_gate = MagicMock()
    fit_gate.evaluate.return_value = FitTier.HIGH
    resume_router = MagicMock()
    resume_router.route_job.side_effect = lambda item: setattr(
        item, "resume_used", "data/resumes/sde_resume.pdf"
    )
    pipeline = JobPipeline(
        company_router=company_router,
        classifier=classifier,
        job_filter=job_filter,
        fit_scorer=fit_scorer,
        fit_gate=fit_gate,
        resume_router=resume_router,
        database=database,
        eligibility_gate=eligibility_gate,
    )

    result = pipeline.reprocess(job_id, job)

    assert result.outcome == PipelineOutcome.AUTO_READY
    assert result.job_id == job_id
    assert len(database.get_jobs_with_ids()) == 1
    stored = database.get_job_by_id(job_id)
    assert stored.application_url.encoded_string() == TARGET_URL
    assert stored.status == ApplicationStatus.NEEDS_APPLICATION
