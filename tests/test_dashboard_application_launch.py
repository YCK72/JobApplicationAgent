from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.applications.adapters.detector import ATSProvider
from app.applications.single_job import (
    SingleJobLaunchResult,
    SingleJobLaunchStatus,
)
from app.dashboard.application_launch import (
    ApplicationLaunchStatus,
    DashboardApplicationLaunchService,
)
from app.dashboard.review_sessions import ReviewSessionSnapshot
from app.dashboard.application_preview import (
    ApplicationPreviewResult,
    ApplicationPreviewStatus,
)
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)


def ready_preview(
    *,
    job_id: int = 7,
    application_url: str = (
        "https://job-boards.greenhouse.io/example/jobs/123"
    ),
) -> ApplicationPreviewResult:
    job = Job(
        company="Example",
        title="Software Engineer I",
        location="Seattle, WA",
        url="https://www.linkedin.com/jobs/view/123",
        application_url=application_url,
        source="test",
        status=ApplicationStatus.NEEDS_APPLICATION,
        company_rule=CompanyRule.AUTO,
        application_method=ApplicationMethod.AUTO,
        resume_used="data/resumes/sde_resume.pdf",
        fit_score=92,
    )
    return ApplicationPreviewResult(
        status=ApplicationPreviewStatus.READY,
        reason="Browser-free preflight passed.",
        job_id=job_id,
        job=job,
        source_url="https://www.linkedin.com/jobs/view/123",
        application_url=application_url,
        provider=ATSProvider.GREENHOUSE,
        resume="data/resumes/sde_resume.pdf",
    )


def make_service(*, previews=None, now=None, review_sessions=None):
    preview_service = MagicMock()
    if previews is None:
        preview_service.preview.return_value = ready_preview()
    else:
        preview_service.preview.side_effect = previews
    launcher = MagicMock()
    launcher.run.return_value = SingleJobLaunchResult(
        status=SingleJobLaunchStatus.READY_FOR_REVIEW,
        reason="Authorized fields populated; human review required.",
        job_id=7,
        job=ready_preview().job.model_copy(
            update={"status": ApplicationStatus.FORM_STARTED}
        ),
        completed_actions=4,
        export_path=Path("tracker.xlsx"),
    )
    clock = MagicMock(return_value=100.0 if now is None else now)
    tokens = iter(["exact-preview-token", "second-preview-token"])
    service = DashboardApplicationLaunchService(
        preview_service=preview_service,
        launcher=launcher,
        authorization_ttl_seconds=120,
        clock=clock,
        token_factory=lambda: next(tokens),
        review_session_manager=review_sessions,
    )
    return service, preview_service, launcher, clock


def test_prepare_issues_short_lived_exact_job_authorization() -> None:
    service, preview_service, launcher, _ = make_service()

    prepared = service.prepare(7)

    assert prepared.preview.status == ApplicationPreviewStatus.READY
    assert prepared.authorization_token == "exact-preview-token"
    assert prepared.authorization_expires_in_seconds == 120
    preview_service.preview.assert_called_once_with(7)
    launcher.run.assert_not_called()


def test_blocked_preview_never_issues_authorization() -> None:
    blocked = ready_preview()
    blocked = ApplicationPreviewResult(
        **{
            **blocked.__dict__,
            "status": ApplicationPreviewStatus.BLOCKED,
            "reason": "Job is not eligible.",
        }
    )
    service, _, launcher, _ = make_service(previews=[blocked])

    prepared = service.prepare(7)

    assert prepared.authorization_token is None
    assert prepared.authorization_expires_in_seconds is None
    launcher.run.assert_not_called()


def test_exact_fresh_authorization_launches_only_that_job() -> None:
    service, preview_service, launcher, _ = make_service()
    prepared = service.prepare(7)

    result = service.launch(
        job_id=7,
        authorization_token=prepared.authorization_token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )

    assert result.status == ApplicationLaunchStatus.READY_FOR_REVIEW
    assert result.completed_actions == 4
    assert result.may_submit is False
    assert preview_service.preview.call_count == 2
    launcher.run.assert_called_once_with(job_id=7, allow_external=True)


def test_wrong_job_or_confirmation_never_reaches_launcher() -> None:
    service, _, launcher, _ = make_service()
    token = service.prepare(7).authorization_token

    wrong_job = service.launch(
        job_id=8,
        authorization_token=token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )
    wrong_confirmation = service.launch(
        job_id=7,
        authorization_token=token,
        confirmation="yes",
    )

    assert wrong_job.status == ApplicationLaunchStatus.AUTHORIZATION_DENIED
    assert wrong_confirmation.status == (
        ApplicationLaunchStatus.AUTHORIZATION_DENIED
    )
    launcher.run.assert_not_called()


def test_expired_authorization_never_reaches_launcher() -> None:
    service, _, launcher, clock = make_service()
    token = service.prepare(7).authorization_token
    clock.return_value = 221.0

    result = service.launch(
        job_id=7,
        authorization_token=token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )

    assert result.status == ApplicationLaunchStatus.AUTHORIZATION_EXPIRED
    launcher.run.assert_not_called()


def test_changed_job_state_invalidates_preview_authorization() -> None:
    changed = ready_preview(
        application_url="https://job-boards.greenhouse.io/example/jobs/456"
    )
    service, _, launcher, _ = make_service(
        previews=[ready_preview(), changed]
    )
    token = service.prepare(7).authorization_token

    result = service.launch(
        job_id=7,
        authorization_token=token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )

    assert result.status == ApplicationLaunchStatus.PREVIEW_STALE
    launcher.run.assert_not_called()


def test_authorization_token_is_single_use() -> None:
    service, _, launcher, _ = make_service()
    token = service.prepare(7).authorization_token

    first = service.launch(
        job_id=7,
        authorization_token=token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )
    second = service.launch(
        job_id=7,
        authorization_token=token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )

    assert first.status == ApplicationLaunchStatus.READY_FOR_REVIEW
    assert second.status == ApplicationLaunchStatus.AUTHORIZATION_DENIED
    launcher.run.assert_called_once_with(job_id=7, allow_external=True)


def test_dashboard_launch_service_exposes_no_submission_capability() -> None:
    service, _, _, _ = make_service()

    assert not hasattr(service, "submit")
    assert not hasattr(service, "confirm_submission")
    assert not hasattr(service, "submission_confirmation_service")


def test_successful_launch_claims_retained_review_session() -> None:
    sessions = MagicMock()
    sessions.reserve.return_value = True
    sessions.claim.return_value = True
    snapshot = ReviewSessionSnapshot(
        job_id=7,
        target_url="https://job-boards.greenhouse.io/example/jobs/123",
        active=True,
        expires_in_seconds=900,
    )
    sessions.snapshot.side_effect = [None, snapshot]
    service, _, launcher, _ = make_service(review_sessions=sessions)
    token = service.prepare(7).authorization_token

    result = service.launch(
        job_id=7,
        authorization_token=token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )

    assert result.status == ApplicationLaunchStatus.READY_FOR_REVIEW
    assert result.review_session.active is True
    sessions.reserve.assert_called_once_with(7)
    sessions.claim.assert_called_once_with(7)
    sessions.release.assert_not_called()
    launcher.run.assert_called_once_with(job_id=7, allow_external=True)


def test_existing_review_session_blocks_second_launch() -> None:
    sessions = MagicMock()
    sessions.reserve.return_value = False
    sessions.snapshot.return_value = None
    service, _, launcher, _ = make_service(review_sessions=sessions)
    token = service.prepare(7).authorization_token

    result = service.launch(
        job_id=7,
        authorization_token=token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )

    assert result.status == ApplicationLaunchStatus.SESSION_ACTIVE
    launcher.run.assert_not_called()


def test_failed_launch_releases_review_session_reservation() -> None:
    sessions = MagicMock()
    sessions.reserve.return_value = True
    sessions.snapshot.return_value = None
    service, _, launcher, _ = make_service(review_sessions=sessions)
    launcher.run.return_value = SingleJobLaunchResult(
        status=SingleJobLaunchStatus.BLOCKED,
        reason="Blocked.",
        job_id=7,
    )
    token = service.prepare(7).authorization_token

    result = service.launch(
        job_id=7,
        authorization_token=token,
        confirmation="AUTHORIZE_EXTERNAL_BROWSER",
    )

    assert result.status == ApplicationLaunchStatus.BLOCKED
    sessions.release.assert_called_once_with(7)


def test_explicit_close_delegates_to_review_session_manager() -> None:
    sessions = MagicMock()
    sessions.close.return_value = True
    service, _, _, _ = make_service(review_sessions=sessions)

    assert service.close_review_session(7) is True
    sessions.close.assert_called_once_with(7)
