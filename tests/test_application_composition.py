from pathlib import Path
from unittest.mock import MagicMock

from app.applications.adapters.detector import (
    ATSProvider,
)
from app.applications.adapters.greenhouse import (
    GreenhouseFormAdapter,
)
from app.applications.composition import (
    build_application_adapter_registry,
    build_application_inspection_service,
)
from app.applications.form_analyzer import (
    ApplicationFormAnalyzer,
)
from app.applications.form_plan import (
    ApplicationFormPlanner,
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