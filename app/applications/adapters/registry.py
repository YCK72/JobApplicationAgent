from __future__ import annotations

from collections.abc import Callable, Mapping

from app.applications.adapters.base import (
    ApplicationFormAdapter,
)
from app.applications.adapters.detector import (
    ATSProvider,
)


AdapterFactory = Callable[
    [str],
    ApplicationFormAdapter,
]


class AdapterNotAvailableError(LookupError):
    """
    Raised when no explicitly registered adapter factory exists
    for an ATS.
    """


class ApplicationAdapterRegistry:
    """
    Deterministic registry of ATS providers to adapter factories.

    Registration must be explicit. Unknown or unsupported providers
    never fall back to another adapter.

    Each factory receives the specific job URL and must return an
    ApplicationFormAdapter configured for that application.
    """

    def __init__(
        self,
        factories: Mapping[
            ATSProvider,
            AdapterFactory,
        ]
        | None = None,
    ) -> None:
        self._factories: dict[
            ATSProvider,
            AdapterFactory,
        ] = {}

        if factories:
            for provider, factory in factories.items():
                self.register(
                    provider=provider,
                    factory=factory,
                )

    def register(
        self,
        provider: ATSProvider,
        factory: AdapterFactory,
    ) -> None:
        """
        Explicitly register one adapter factory for one known provider.
        """
        if not isinstance(provider, ATSProvider):
            raise TypeError(
                "provider must be an ATSProvider"
            )

        if provider == ATSProvider.UNKNOWN:
            raise ValueError(
                "Cannot register an adapter factory for "
                "UNKNOWN provider."
            )

        if not callable(factory):
            raise TypeError(
                "factory must be callable"
            )

        self._factories[provider] = factory

    def create(
        self,
        provider: ATSProvider,
        job_url: str,
    ) -> ApplicationFormAdapter:
        """
        Create the explicitly registered adapter for one job URL.

        Unknown or unregistered providers fail closed.
        """
        if not isinstance(provider, ATSProvider):
            raise AdapterNotAvailableError(
                "Invalid ATS provider."
            )

        if provider == ATSProvider.UNKNOWN:
            raise AdapterNotAvailableError(
                "No adapter is available for UNKNOWN provider."
            )

        factory = self._factories.get(provider)

        if factory is None:
            raise AdapterNotAvailableError(
                f"No adapter registered for {provider.value}."
            )

        adapter = factory(job_url)

        if not isinstance(
            adapter,
            ApplicationFormAdapter,
        ):
            raise TypeError(
                "Adapter factory must return an "
                "ApplicationFormAdapter."
            )

        return adapter

    def has_adapter(
        self,
        provider: ATSProvider,
    ) -> bool:
        """
        Return True only when a known provider has an explicitly
        registered adapter factory.
        """
        return (
            isinstance(provider, ATSProvider)
            and provider != ATSProvider.UNKNOWN
            and provider in self._factories
        )