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
    @property
    def provider_name(self) -> str:
        return "Greenhouse"

    def inspect(self) -> ApplicationForm:
        return ApplicationForm(
            provider=self.provider_name,
            job_url="https://boards.greenhouse.io/example/jobs/123",
        )


class FakeLeverAdapter(
    ApplicationFormAdapter
):
    @property
    def provider_name(self) -> str:
        return "Lever"

    def inspect(self) -> ApplicationForm:
        return ApplicationForm(
            provider=self.provider_name,
            job_url="https://jobs.lever.co/example/123",
        )


def test_registered_adapter_can_be_retrieved():
    adapter = FakeGreenhouseAdapter()

    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE: adapter,
        }
    )

    result = registry.get(
        ATSProvider.GREENHOUSE
    )

    assert result is adapter


def test_multiple_adapters_can_be_registered():
    greenhouse = FakeGreenhouseAdapter()
    lever = FakeLeverAdapter()

    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE: greenhouse,
            ATSProvider.LEVER: lever,
        }
    )

    assert (
        registry.get(ATSProvider.GREENHOUSE)
        is greenhouse
    )

    assert (
        registry.get(ATSProvider.LEVER)
        is lever
    )


def test_unregistered_known_provider_fails_closed():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(
        AdapterNotAvailableError
    ):
        registry.get(
            ATSProvider.GREENHOUSE
        )


def test_unknown_provider_fails_closed():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(
        AdapterNotAvailableError
    ):
        registry.get(
            ATSProvider.UNKNOWN
        )


def test_invalid_provider_fails_closed():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(
        AdapterNotAvailableError
    ):
        registry.get("GREENHOUSE")


def test_unknown_provider_cannot_be_registered():
    registry = ApplicationAdapterRegistry()
    adapter = FakeGreenhouseAdapter()

    with pytest.raises(ValueError):
        registry.register(
            ATSProvider.UNKNOWN,
            adapter,
        )


def test_invalid_provider_cannot_be_registered():
    registry = ApplicationAdapterRegistry()
    adapter = FakeGreenhouseAdapter()

    with pytest.raises(TypeError):
        registry.register(
            "GREENHOUSE",
            adapter,
        )


def test_invalid_adapter_cannot_be_registered():
    registry = ApplicationAdapterRegistry()

    with pytest.raises(TypeError):
        registry.register(
            ATSProvider.GREENHOUSE,
            object(),
        )


def test_has_adapter_true_for_registered_provider():
    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE:
                FakeGreenhouseAdapter(),
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
    greenhouse = FakeGreenhouseAdapter()

    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE: greenhouse,
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
        registry.get(
            ATSProvider.LEVER
        )