from pathlib import Path
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest

from app.applications.execution_session import ApplicationExecutionSession
from app.applications.router import PreparationOutcome
from app.applications.inspection_service import InspectionOutcome
from app.applications.form_plan import FormAnswerPlan, FormPlanStatus
from app.applications.workflow import ApplicationWorkflowStatus

from app.applications.submission_confirmation import (
    SubmissionConfirmationService,
)
from app.applications.run_coordinator import (
    ApplicationRunCoordinator,
)
from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.applications.validator import (
    ApplicationValidator,
)
from app.applications.adapters.detector import (
    ATSProvider,
)
from app.applications.adapters.greenhouse import (
    GreenhouseFormAdapter,
)
from app.applications.browser_form_executor import (
    BrowserFormExecutor,
)
from app.applications.batch_runner import (
    ApplicationBatchRunner,
)
from app.applications.composition import (
    build_application_adapter_registry,
    build_application_batch_runner,
    build_application_inspection_service,
    build_application_run_coordinator,
    build_application_workflow,
    build_submission_confirmation_service,
)
from app.applications.execution_guard import (
    ExternalExecutionGuard,
)
from app.applications.form_analyzer import (
    ApplicationFormAnalyzer,
)
from app.applications.form_executor import (
    ApplicationFormExecutor,
)
from app.applications.form_plan import (
    ApplicationFormPlanner,
)
from app.applications.router import (
    ApplicationPreparationService,
)
from app.applications.workflow import (
    ApplicationWorkflow,
)
from app.browser import BrowserSession
from app.tracking.database import JobDatabase


def test_registry_build_does_not_create_browser_session() -> None:
    browser_factory = MagicMock()

    registry = build_application_adapter_registry(
        browser_session_factory=browser_factory,
    )

    assert registry.has_adapter(
        ATSProvider.GREENHOUSE
    )

    browser_factory.assert_not_called()


def test_greenhouse_adapter_is_created_lazily() -> None:
    browser_session = MagicMock(
        spec=BrowserSession
    )

    browser_factory = MagicMock(
        return_value=browser_session
    )

    registry = build_application_adapter_registry(
        browser_session_factory=browser_factory,
    )

    url = (
        "https://boards.greenhouse.io/"
        "example/jobs/123"
    )

    adapter = registry.create(
        ATSProvider.GREENHOUSE,
        url,
    )

    browser_factory.assert_called_once_with()

    assert isinstance(
        adapter,
        GreenhouseFormAdapter,
    )

    assert adapter.job_url == url

    assert (
        adapter.browser_session
        is browser_session
    )


def test_each_adapter_gets_its_own_browser_session() -> None:
    first_session = MagicMock(
        spec=BrowserSession
    )

    second_session = MagicMock(
        spec=BrowserSession
    )

    browser_factory = MagicMock(
        side_effect=[
            first_session,
            second_session,
        ]
    )

    registry = build_application_adapter_registry(
        browser_session_factory=browser_factory,
    )

    first = registry.create(
        ATSProvider.GREENHOUSE,
        (
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
    )

    second = registry.create(
        ATSProvider.GREENHOUSE,
        (
            "https://boards.greenhouse.io/"
            "example/jobs/456"
        ),
    )

    assert (
        first.browser_session
        is first_session
    )

    assert (
        second.browser_session
        is second_session
    )

    assert browser_factory.call_count == 2


def test_inspection_service_can_be_composed(
    tmp_path: Path,
) -> None:
    analyzer = MagicMock(
        spec=ApplicationFormAnalyzer
    )

    planner = MagicMock(
        spec=ApplicationFormPlanner
    )

    database = JobDatabase(
        tmp_path / "composition_test.db"
    )

    browser_factory = MagicMock()

    service = build_application_inspection_service(
        analyzer=analyzer,
        planner=planner,
        database=database,
        browser_session_factory=browser_factory,
    )

    assert service.analyzer is analyzer
    assert service.planner is planner
    assert service.database is database

    assert service.registry.has_adapter(
        ATSProvider.GREENHOUSE
    )

    browser_factory.assert_not_called()


def test_build_application_workflow_composes_controlled_layers(
    tmp_path: Path,
) -> None:
    analyzer = MagicMock(
        spec=ApplicationFormAnalyzer
    )

    planner = MagicMock(
        spec=ApplicationFormPlanner
    )

    database = JobDatabase(
        tmp_path / "workflow_composition_test.db"
    )

    local_fixture = (
        tmp_path / "application_fixture.html"
    )

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        allowed_local_fixture=local_fixture,
    )

    assert isinstance(
        workflow,
        ApplicationWorkflow,
    )

    assert isinstance(
        workflow._preparation_service,
        ApplicationPreparationService,
    )

    assert isinstance(
        workflow._form_executor,
        ApplicationFormExecutor,
    )

    assert isinstance(
        workflow._execution_guard,
        ExternalExecutionGuard,
    )

    assert workflow._browser_executor is None
    assert callable(workflow._execution_session_factory)

    assert (
        workflow._preparation_service.database
        is database
    )

    assert (
        workflow._inspection_service.database
        is database
    )

    assert (
        workflow._inspection_service.analyzer
        is analyzer
    )

    assert (
        workflow._inspection_service.planner
        is planner
    )

    assert isinstance(
        workflow._execution_session_factory("https://example.com/jobs/123"),
        ApplicationExecutionSession,
    )

    assert workflow._inspection_service.registry.has_adapter(
        ATSProvider.GREENHOUSE
    )


def test_build_application_workflow_does_not_launch_browser(
    tmp_path: Path,
) -> None:
    analyzer = MagicMock(
        spec=ApplicationFormAnalyzer
    )

    planner = MagicMock(
        spec=ApplicationFormPlanner
    )

    database = JobDatabase(
        tmp_path / "workflow_lazy_browser_test.db"
    )

    browser_session_factory = MagicMock()

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
        browser_session_factory=browser_session_factory,
    )

    assert isinstance(
        workflow,
        ApplicationWorkflow,
    )

    browser_session_factory.assert_not_called()

def test_build_application_workflow_uses_real_validator(
    tmp_path: Path,
) -> None:
    analyzer = MagicMock(
        spec=ApplicationFormAnalyzer
    )

    planner = MagicMock(
        spec=ApplicationFormPlanner
    )

    database = JobDatabase(
        tmp_path / "workflow_validator_test.db"
    )

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    assert isinstance(
        workflow._preparation_service.validator,
        ApplicationValidator,
    )


def test_build_application_workflow_shares_database(
    tmp_path: Path,
) -> None:
    analyzer = MagicMock(
        spec=ApplicationFormAnalyzer
    )

    planner = MagicMock(
        spec=ApplicationFormPlanner
    )

    database = JobDatabase(
        tmp_path / "workflow_shared_database_test.db"
    )

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    assert (
        workflow._preparation_service.database
        is database
    )

    assert (
        workflow._inspection_service.database
        is database
    )


def test_build_application_workflow_creates_execution_session(
    tmp_path: Path,
) -> None:
    analyzer = MagicMock(
        spec=ApplicationFormAnalyzer
    )

    planner = MagicMock(
        spec=ApplicationFormPlanner
    )

    database = JobDatabase(
        tmp_path / "workflow_writer_test.db"
    )

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    assert isinstance(
        workflow._execution_session_factory("https://example.com/jobs/123"),
        ApplicationExecutionSession,
    )


def test_build_application_workflow_preserves_local_fixture(
    tmp_path: Path,
) -> None:
    analyzer = MagicMock(
        spec=ApplicationFormAnalyzer
    )

    planner = MagicMock(
        spec=ApplicationFormPlanner
    )

    database = JobDatabase(
        tmp_path / "workflow_guard_test.db"
    )

    local_fixture = (
        tmp_path / "application_fixture.html"
    )

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        allowed_local_fixture=local_fixture,
    )

    assert (
        workflow._execution_guard._allowed_local_fixture
        == local_fixture.resolve()
    )


def test_composed_execution_components_never_authorize_submission(
    tmp_path: Path,
) -> None:
    analyzer = MagicMock(
        spec=ApplicationFormAnalyzer
    )

    planner = MagicMock(
        spec=ApplicationFormPlanner
    )

    database = JobDatabase(
        tmp_path / "workflow_submission_test.db"
    )

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    assert workflow._execution_guard is not None
    assert workflow._form_executor is not None
    assert workflow._browser_executor is None
    assert callable(workflow._execution_session_factory)

    # These layers expose no workflow-level submission authorization.
    assert not hasattr(
        workflow,
        "submit",
    )

    assert not hasattr(
        BrowserFormExecutor,
        "submit",
    )

def test_submission_confirmation_service_can_be_composed(
    tmp_path: Path,
) -> None:
    database = JobDatabase(
        tmp_path / "confirmation_composition_test.db"
    )

    service = build_submission_confirmation_service(
        database=database,
    )

    assert isinstance(
        service,
        SubmissionConfirmationService,
    )

    assert service.database is database


def test_submission_confirmation_composition_is_independent_of_workflow(
    tmp_path: Path,
) -> None:
    database = JobDatabase(
        tmp_path / "confirmation_independence_test.db"
    )

    service = build_submission_confirmation_service(
        database=database,
    )

    assert isinstance(
        service,
        SubmissionConfirmationService,
    )

    assert not hasattr(
        service,
        "submit",
    )

    assert not hasattr(
        service,
        "workflow",
    )

    assert not hasattr(
        service,
        "browser_executor",
    )

    assert service.database is database


def test_composed_confirmation_service_never_authorizes_submission(
    tmp_path: Path,
) -> None:
    database = JobDatabase(
        tmp_path / "confirmation_submission_test.db"
    )

    service = build_submission_confirmation_service(
        database=database,
    )

    assert not hasattr(
        service,
        "submit",
    )

    assert not hasattr(
        service,
        "may_submit",
    )

def test_workflow_and_confirmation_service_remain_separate_lifecycle_boundaries(
    tmp_path: Path,
) -> None:
    database = JobDatabase(
        tmp_path / "workflow_confirmation_boundary_test.db"
    )

    workflow = build_application_workflow(
        analyzer=MagicMock(
            spec=ApplicationFormAnalyzer
        ),
        planner=MagicMock(
            spec=ApplicationFormPlanner
        ),
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    confirmation_service = (
        build_submission_confirmation_service(
            database=database,
        )
    )

    assert isinstance(
        workflow,
        ApplicationWorkflow,
    )

    assert isinstance(
        confirmation_service,
        SubmissionConfirmationService,
    )

    assert (
        workflow._preparation_service.database
        is database
    )

    assert (
        workflow._inspection_service.database
        is database
    )

    assert confirmation_service.database is database

    # Workflow execution and post-review confirmation are deliberately
    # separate composition boundaries.
    assert not hasattr(
        workflow,
        "submission_confirmation_service",
    )

    assert not hasattr(
        workflow,
        "confirm_submission",
    )

    assert not hasattr(
        workflow,
        "submit",
    )

    assert not hasattr(
        confirmation_service,
        "workflow",
    )

    assert not hasattr(
        confirmation_service,
        "submit",
    )

def test_build_application_run_coordinator_preserves_workflow_identity(
    tmp_path: Path,
) -> None:
    database = JobDatabase(
        tmp_path / "run_coordinator_composition_test.db"
    )

    workflow = build_application_workflow(
        analyzer=MagicMock(
            spec=ApplicationFormAnalyzer
        ),
        planner=MagicMock(
            spec=ApplicationFormPlanner
        ),
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    coordinator = build_application_run_coordinator(
        workflow=workflow,
    )

    assert isinstance(
        coordinator,
        ApplicationRunCoordinator,
    )

    assert coordinator.workflow is workflow


def test_build_application_run_coordinator_has_no_submission_capability(
    tmp_path: Path,
) -> None:
    database = JobDatabase(
        tmp_path / "run_coordinator_submission_test.db"
    )

    workflow = build_application_workflow(
        analyzer=MagicMock(
            spec=ApplicationFormAnalyzer
        ),
        planner=MagicMock(
            spec=ApplicationFormPlanner
        ),
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    coordinator = build_application_run_coordinator(
        workflow=workflow,
    )

    assert not hasattr(
        coordinator,
        "submit",
    )

    assert not hasattr(
        coordinator,
        "confirm_submission",
    )

    assert not hasattr(
        coordinator,
        "submission_confirmation_service",
    )

def test_build_application_batch_runner_preserves_coordinator_identity(
    tmp_path: Path,
) -> None:
    database = JobDatabase(
        tmp_path / "batch_runner_composition_test.db"
    )

    workflow = build_application_workflow(
        analyzer=MagicMock(
            spec=ApplicationFormAnalyzer
        ),
        planner=MagicMock(
            spec=ApplicationFormPlanner
        ),
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    coordinator = build_application_run_coordinator(
        workflow=workflow,
    )

    batch_runner = build_application_batch_runner(
        coordinator=coordinator,
    )

    assert isinstance(
        batch_runner,
        ApplicationBatchRunner,
    )

    assert batch_runner.coordinator is coordinator


def test_build_application_batch_runner_has_no_submission_capability(
    tmp_path: Path,
) -> None:
    database = JobDatabase(
        tmp_path / "batch_runner_submission_test.db"
    )

    workflow = build_application_workflow(
        analyzer=MagicMock(
            spec=ApplicationFormAnalyzer
        ),
        planner=MagicMock(
            spec=ApplicationFormPlanner
        ),
        database=database,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    coordinator = build_application_run_coordinator(
        workflow=workflow,
    )

    batch_runner = build_application_batch_runner(
        coordinator=coordinator,
    )

    assert not hasattr(
        batch_runner,
        "submit",
    )

    assert not hasattr(
        batch_runner,
        "confirm_submission",
    )

    assert not hasattr(
        batch_runner,
        "submission_confirmation_service",
    )

@pytest.mark.parametrize("stop", ["preparation", "inspection", "form", "target", None])
@pytest.mark.parametrize("scheme", ["http", "https"])
def test_composed_workflow_opens_execution_only_after_safety_gates(
    tmp_path: Path, stop: str | None, scheme: str,
) -> None:
    events = []
    target = f"{scheme}://boards.greenhouse.io/example/jobs/123"
    inspection_session = MagicMock(spec=BrowserSession)
    execution_session = MagicMock(spec=BrowserSession)
    execution_session.navigate.return_value.url = target

    def create_browser():
        events.append("browser")
        if events.count("browser") == 1:
            return inspection_session
        return execution_session

    browser_factory = MagicMock(side_effect=create_browser)
    workflow = build_application_workflow(
        analyzer=MagicMock(spec=ApplicationFormAnalyzer),
        planner=MagicMock(spec=ApplicationFormPlanner),
        database=JobDatabase(tmp_path / "gates.db"),
        allowed_local_fixture=tmp_path / "fixture.html",
        browser_session_factory=browser_factory,
    )
    browser_factory.assert_not_called()
    job = SimpleNamespace(url=target, resume_used=None)
    plan = FormAnswerPlan(
        fields=(), status=FormPlanStatus.AUTO_FILL_ALLOWED, reason="Test plan",
    )

    def prepare(result):
        events.append("prepare")
        return SimpleNamespace(
            outcome="STOP" if stop == "preparation" else PreparationOutcome.READY,
            reason="Preparation", job=job, job_id=1,
        )

    def inspect(job, job_id):
        events.append("inspect")
        adapter = workflow._inspection_service.registry.create(
            ATSProvider.GREENHOUSE, target,
        )
        assert adapter.browser_session is inspection_session
        return SimpleNamespace(
            outcome="STOP" if stop == "inspection" else InspectionOutcome.INSPECTED,
            reason="Inspection", plan=plan,
        )

    authorize_form = workflow._form_executor.authorize
    authorize_target = workflow._execution_guard.authorize

    def form(*args, **kwargs):
        events.append("form")
        if stop == "form":
            return SimpleNamespace(status="BLOCKED", may_execute=False, reason="Form")
        return authorize_form(*args, **kwargs)

    def target_guard(*args, **kwargs):
        events.append("target")
        return authorize_target(*args, **kwargs)

    workflow._preparation_service.prepare = MagicMock(side_effect=prepare)
    workflow._inspection_service.inspect = MagicMock(side_effect=inspect)
    workflow._form_executor.authorize = MagicMock(side_effect=form)
    workflow._execution_guard.authorize = MagicMock(side_effect=target_guard)
    if stop == "target":
        result = workflow.run(MagicMock())  # External execution denied by default.
    else:
        result = workflow.run(MagicMock(), allow_external=True)

    expected = ["prepare", "inspect", "browser", "form", "target", "browser"]
    if scheme == "http" and stop in {"target", None}:
        expected = expected[:4]
        assert result.status == ApplicationWorkflowStatus.BLOCKED
        execution_session.__enter__.assert_not_called()
        execution_session.navigate.assert_not_called()
    elif stop is None:
        assert result.status == ApplicationWorkflowStatus.READY_FOR_REVIEW
        execution_session.__enter__.assert_called_once_with()
        execution_session.navigate.assert_called_once_with(target)
        execution_session.__exit__.assert_called_once_with(None, None, None)
    else:
        boundary = {"preparation": 1, "inspection": 3, "form": 4, "target": 5}[stop]
        expected = expected[:boundary]
        assert result.status == (
            ApplicationWorkflowStatus.NOT_ELIGIBLE
            if stop in {"preparation", "inspection"}
            else ApplicationWorkflowStatus.BLOCKED
        )
        execution_session.__enter__.assert_not_called()
        execution_session.navigate.assert_not_called()
    assert events == expected
    assert not result.may_submit
    inspection_session.navigate.assert_not_called()


def test_execution_factory_is_lazy_and_creates_fresh_sessions(tmp_path: Path) -> None:
    first = MagicMock(spec=BrowserSession)
    second = MagicMock(spec=BrowserSession)
    browser_factory = MagicMock(side_effect=[first, second])
    workflow = build_application_workflow(
        analyzer=MagicMock(spec=ApplicationFormAnalyzer),
        planner=MagicMock(spec=ApplicationFormPlanner),
        database=JobDatabase(tmp_path / "fresh.db"),
        allowed_local_fixture=tmp_path / "fixture.html",
        browser_session_factory=browser_factory,
    )
    target = "https://example.com/jobs/123"
    one = workflow._execution_session_factory(target)
    two = workflow._execution_session_factory(target)
    assert one is not two
    browser_factory.assert_not_called()
    with one as executor_one:
        assert isinstance(executor_one, BrowserFormExecutor)
    with two as executor_two:
        assert isinstance(executor_two, BrowserFormExecutor)
    assert executor_one is not executor_two
    assert browser_factory.call_count == 2
    for session in (first, second):
        session.navigate.assert_called_once_with(target)
        session.__exit__.assert_called_once_with(None, None, None)
