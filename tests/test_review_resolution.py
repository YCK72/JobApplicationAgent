from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.dashboard.review_resolution import (
    ApplicationReviewResolutionService,
    ReviewResolutionOutcome,
    ReviewResolutionStatus,
)
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    Job,
)
from app.tracking.database import JobDatabase


def review_job() -> Job:
    return Job(
        company="Example",
        title="Software Engineer I",
        location="Seattle, WA",
        url="https://www.linkedin.com/jobs/view/123",
        source="linkedin_composio",
        status=ApplicationStatus.NEEDS_REVIEW,
        application_method=ApplicationMethod.REVIEW,
    )


def make_service(tmp_path: Path):
    database = JobDatabase(tmp_path / "jobs.db")
    tracker = MagicMock()
    tracker.generate.return_value = tmp_path / "tracker.xlsx"
    return (
        database,
        tracker,
        ApplicationReviewResolutionService(
            database=database,
            tracker=tracker,
        ),
    )


@pytest.mark.parametrize(
    "outcome",
    list(ReviewResolutionOutcome),
)
def test_records_review_decision_without_changing_application_status(
    tmp_path: Path,
    outcome: ReviewResolutionOutcome,
) -> None:
    database, tracker, service = make_service(tmp_path)
    job_id = database.add_job(review_job())

    result = service.record(
        job_id=job_id,
        outcome=outcome.value,
        note="Reviewed the source listing and documented the decision.",
    )

    assert result.status == ReviewResolutionStatus.RECORDED
    assert result.record.outcome == outcome
    assert result.record.review_kind == "TARGET_REQUIRED"
    assert result.export_path == tmp_path / "tracker.xlsx"
    assert database.get_job_by_id(job_id).status == ApplicationStatus.NEEDS_REVIEW
    tracker.generate.assert_called_once_with()


def test_history_is_append_only_and_latest_is_kind_scoped(tmp_path: Path) -> None:
    database, _, service = make_service(tmp_path)
    job_id = database.add_job(review_job())

    service.record(
        job_id=job_id,
        outcome="DEFERRED",
        note="Waiting for the company application link.",
    )
    service.record(
        job_id=job_id,
        outcome="DISMISSED",
        note="The role closed before an application target appeared.",
    )

    history = database.get_review_resolutions(job_id)
    latest = service.latest(job_id, "TARGET_REQUIRED")

    assert [item["outcome"] for item in history] == [
        "DEFERRED",
        "DISMISSED",
    ]
    assert latest.outcome == ReviewResolutionOutcome.DISMISSED

    service_history = service.history(job_id)
    assert [record.outcome for record in service_history] == [
        ReviewResolutionOutcome.DEFERRED,
        ReviewResolutionOutcome.DISMISSED,
    ]


@pytest.mark.parametrize("note", [None, "", "  ", "ok"])
def test_note_is_required_and_meaningful(
    tmp_path: Path,
    note: str | None,
) -> None:
    database, tracker, service = make_service(tmp_path)
    job_id = database.add_job(review_job())

    result = service.record(
        job_id=job_id,
        outcome="RESOLVED",
        note=note,
    )

    assert result.status == ReviewResolutionStatus.INVALID
    assert database.get_review_resolutions(job_id) == []
    tracker.generate.assert_not_called()


def test_job_without_active_review_cannot_receive_decision(tmp_path: Path) -> None:
    database, tracker, service = make_service(tmp_path)
    job = Job.model_validate({
        **review_job().model_dump(),
        "status": ApplicationStatus.NEEDS_APPLICATION,
        "application_method": ApplicationMethod.AUTO,
        "application_url": "https://jobs.lever.co/example/123/apply",
    })
    job_id = database.add_job(job)

    result = service.record(
        job_id=job_id,
        outcome="RESOLVED",
        note="No review remains.",
    )

    assert result.status == ReviewResolutionStatus.NOT_REQUIRED
    assert database.get_review_resolutions(job_id) == []
    tracker.generate.assert_not_called()


def test_closed_decision_hides_only_the_matching_review_kind(
    tmp_path: Path,
) -> None:
    database, _, service = make_service(tmp_path)
    job_id = database.add_job(review_job())
    service.record(
        job_id=job_id,
        outcome="RESOLVED",
        note="The missing-target review was handled manually.",
    )

    matching = service.apply_latest(
        job_id,
        {
            "review_required": True,
            "review_kind": "TARGET_REQUIRED",
            "review_reason": "Target missing.",
        },
    )
    changed = service.apply_latest(
        job_id,
        {
            "review_required": True,
            "review_kind": "APPLICATION_ERROR",
            "review_reason": "New processing error.",
        },
    )

    assert matching["review_required"] is False
    assert matching["review_outcome"] == "RESOLVED"
    assert changed["review_required"] is True
    assert changed["review_outcome"] is None


def test_tracker_failure_keeps_durable_resolution(tmp_path: Path) -> None:
    database, tracker, service = make_service(tmp_path)
    job_id = database.add_job(review_job())
    tracker.generate.side_effect = OSError("workbook locked")

    result = service.record(
        job_id=job_id,
        outcome="DEFERRED",
        note="Retry after the workbook is available.",
    )

    assert result.status == ReviewResolutionStatus.RECORDED
    assert result.export_path is None
    assert "workbook locked" in result.tracker_error
    assert len(database.get_review_resolutions(job_id)) == 1
