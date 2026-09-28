from __future__ import annotations

from abc import ABC, abstractmethod

from app.applications.form_models import FormField


class BrowserFieldWriter(ABC):
    """
    Abstract boundary for narrowly scoped browser field mutation.

    Implementations may expose the current browser target URL and may
    mutate only explicitly identified, previously authorized fields.

    This interface does not expose navigation, arbitrary clicking,
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
        Write a verified text value to one authorized text-like field.
        """
        raise NotImplementedError

    @abstractmethod
    def select_option(
        self,
        field: FormField,
        value: str,
    ) -> None:
        """
        Select one verified option on one authorized native SELECT field.

        This method does not authorize the field itself. Authorization must
        already have occurred before this browser-mutation boundary.
        """
        raise NotImplementedError

    @abstractmethod
    def select_radio_option(
        self,
        field: FormField,
        value: str,
    ) -> None:
        """
        Select one exact verified option from one authorized native RADIO group.

        This method does not authorize the field or infer an answer.
        Authorization and exact option resolution must already have occurred
        before this browser-mutation boundary.
        """
        raise NotImplementedError

    @abstractmethod
    def upload_file(
        self,
        field: FormField,
        file_path: str,
    ) -> None:
        """
        Attach one previously authorized local file to one FILE field.

        This method does not select or authorize the file. Upstream policy
        and routing must already have chosen the exact file path before this
        browser-mutation boundary.
        """
        raise NotImplementedError