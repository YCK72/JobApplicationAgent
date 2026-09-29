from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.applications.adapters.detector import (
    ATSProvider,
)
from app.applications.adapters.greenhouse import (
    GreenhouseFormAdapter,
)
from app.applications.adapters.registry import (
    ApplicationAdapterRegistry,
)
from app.applications.browser_form_executor import (
    BrowserFormExecutor,
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
from app.applications.form_validator import (
    ApplicationFormValidator,
)
from app.applications.inspection_service import (
    ApplicationInspectionService,
)
from app.applications.router import (
    ApplicationPreparationService,
)
from app.applications.validator import (
    ApplicationValidator,
)
from app.applications.workflow import (
    ApplicationWorkflow,
)
from app.browser import BrowserSession
from app.browser.form_writer import (
    BrowserFieldWriter,
)
from app.tracking.database import JobDatabase


BrowserSessionFactory = Callable[[], BrowserSession]


def build_application_adapter_registry(
    *,
    browser_session_factory: BrowserSessionFactory = BrowserSession,
) -> ApplicationAdapterRegistry:
    """
    Build the production ATS adapter registry.

    Browser sessions are created lazily when an adapter is created for
    a specific application URL. Merely building the registry does not
    launch Brave or navigate anywhere.
    """

    def create_greenhouse_adapter(
        job_url: str,
    ) -> GreenhouseFormAdapter:
        return GreenhouseFormAdapter(
            job_url=job_url,
            browser_session=browser_session_factory(),
        )

    return ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE:
                create_greenhouse_adapter,
        }
    )


def build_application_inspection_service(
    *,
    analyzer: ApplicationFormAnalyzer,
    planner: ApplicationFormPlanner,
    database: JobDatabase,
    browser_session_factory: BrowserSessionFactory = BrowserSession,
) -> ApplicationInspectionService:
    """
    Build the production application-inspection service.

    This function performs dependency composition only. It does not
    launch a browser or inspect an application.
    """

    registry = build_application_adapter_registry(
        browser_session_factory=browser_session_factory,
    )

    return ApplicationInspectionService(
        registry=registry,
        analyzer=analyzer,
        planner=planner,
        database=database,
        form_validator=ApplicationFormValidator(),
    )


def build_application_workflow(
    *,
    analyzer: ApplicationFormAnalyzer,
    planner: ApplicationFormPlanner,
    database: JobDatabase,
    writer: BrowserFieldWriter,
    allowed_local_fixture: Path,
    browser_session_factory: BrowserSessionFactory = BrowserSession,
) -> ApplicationWorkflow:
    """
    Build the controlled application workflow.

    This function performs dependency composition only.

    Building the workflow does not:

    - launch a browser,
    - inspect an application,
    - authorize an external target,
    - mutate application fields,
    - upload a resume,
    - navigate a page,
    - bypass verification,
    - submit an application.

    Browser inspection remains lazy through the ATS adapter registry.

    Browser field mutation is delegated to the supplied
    BrowserFieldWriter. The writer must already be bound to the
    browser page that will be used for controlled execution.

    External HTTP/HTTPS mutation remains disabled by default at
    workflow execution time. The workflow caller must explicitly
    request external authorization for a specific run.

    Final submission is never authorized by this composition layer.
    """

    preparation_service = ApplicationPreparationService(
        validator=ApplicationValidator(),
        database=database,
    )

    inspection_service = build_application_inspection_service(
        analyzer=analyzer,
        planner=planner,
        database=database,
        browser_session_factory=browser_session_factory,
    )

    form_executor = ApplicationFormExecutor()

    execution_guard = ExternalExecutionGuard(
        allowed_local_fixture=allowed_local_fixture,
    )

    browser_executor = BrowserFormExecutor(
        writer=writer,
    )

    return ApplicationWorkflow(
        preparation_service=preparation_service,
        inspection_service=inspection_service,
        form_executor=form_executor,
        execution_guard=execution_guard,
        browser_executor=browser_executor,
    )