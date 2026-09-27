from __future__ import annotations

from playwright.sync_api import Page

from app.applications.form_models import (
    FormField,
    FormFieldType,
)
from app.browser.form_writer import BrowserFieldWriter


class PlaywrightFieldWriterError(RuntimeError):
    """
    Raised when a field cannot be safely identified or written.
    """


class PlaywrightFieldWriter(BrowserFieldWriter):
    """
    Narrow Playwright implementation for writing authorized text values.

    This writer exposes the current page URL for target verification and
    supports only text-like field mutation.

    It exposes no navigation, clicking, selection, file-upload, keyboard,
    verification-bypass, or submission operations.
    """

    _SUPPORTED_FIELD_TYPES = {
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
    }

    def __init__(
        self,
        page: Page,
    ) -> None:
        self._page = page

    @property
    def current_url(self) -> str:
        """
        Return the current Playwright page URL without changing browser state.
        """
        return self._page.url

    def write_text(
        self,
        field: FormField,
        value: str,
    ) -> None:
        if field.field_type not in self._SUPPORTED_FIELD_TYPES:
            raise PlaywrightFieldWriterError(
                "Field type is not supported for text writing."
            )

        if not isinstance(value, str):
            raise PlaywrightFieldWriterError(
                "Field value must be a string."
            )

        if not field.field_id.strip():
            raise PlaywrightFieldWriterError(
                "Field identifier must not be empty."
            )

        locator = self._resolve_locator(field)

        if locator.count() != 1:
            raise PlaywrightFieldWriterError(
                "Field identifier did not resolve to exactly one control."
            )

        locator.fill(value)

    def _resolve_locator(
        self,
        field: FormField,
    ):
        field_id = field.field_id.strip()

        by_id = self._page.locator(
            f'[id="{self._css_escape(field_id)}"]'
        )

        if by_id.count() == 1:
            return by_id

        if by_id.count() > 1:
            raise PlaywrightFieldWriterError(
                "Field identifier matched multiple controls by id."
            )

        by_name = self._page.locator(
            f'[name="{self._css_escape(field_id)}"]'
        )

        if by_name.count() == 1:
            return by_name

        if by_name.count() > 1:
            raise PlaywrightFieldWriterError(
                "Field identifier matched multiple controls by name."
            )

        raise PlaywrightFieldWriterError(
            "Field identifier could not be resolved."
        )

    @staticmethod
    def _css_escape(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
        )