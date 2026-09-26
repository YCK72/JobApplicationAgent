import pytest

from app.applications.adapters.base import (
    ApplicationFormAdapter,
)
from app.applications.adapters.detector import (
    ATSProvider,
)
from app.applications.adapters.registry import (
    AdapterNotAvailableError,
    ApplicationAdapterRegistry,
)
from app.applications.form_models import (
    ApplicationForm,
)


class FakeGreenhouseAdapter(
    ApplicationFormAdapter
):
    def __init__(self, job_url: str) -> None:
        self.job_url = job_url

    @property
    def provider_name(self) -> str:
        return "Greenhouse"

    def inspect(self) -> ApplicationForm:
        return ApplicationForm(
            provider=self.provider_name,
            job_url=self.job_url,
        )


class FakeLeverAdapter(
    ApplicationFormAdapter
):
    def __init__(self, job_url: str) -> None:
        self.job_url = job_url

    @property
    def provider_name(self) -> str:
        return "Lever"

    def inspect(self) -> ApplicationForm:
        return ApplicationForm(
            provider=self.provider_name,
            job_url=self.job_url,
        )


def greenhouse_factory(
    job_url: str,
) -> ApplicationFormAdapter:
    return FakeGreenhouseAdapter(job_url)


def lever_factory(
    job_url: str,
) -> ApplicationFormAdapter:
    return FakeLeverAdapter(job_url)


def test_registered_factory_creates_adapter():
    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE:
                greenhouse_factory,
        }
    )

    url = (
        "https://boards.greenhouse.io/"
        "example/jobs/123"
    )

    result = registry.create(
        ATSProvider.GREENHOUSE,
        url,
    )

    assert isinstance(
        result,
        FakeGreenhouseAdapter,
    )
    assert result.job_url == url


def test_multiple_factories_can_be_registered():
    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE:
                greenhouse_factory,
            ATSProvider.LEVER:
                lever_factory,
        }
    )

    greenhouse = registry.create(
        ATSProvider.GREENHOUSE,
        "https://boards.greenhouse.io/example/jobs/123",
    )

    lever = registry.create(
        ATSProvider.LEVER,
        "https://jobs.lever.co/example/123",
    )

    assert isinstance(
        greenhouse,
        FakeGreenhouseAdapter,
    )

    assert isinstance(
        lever,
        FakeLeverAdapter,
    )


def test_job_url_is_passed_to_factory():
    received_urls = []

    def factory(
        job_url: str,
    ) -> ApplicationFormAdapter:
        received_urls.append(job_url)
        return FakeGreenhouseAdapter(job_url)

    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE: factory,
        }
    )

    url = (
        "https://boards.greenhouse.io/"
        "example/jobs/456"
    )

    registry.create(
        ATSProvider.GREENHOUSE,
        url,
    )

    assert received_urls == [url]


def test_unregistered_known_provider_fails_closed():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(
        AdapterNotAvailableError
    ):
        registry.create(
            ATSProvider.GREENHOUSE,
            "https://boards.greenhouse.io/example/jobs/123",
        )


def test_unknown_provider_fails_closed():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(
        AdapterNotAvailableError
    ):
        registry.create(
            ATSProvider.UNKNOWN,
            "https://example.com/jobs/123",
        )


def test_invalid_provider_fails_closed():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(
        AdapterNotAvailableError
    ):
        registry.create(
            "GREENHOUSE",
            "https://boards.greenhouse.io/example/jobs/123",
        )


def test_unknown_provider_cannot_be_registered():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(ValueError):
        registry.register(
            ATSProvider.UNKNOWN,
            greenhouse_factory,
        )


def test_invalid_provider_cannot_be_registered():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(TypeError):
        registry.register(
            "GREENHOUSE",
            greenhouse_factory,
        )


def test_non_callable_factory_cannot_be_registered():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(TypeError):
        registry.register(
            ATSProvider.GREENHOUSE,
            object(),
        )


def test_factory_must_return_adapter():
    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE:
                lambda job_url: object(),
        }
    )

    with pytest.raises(
        TypeError,
        match="must return",
    ):
        registry.create(
            ATSProvider.GREENHOUSE,
            "https://boards.greenhouse.io/example/jobs/123",
        )


def test_has_adapter_true_for_registered_provider():
    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE:
                greenhouse_factory,
        }
    )

    assert (
        registry.has_adapter(
            ATSProvider.GREENHOUSE
        )
        is True
    )


def test_has_adapter_false_for_unregistered_provider():
    registry = ApplicationAdapterRegistry()

    assert (
        registry.has_adapter(
            ATSProvider.LEVER
        )
        is False
    )


def test_has_adapter_false_for_unknown():
    registry = ApplicationAdapterRegistry()

    assert (
        registry.has_adapter(
            ATSProvider.UNKNOWN
        )
        is False
    )


def test_registration_is_provider_specific():
    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE:
                greenhouse_factory,
        }
    )

    assert (
        registry.has_adapter(
            ATSProvider.GREENHOUSE
        )
        is True
    )

    assert (
        registry.has_adapter(
            ATSProvider.LEVER
        )
        is False
    )

    with pytest.raises(
        AdapterNotAvailableError
    ):
        registry.create(
            ATSProvider.LEVER,
            "https://jobs.lever.co/example/123",
        )