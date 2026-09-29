from pathlib import Path
from unittest.mock import MagicMock

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
from app.applications.composition import (
    build_application_adapter_registry,
    build_application_inspection_service,
    build_application_workflow,
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

    writer = MagicMock()

    local_fixture = (
        tmp_path / "application_fixture.html"
    )

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        writer=writer,
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

    assert isinstance(
        workflow._browser_executor,
        BrowserFormExecutor,
    )

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

    assert (
        workflow._browser_executor._writer
        is writer
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

    writer = MagicMock()

    browser_session_factory = MagicMock()

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        writer=writer,
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
        writer=MagicMock(),
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
        writer=MagicMock(),
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


def test_build_application_workflow_preserves_writer_identity(
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

    writer = MagicMock()

    workflow = build_application_workflow(
        analyzer=analyzer,
        planner=planner,
        database=database,
        writer=writer,
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    assert (
        workflow._browser_executor._writer
        is writer
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
        writer=MagicMock(),
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
        writer=MagicMock(),
        allowed_local_fixture=(
            tmp_path / "application_fixture.html"
        ),
    )

    assert workflow._execution_guard is not None
    assert workflow._form_executor is not None
    assert workflow._browser_executor is not None

    # These layers expose no workflow-level submission authorization.
    assert not hasattr(
        workflow,
        "submit",
    )

    assert not hasattr(
        workflow._browser_executor,
        "submit",
    )