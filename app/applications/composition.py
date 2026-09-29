from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.applications.run_coordinator import (
    ApplicationRunCoordinator,
)
from app.applications.batch_runner import (
    ApplicationBatchRunner,
)
from app.applications.submission_confirmation import (
    SubmissionConfirmationService,
)
from app.applications.single_job import (
    SingleJobApplicationLauncher,
)
from app.applications.submission_recording import (
    SubmissionRecordingRunner,
)
from app.applications.answer_service import (
    build_application_answer_resolver,
)
from app.applications.adapters.detector import (
    ATSProvider,
)
from app.applications.adapters.ashby import AshbyFormAdapter
from app.applications.adapters.greenhouse import (
    GreenhouseFormAdapter,
)
from app.applications.adapters.lever import LeverFormAdapter
from app.applications.adapters.workday import WorkdayFormAdapter
from app.applications.adapters.registry import (
    ApplicationAdapterRegistry,
)
from app.applications.execution_session import (
    ApplicationExecutionSession,
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
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_APPLICATION_DATABASE_PATH = PROJECT_ROOT / "database" / "jobs.db"
DEFAULT_APPLICATION_EXPORT_PATH = (
    PROJECT_ROOT / "data" / "exports" / "Job_Application_Tracker.xlsx"
)
DEFAULT_APPLICATION_ANSWERS_PATH = (
    PROJECT_ROOT / "config" / "application_answers.yaml"
)
DEFAULT_LOCAL_EXECUTION_FIXTURE = (
    PROJECT_ROOT / "data" / "fixtures" / "safe_application_form.html"
)


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

    def create_lever_adapter(
        job_url: str,
    ) -> LeverFormAdapter:
        return LeverFormAdapter(
            job_url=job_url,
            browser_session=browser_session_factory(),
        )

    def create_ashby_adapter(
        job_url: str,
    ) -> AshbyFormAdapter:
        return AshbyFormAdapter(
            job_url=job_url,
            browser_session=browser_session_factory(),
        )

    def create_workday_adapter(
        job_url: str,
    ) -> WorkdayFormAdapter:
        return WorkdayFormAdapter(
            job_url=job_url,
            browser_session=browser_session_factory(),
        )

    return ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE:
                create_greenhouse_adapter,
            ATSProvider.LEVER:
                create_lever_adapter,
            ATSProvider.ASHBY:
                create_ashby_adapter,
            ATSProvider.WORKDAY:
                create_workday_adapter,
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

    Execution uses a lazy ApplicationExecutionSession factory after
    preparation, inspection, form authorization, and target authorization
    succeed. Inspection and execution independently request browser
    sessions from the configured factory; no page is shared between them.

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

    def create_execution_session(
        target_url: str,
    ) -> ApplicationExecutionSession:
        return ApplicationExecutionSession(
            target_url=target_url,
            browser_session_factory=browser_session_factory,
        )

    return ApplicationWorkflow(
        preparation_service=preparation_service,
        inspection_service=inspection_service,
        form_executor=form_executor,
        execution_guard=execution_guard,
        execution_session_factory=create_execution_session,
    )


def build_application_run_coordinator(
    *,
    workflow: ApplicationWorkflow,
) -> ApplicationRunCoordinator:
    """
    Compose the runtime boundary that forwards only eligible,
    persisted pipeline results into ApplicationWorkflow.

    Building the coordinator does not:

    - run discovery or the job pipeline,
    - launch a browser,
    - authorize external execution,
    - fill application fields,
    - submit applications,
    - confirm submission,
    - mark jobs APPLIED.
    """

    return ApplicationRunCoordinator(
        workflow=workflow,
    )


def build_submission_confirmation_service(
    *,
    database: JobDatabase,
) -> SubmissionConfirmationService:
    """
    Build the independent post-review submission-confirmation service.

    This composition boundary is intentionally separate from
    ApplicationWorkflow.

    Building this service does not:

    - launch or manipulate a browser,
    - inspect or fill an application,
    - click or authorize submission,
    - infer submission from workflow completion,
    - mark an application as applied.

    APPLIED can only be recorded later when the caller explicitly
    invokes the returned service with independently supplied
    confirmation evidence.
    """

    return SubmissionConfirmationService(
        database=database,
    )


def build_application_batch_runner(
    *,
    coordinator: ApplicationRunCoordinator,
) -> ApplicationBatchRunner:
    """
    Compose the batch boundary that processes pipeline results through
    the controlled single-result application coordinator.

    Building this runner does not:

    - discover jobs,
    - run JobPipeline,
    - launch a browser,
    - authorize external execution,
    - submit applications,
    - confirm submission,
    - mark jobs APPLIED.
    """

    return ApplicationBatchRunner(
        coordinator=coordinator,
    )


def build_single_job_application_launcher(
    *,
    database_path: Path | str = DEFAULT_APPLICATION_DATABASE_PATH,
    export_path: Path | str = DEFAULT_APPLICATION_EXPORT_PATH,
    answer_config_path: Path | str = DEFAULT_APPLICATION_ANSWERS_PATH,
    allowed_local_fixture: Path = DEFAULT_LOCAL_EXECUTION_FIXTURE,
    browser_session_factory: BrowserSessionFactory = BrowserSession,
) -> SingleJobApplicationLauncher:
    """Compose the exact-ID controlled application launch boundary.

    Composition loads verified ordinary answers but remains browser-lazy.
    External execution is still denied until the launcher receives explicit
    authorization for a run. No component in this boundary submits forms.
    """

    answer_resolver = build_application_answer_resolver(answer_config_path)
    database = JobDatabase(Path(database_path))
    workflow = build_application_workflow(
        analyzer=ApplicationFormAnalyzer(answer_resolver),
        planner=ApplicationFormPlanner(),
        database=database,
        allowed_local_fixture=allowed_local_fixture,
        browser_session_factory=browser_session_factory,
    )
    coordinator = build_application_run_coordinator(workflow=workflow)

    return SingleJobApplicationLauncher(
        database=database,
        coordinator=coordinator,
        tracker=ExcelTracker(
            database=database,
            export_path=Path(export_path),
        ),
    )


def build_submission_recording_runner(
    *,
    database_path: Path | str = DEFAULT_APPLICATION_DATABASE_PATH,
    export_path: Path | str = DEFAULT_APPLICATION_EXPORT_PATH,
) -> SubmissionRecordingRunner:
    """Compose exact-ID post-review recording with tracker refresh."""

    database = JobDatabase(Path(database_path))
    return SubmissionRecordingRunner(
        database=database,
        confirmation_service=build_submission_confirmation_service(
            database=database,
        ),
        tracker=ExcelTracker(
            database=database,
            export_path=Path(export_path),
        ),
    )
