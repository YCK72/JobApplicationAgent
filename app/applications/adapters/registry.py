from __future__ import annotations

from collections.abc import Mapping

from app.applications.adapters.base import (
    ApplicationFormAdapter,
)
from app.applications.adapters.detector import (
    ATSProvider,
)


class AdapterNotAvailableError(LookupError):
    """
    Raised when no explicitly registered adapter exists for an ATS.
    """


class ApplicationAdapterRegistry:
    """
    Deterministic registry of ATS providers to form adapters.

    Registration must be explicit. Unknown or unsupported providers
    never fall back to another adapter.
    """

    def __init__(
        self,
        adapters: Mapping[
            ATSProvider,
            ApplicationFormAdapter,
        ]
        | None = None,
    ) -> None:
        self._adapters: dict[
            ATSProvider,
            ApplicationFormAdapter,
        ] = {}

        if adapters:
            for provider, adapter in adapters.items():
                self.register(
                    provider=provider,
                    adapter=adapter,
                )

    def register(
        self,
        provider: ATSProvider,
        adapter: ApplicationFormAdapter,
    ) -> None:
        """
        Explicitly register one adapter for one known provider.
        """

        if not isinstance(provider, ATSProvider):
            raise TypeError(
                "provider must be an ATSProvider"
            )

        if provider == ATSProvider.UNKNOWN:
            raise ValueError(
                "Cannot register an adapter for UNKNOWN provider."
            )

        if not isinstance(
            adapter,
            ApplicationFormAdapter,
        ):
            raise TypeError(
                "adapter must implement ApplicationFormAdapter"
            )

        self._adapters[provider] = adapter

    def get(
        self,
        provider: ATSProvider,
    ) -> ApplicationFormAdapter:
        """
        Return the explicitly registered adapter.

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

        adapter = self._adapters.get(provider)

        if adapter is None:
            raise AdapterNotAvailableError(
                f"No adapter registered for {provider.value}."
            )

        return adapter

    def has_adapter(
        self,
        provider: ATSProvider,
    ) -> bool:
        """
        Return True only when a known provider has an explicitly
        registered adapter.
        """

        return (
            isinstance(provider, ATSProvider)
            and provider != ATSProvider.UNKNOWN
            and provider in self._adapters
        )