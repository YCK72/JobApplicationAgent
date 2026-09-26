from __future__ import annotations

from collections.abc import Callable

from app.applications.adapters.detector import (
    ATSProvider,
)
from app.applications.adapters.greenhouse import (
    GreenhouseFormAdapter,
)
from app.applications.adapters.registry import (
    ApplicationAdapterRegistry,
)
from app.applications.form_analyzer import (
    ApplicationFormAnalyzer,
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
from app.browser import BrowserSession
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