from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.applications.single_job import (
    SingleJobApplicationLauncher,
    SingleJobLaunchResult,
    SingleJobLaunchStatus,
)
from app.applications.composition import (
    build_single_job_application_launcher,
)
from app.applications.workflow import (
    ApplicationWorkflowResult,
    ApplicationWorkflowStatus,
)
from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
)
from app.jobs.pipeline import PipelineOutcome
from app.tracking.database import JobDatabase
from scripts.run_application import main


def add_job(
    database: JobDatabase,
    *,
    status: ApplicationStatus = ApplicationStatus.NEEDS_APPLICATION,
    company_rule: CompanyRule = CompanyRule.AUTO,
    application_method: ApplicationMethod = ApplicationMethod.AUTO,
    url: str = "https://job-boards.greenhouse.io/example/jobs/123",
) -> int:
    return database.add_job(
        Job(
            company="Example",
            title="Software Engineer I",
            location="Seattle, WA",
            url=url,
            source="test",
            status=status,
            company_rule=company_rule,
            application_method=application_method,
            resume_used="data/resumes/sde_resume.pdf",
            fit_score=92,
        )
    )


def make_launcher(
    database: JobDatabase,
    *,
    workflow_result: ApplicationWorkflowResult | None = None,
):
    coordinator = MagicMock()
    coordinator.run.return_value = workflow_result or ApplicationWorkflowResult(
        status=ApplicationWorkflowStatus.READY_FOR_REVIEW,
        reason="Authorized fields populated.",
        completed_actions=3,
    )
    tracker = MagicMock()
    tracker.generate.return_value = Path("tracker.xlsx")
    return (
        SingleJobApplicationLauncher(
            database=database,
            coordinator=coordinator,
            tracker=tracker,
        ),
        coordinator,
        tracker,
    )


def test_missing_job_never_reaches_workflow(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    launcher, coordinator, tracker = make_launcher(database)

    result = launcher.run(job_id=999, allow_external=True)

    assert result.status == SingleJobLaunchStatus.NOT_FOUND
    assert result.may_submit is False
    coordinator.run.assert_not_called()
    tracker.generate.assert_not_called()


@pytest.mark.parametrize(
    ("status", "company_rule", "method"),
    [
        (ApplicationStatus.NEEDS_REVIEW, CompanyRule.AUTO, ApplicationMethod.AUTO),
        (ApplicationStatus.NEEDS_APPLICATION, CompanyRule.MANUAL, ApplicationMethod.MANUAL),
        (ApplicationStatus.NEEDS_APPLICATION, CompanyRule.BLOCKED, ApplicationMethod.UNKNOWN),
    ],
)
def test_ineligible_persisted_job_never_reaches_workflow(
    tmp_path: Path,
    status: ApplicationStatus,
    company_rule: CompanyRule,
    method: ApplicationMethod,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(
        database,
        status=status,
        company_rule=company_rule,
        application_method=method,
    )
    launcher, coordinator, tracker = make_launcher(database)

    result = launcher.run(job_id=job_id, allow_external=True)

    assert result.status == SingleJobLaunchStatus.NOT_ELIGIBLE
    coordinator.run.assert_not_called()
    tracker.generate.assert_not_called()


def test_external_authorization_is_required_before_workflow(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(database)
    launcher, coordinator, tracker = make_launcher(database)

    result = launcher.run(job_id=job_id)

    assert result.status == SingleJobLaunchStatus.AUTHORIZATION_REQUIRED
    assert result.job is not None
    assert result.job.status == ApplicationStatus.NEEDS_APPLICATION
    assert result.may_submit is False
    coordinator.run.assert_not_called()
    tracker.generate.assert_not_called()
    assert database.get_job_by_id(job_id).status == ApplicationStatus.NEEDS_APPLICATION


def test_production_composition_and_preview_remain_browser_lazy(
    tmp_path: Path,
) -> None:
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        "first_name: Test\nlast_name: Candidate\n",
        encoding="utf-8",
    )
    browser_session_factory = MagicMock()
    database_path = tmp_path / "jobs.db"
    launcher = build_single_job_application_launcher(
        database_path=database_path,
        export_path=tmp_path / "tracker.xlsx",
        answer_config_path=answers_path,
        allowed_local_fixture=tmp_path / "fixture.html",
        browser_session_factory=browser_session_factory,
    )
    job_id = add_job(launcher.database)

    result = launcher.run(job_id=job_id)

    assert result.status == SingleJobLaunchStatus.AUTHORIZATION_REQUIRED
    assert result.may_submit is False
    browser_session_factory.assert_not_called()


def test_exact_job_is_reconstructed_as_auto_ready_pipeline_result(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(database)
    launcher, coordinator, _ = make_launcher(database)

    launcher.run(job_id=job_id, allow_external=True)

    pipeline_result = coordinator.run.call_args.args[0]
    assert pipeline_result.job_id == job_id
    assert pipeline_result.outcome == PipelineOutcome.AUTO_READY
    assert pipeline_result.job.url.encoded_string() == (
        "https://job-boards.greenhouse.io/example/jobs/123"
    )
    coordinator.run.assert_called_once_with(
        pipeline_result,
        allow_external=True,
    )


def test_list_eligible_returns_exact_ids_without_running_workflow(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    eligible_id = add_job(database)
    add_job(
        database,
        status=ApplicationStatus.NEEDS_REVIEW,
        url="https://job-boards.greenhouse.io/example/jobs/456",
    )
    launcher, coordinator, tracker = make_launcher(database)

    candidates = launcher.list_eligible()

    assert [candidate.job_id for candidate in candidates] == [eligible_id]
    assert candidates[0].job.status == ApplicationStatus.NEEDS_APPLICATION
    coordinator.run.assert_not_called()
    tracker.generate.assert_not_called()


def test_ready_for_review_is_persisted_as_form_started(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(database)
    launcher, _, tracker = make_launcher(database)

    result = launcher.run(job_id=job_id, allow_external=True)

    assert result.status == SingleJobLaunchStatus.READY_FOR_REVIEW
    assert result.completed_actions == 3
    assert result.may_submit is False
    assert result.export_path == Path("tracker.xlsx")
    assert result.job.status == ApplicationStatus.FORM_STARTED
    stored = database.get_job_by_id(job_id)
    assert stored.status == ApplicationStatus.FORM_STARTED
    assert stored.status != ApplicationStatus.APPLIED
    assert "human review" in stored.notes.lower()
    tracker.generate.assert_called_once_with()


@pytest.mark.parametrize(
    ("workflow_status", "launch_status"),
    [
        (ApplicationWorkflowStatus.NEEDS_REVIEW, SingleJobLaunchStatus.NEEDS_REVIEW),
        (ApplicationWorkflowStatus.BLOCKED, SingleJobLaunchStatus.BLOCKED),
        (ApplicationWorkflowStatus.FAILED, SingleJobLaunchStatus.FAILED),
        (ApplicationWorkflowStatus.NOT_ELIGIBLE, SingleJobLaunchStatus.NOT_ELIGIBLE),
    ],
)
def test_workflow_failures_remain_non_submission_results(
    tmp_path: Path,
    workflow_status: ApplicationWorkflowStatus,
    launch_status: SingleJobLaunchStatus,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(database)
    workflow_result = ApplicationWorkflowResult(
        status=workflow_status,
        reason="Controlled stop.",
        completed_actions=1,
    )
    launcher, _, tracker = make_launcher(
        database,
        workflow_result=workflow_result,
    )

    result = launcher.run(job_id=job_id, allow_external=True)

    assert result.status == launch_status
    assert result.may_submit is False
    assert database.get_job_by_id(job_id).status != ApplicationStatus.APPLIED
    tracker.generate.assert_called_once_with()


def test_form_started_persistence_failure_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(database)
    launcher, _, tracker = make_launcher(database)
    monkeypatch.setattr(
        database,
        "update_application_state",
        MagicMock(side_effect=OSError("database unavailable")),
    )

    result = launcher.run(job_id=job_id, allow_external=True)

    assert result.status == SingleJobLaunchStatus.FAILED
    assert result.may_submit is False
    assert result.job.status == ApplicationStatus.NEEDS_APPLICATION
    tracker.generate.assert_called_once_with()


def test_tracker_refresh_failure_is_visible_and_never_authorizes_submission(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = add_job(database)
    launcher, _, tracker = make_launcher(database)
    tracker.generate.side_effect = OSError("workbook locked")

    result = launcher.run(job_id=job_id, allow_external=True)

    assert result.status == SingleJobLaunchStatus.FAILED
    assert "tracker refresh failed" in result.reason.lower()
    assert result.may_submit is False
    assert database.get_job_by_id(job_id).status == ApplicationStatus.FORM_STARTED
    assert database.get_job_by_id(job_id).status != ApplicationStatus.APPLIED


def test_launcher_exposes_no_submission_or_confirmation_capability(
    tmp_path: Path,
) -> None:
    launcher, _, _ = make_launcher(JobDatabase(tmp_path / "jobs.db"))

    assert not hasattr(launcher, "submit")
    assert not hasattr(launcher, "confirm_submission")
    assert not hasattr(launcher, "submission_confirmation_service")


def test_cli_preview_does_not_authorize_external_execution(
    tmp_path: Path,
    capsys,
) -> None:
    job = Job(
        company="Example",
        title="Software Engineer I",
        location="Seattle, WA",
        url="https://job-boards.greenhouse.io/example/jobs/123",
        source="test",
        status=ApplicationStatus.NEEDS_APPLICATION,
        company_rule=CompanyRule.AUTO,
        application_method=ApplicationMethod.AUTO,
        resume_used="data/resumes/sde_resume.pdf",
        fit_score=92,
    )
    launch_result = SingleJobLaunchResult(
        status=SingleJobLaunchStatus.AUTHORIZATION_REQUIRED,
        reason="Explicit authorization required.",
        job_id=7,
        job=job,
    )
    launcher = MagicMock()
    launcher.run.return_value = launch_result
    builder = MagicMock(return_value=launcher)

    exit_code = main(
        ["--job-id", "7", "--database", str(tmp_path / "jobs.db")],
        launcher_builder=builder,
    )

    assert exit_code == 1
    launcher.run.assert_called_once_with(job_id=7, allow_external=False)
    output = capsys.readouterr().out
    assert '"status": "AUTHORIZATION_REQUIRED"' in output
    assert '"may_submit": false' in output
    assert "sde_resume.pdf" in output


def test_cli_explicit_flag_is_forwarded_to_launcher(tmp_path: Path) -> None:
    launcher = MagicMock()
    launcher.run.return_value = SingleJobLaunchResult(
        status=SingleJobLaunchStatus.READY_FOR_REVIEW,
        reason="Human review required.",
        job_id=7,
        job=MagicMock(
            company="Example",
            title="Engineer",
            location="Seattle",
            url="https://example.com/jobs/7",
            fit_score=90,
            resume_used="resume.pdf",
            status=ApplicationStatus.FORM_STARTED,
        ),
        completed_actions=2,
        export_path=tmp_path / "tracker.xlsx",
    )

    exit_code = main(
        ["--job-id", "7", "--allow-external"],
        launcher_builder=MagicMock(return_value=launcher),
    )

    assert exit_code == 0
    launcher.run.assert_called_once_with(job_id=7, allow_external=True)


def test_cli_lists_eligible_ids_without_running_application(capsys) -> None:
    job = MagicMock(
        company="Example",
        title="Engineer",
        location="Seattle",
        fit_score=90,
        status=ApplicationStatus.NEEDS_APPLICATION,
    )
    launcher = MagicMock()
    launcher.list_eligible.return_value = [
        SimpleNamespace(job_id=7, job=job),
    ]

    exit_code = main(
        ["--list-eligible"],
        launcher_builder=MagicMock(return_value=launcher),
    )

    assert exit_code == 0
    assert '"job_id": 7' in capsys.readouterr().out
    launcher.run.assert_not_called()


@pytest.mark.parametrize("job_id", ["0", "-1"])
def test_cli_rejects_non_positive_job_id(job_id: str) -> None:
    with pytest.raises(SystemExit):
        main(["--job-id", job_id], launcher_builder=MagicMock())


def test_cli_rejects_external_authorization_without_exact_job() -> None:
    with pytest.raises(SystemExit):
        main(
            ["--list-eligible", "--allow-external"],
            launcher_builder=MagicMock(),
        )
