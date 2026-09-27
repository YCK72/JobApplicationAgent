from __future__ import annotations

from abc import ABC, abstractmethod

from app.applications.form_models import FormField


class BrowserFieldWriter(ABC):
    """
    Abstract boundary for narrowly scoped browser field mutation.

    Implementations may write only a value to an explicitly identified
    field. This interface does not expose navigation, clicking,
    file uploads, submission, or arbitrary page access.
    """

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