from __future__ import annotations

from abc import ABC, abstractmethod

from app.applications.form_models import ApplicationForm


class ApplicationFormAdapter(ABC):
    """
    Base contract for ATS-specific application-form adapters.

    Adapters normalize provider-specific form structures into an
    ApplicationForm.

    They do not resolve answers, fill fields, upload files, click
    controls, bypass human verification, or submit applications.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable ATS/provider name."""

        raise NotImplementedError

    @abstractmethod
    def inspect(self) -> ApplicationForm:
        """
        Inspect the provider-specific form and return its normalized
        representation.

        Concrete browser-backed implementations will be introduced
        later.
        """

        raise NotImplementedError