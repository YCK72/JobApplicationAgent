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
    Narrow Playwright implementation for authorized field mutation.

    This writer exposes the current page URL for target verification.

    It supports:
    - text-like field filling,
    - native SELECT mutation using an exact verified option label.

    It exposes no navigation, arbitrary clicking, file upload, keyboard,
    verification-bypass, or submission operations.
    """

    _SUPPORTED_TEXT_FIELD_TYPES = {
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
        if field.field_type not in self._SUPPORTED_TEXT_FIELD_TYPES:
            raise PlaywrightFieldWriterError(
                "Field type is not supported for text writing."
            )

        self._validate_string_value(value)

        locator = self._resolve_locator(field)

        if locator.count() != 1:
            raise PlaywrightFieldWriterError(
                "Field identifier did not resolve to exactly one control."
            )

        locator.fill(value)

    def select_option(
        self,
        field: FormField,
        value: str,
    ) -> None:
        """
        Select one exact inspected option on a native SELECT control.

        The requested value must already be the exact option text preserved
        by deterministic form analysis. No fuzzy matching, aliases,
        abbreviations, or browser-side guessing are permitted.
        """
        if field.field_type != FormFieldType.SELECT:
            raise PlaywrightFieldWriterError(
                "Field type is not supported for option selection."
            )

        self._validate_string_value(value)

        if not field.options:
            raise PlaywrightFieldWriterError(
                "SELECT field has no inspected options."
            )

        matches = [
            option
            for option in field.options
            if option == value
        ]

        if len(matches) != 1:
            raise PlaywrightFieldWriterError(
                "SELECT value does not identify exactly one inspected option."
            )

        locator = self._resolve_locator(field)

        if locator.count() != 1:
            raise PlaywrightFieldWriterError(
                "Field identifier did not resolve to exactly one control."
            )

        locator.select_option(label=value)

    @staticmethod
    def _validate_string_value(
        value: str,
    ) -> None:
        if not isinstance(value, str):
            raise PlaywrightFieldWriterError(
                "Field value must be a string."
            )

        if not value.strip():
            raise PlaywrightFieldWriterError(
                "Field value must not be empty."
            )

    def _resolve_locator(
        self,
        field: FormField,
    ):
        if not isinstance(field.field_id, str):
            raise PlaywrightFieldWriterError(
                "Field identifier must be a string."
            )

        field_id = field.field_id.strip()

        if not field_id:
            raise PlaywrightFieldWriterError(
                "Field identifier must not be empty."
            )

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