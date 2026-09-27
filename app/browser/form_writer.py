from __future__ import annotations

from abc import ABC, abstractmethod

from app.applications.form_models import FormField


class BrowserFieldWriter(ABC):
    """
    Abstract boundary for narrowly scoped browser field mutation.

    Implementations may expose the current browser target URL and may
    write only a value to an explicitly identified field.

    This interface does not expose navigation, clicking, file uploads,
    submission, or arbitrary page access.
    """

    @property
    @abstractmethod
    def current_url(self) -> str:
        """
        Return the current browser page URL without mutating browser state.
        """
        raise NotImplementedError

    @abstractmethod
    def write_text(
        self,
        field: FormField,
        value: str,
    ) -> None:
        """
        Write a verified text value to one authorized field.
        """
        raise NotImplementedError