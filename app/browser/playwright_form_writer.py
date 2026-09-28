from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from app.applications.form_models import (
    FormField,
    FormFieldOption,
    FormFieldType,
    FormControlKind,
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
    - native SELECT mutation using an exact verified option label,
    - native RADIO mutation using an exact verified option value,
    - one authorized local PDF attachment on a native file input.

    SELECT execution fails closed unless the resolved browser control is
    still an actual native HTML SELECT element at mutation time.

    RADIO execution fails closed unless the resolved browser control is
    still an actual native HTML INPUT element with type=radio at mutation
    time.

    FILE execution fails closed unless the resolved browser control is
    still an actual native HTML INPUT element with type=file at mutation
    time.

    It exposes no navigation, arbitrary clicking, keyboard interaction,
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
        Select one exact inspected option from a native HTML SELECT.

        The requested value is the human-visible semantic option label
        already resolved by deterministic planning.

        Execution requires an exact and unique mapping from that semantic
        label to the provider/browser value captured during inspection.

        Custom comboboxes are explicitly rejected. Missing, ambiguous, or
        stale mappings fail closed rather than falling back to label-based
        browser inference.
        """
        if field.field_type != FormFieldType.SELECT:
            raise PlaywrightFieldWriterError(
                "Field type is not supported for option selection."
            )

        if field.control_kind == FormControlKind.CUSTOM_COMBOBOX:
            raise PlaywrightFieldWriterError(
                "CUSTOM_COMBOBOX cannot use native SELECT execution."
            )

        self._validate_string_value(value)

        if not field.options:
            raise PlaywrightFieldWriterError(
                "SELECT field has no inspected options."
            )

        semantic_matches = [
            option
            for option in field.options
            if option == value
        ]

        if len(semantic_matches) != 1:
            raise PlaywrightFieldWriterError(
                "SELECT value does not identify exactly one inspected option."
            )

        native_matches = [
            option
            for option in field.option_details
            if option.label == value
        ]

        if len(native_matches) != 1:
            raise PlaywrightFieldWriterError(
                "SELECT option must have exactly one inspected "
                "native-value mapping."
            )

        native_value = native_matches[0].value

        self._validate_string_value(native_value)

        locator = self._resolve_locator(field)

        self._validate_native_select(locator)

        option_locator = locator.locator(
            f'option[value="{self._css_escape(native_value)}"]'
        )

        if option_locator.count() != 1:
            raise PlaywrightFieldWriterError(
                "SELECT native value did not resolve to exactly one option."
            )

        locator.select_option(
            value=native_value
        )

    def select_radio_option(
            self,
            field: FormField,
            value: str,
    ) -> None:
        """
        Select one exact inspected semantic option from a native RADIO group.

        value is the human-visible semantic option already resolved by
        deterministic planning.

        The corresponding native DOM value must have been independently
        preserved during inspection in field.option_details. Execution fails
        closed if that mapping is missing or ambiguous.

        No fuzzy matching, aliases, DOM-side inference, or browser-side
        guessing are permitted.
        """
        if field.field_type != FormFieldType.RADIO:
            raise PlaywrightFieldWriterError(
                "Field type is not supported for radio selection."
            )

        self._validate_string_value(value)

        if not field.options:
            raise PlaywrightFieldWriterError(
                "RADIO field has no inspected options."
            )

        matches = [
            option
            for option in field.options
            if option == value
        ]

        if len(matches) != 1:
            raise PlaywrightFieldWriterError(
                "RADIO value does not identify exactly one inspected option."
            )

        native_matches = [
            option
            for option in field.option_details
            if option.label == value
        ]

        if not native_matches:
            raise PlaywrightFieldWriterError(
                "RADIO option has no inspected native value mapping."
            )

        if len(native_matches) != 1:
            raise PlaywrightFieldWriterError(
                "RADIO option does not identify exactly one native value."
            )

        native_value = native_matches[0].value

        self._validate_string_value(native_value)

        group_locator = self._resolve_radio_group(field)

        if group_locator.count() < 1:
            raise PlaywrightFieldWriterError(
                "Field identifier did not resolve to a radio group."
            )

        field_id = field.field_id.strip()

        option_locator = self._page.locator(
            (
                f'[name="{self._css_escape(field_id)}"]'
                f'[value="{self._css_escape(native_value)}"]'
            )
        )

        if option_locator.count() != 1:
            raise PlaywrightFieldWriterError(
                "RADIO native value did not resolve to exactly one "
                "browser control."
            )

        self._validate_native_radio_input(
            option_locator
        )

        option_locator.check()

    def set_checkbox_state(
        self,
        field: FormField,
        checked: bool,
    ) -> None:
        """
        Set one authorized native CHECKBOX to an exact boolean state.

        The desired state must already have been explicitly authorized
        upstream. This method does not infer intent and never blindly
        toggles a checkbox.

        The resolved browser control is revalidated immediately before
        mutation and must still be an actual native
        HTML INPUT[type=checkbox].
        """
        if field.field_type != FormFieldType.CHECKBOX:
            raise PlaywrightFieldWriterError(
                "Field type is not supported for checkbox mutation."
            )

        if not isinstance(checked, bool):
            raise PlaywrightFieldWriterError(
                "CHECKBOX desired state must be a boolean."
            )

        locator = self._resolve_locator(field)

        if locator.count() != 1:
            raise PlaywrightFieldWriterError(
                "Field identifier did not resolve to exactly one control."
            )

        self._validate_native_checkbox_input(locator)

        try:
            current_checked = locator.is_checked()
        except Exception as exc:
            raise PlaywrightFieldWriterError(
                "CHECKBOX state could not be safely verified."
            ) from exc

        if not isinstance(current_checked, bool):
            raise PlaywrightFieldWriterError(
                "CHECKBOX state could not be safely verified."
            )

        if current_checked == checked:
            return

        if checked:
            locator.check()
            return

        locator.uncheck()

    def upload_file(
        self,
        field: FormField,
        file_path: str,
    ) -> None:
        """
        Attach one exact local PDF to a native INPUT[type=file] control.

        The exact path must already have been selected and authorized by an
        upstream deterministic layer. This method does not search for,
        choose, substitute, or infer a resume.

        The local path and the resolved DOM control are both revalidated
        immediately before mutation.
        """
        if field.field_type != FormFieldType.FILE:
            raise PlaywrightFieldWriterError(
                "Field type is not supported for file upload."
            )

        self._validate_string_value(file_path)

        path = Path(file_path).expanduser()

        try:
            resolved_path = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise PlaywrightFieldWriterError(
                "Upload file could not be safely resolved."
            ) from exc

        if not resolved_path.is_file():
            raise PlaywrightFieldWriterError(
                "Upload path does not identify a regular file."
            )

        if resolved_path.suffix.casefold() != ".pdf":
            raise PlaywrightFieldWriterError(
                "Only PDF files are supported for controlled upload."
            )

        locator = self._resolve_locator(field)

        if locator.count() != 1:
            raise PlaywrightFieldWriterError(
                "Field identifier did not resolve to exactly one control."
            )

        self._validate_native_file_input(locator)

        locator.set_input_files(str(resolved_path))

    @staticmethod
    def _validate_native_select(
        locator,
    ) -> None:
        """
        Require the resolved browser control to be a native HTML SELECT.

        FormFieldType.SELECT is an ATS-independent semantic type and may also
        represent custom combobox widgets. Browser mutation is therefore
        permitted only after checking the actual DOM element at execution
        time.
        """
        try:
            tag_name = locator.evaluate(
                "element => element.tagName"
            )
        except Exception as exc:
            raise PlaywrightFieldWriterError(
                "SELECT control type could not be safely verified."
            ) from exc

        if not isinstance(tag_name, str):
            raise PlaywrightFieldWriterError(
                "SELECT control type could not be safely verified."
            )

        if tag_name.strip().casefold() != "select":
            raise PlaywrightFieldWriterError(
                "Resolved SELECT field is not a native HTML select control."
            )

    @staticmethod
    def _validate_native_file_input(
        locator,
    ) -> None:
        """
        Require the resolved browser control to be INPUT[type=file].
        """
        try:
            control = locator.evaluate(
                """element => ({
                    tagName: element.tagName,
                    type: element.type
                })"""
            )
        except Exception as exc:
            raise PlaywrightFieldWriterError(
                "FILE control type could not be safely verified."
            ) from exc

        if not isinstance(control, dict):
            raise PlaywrightFieldWriterError(
                "FILE control type could not be safely verified."
            )

        tag_name = control.get("tagName")
        input_type = control.get("type")

        if not isinstance(tag_name, str) or not isinstance(input_type, str):
            raise PlaywrightFieldWriterError(
                "FILE control type could not be safely verified."
            )

        if (
            tag_name.strip().casefold() != "input"
            or input_type.strip().casefold() != "file"
        ):
            raise PlaywrightFieldWriterError(
                "Resolved FILE field is not a native HTML file input."
            )

    @staticmethod
    def _validate_native_checkbox_input(
        locator,
    ) -> None:
        """
        Require the resolved browser control to be INPUT[type=checkbox].
        """
        try:
            control = locator.evaluate(
                """element => ({
                    tagName: element.tagName,
                    type: element.type
                })"""
            )
        except Exception as exc:
            raise PlaywrightFieldWriterError(
                "CHECKBOX control type could not be safely verified."
            ) from exc

        if not isinstance(control, dict):
            raise PlaywrightFieldWriterError(
                "CHECKBOX control type could not be safely verified."
            )

        tag_name = control.get("tagName")
        input_type = control.get("type")

        if not isinstance(tag_name, str) or not isinstance(
            input_type,
            str,
        ):
            raise PlaywrightFieldWriterError(
                "CHECKBOX control type could not be safely verified."
            )

        if (
            tag_name.strip().casefold() != "input"
            or input_type.strip().casefold() != "checkbox"
        ):
            raise PlaywrightFieldWriterError(
                "Resolved CHECKBOX field is not a native HTML "
                "checkbox input."
            )

    @staticmethod
    def _validate_native_radio_input(
        locator,
    ) -> None:
        """
        Require the resolved browser control to be INPUT[type=radio].
        """
        try:
            control = locator.evaluate(
                """element => ({
                    tagName: element.tagName,
                    type: element.type
                })"""
            )
        except Exception as exc:
            raise PlaywrightFieldWriterError(
                "RADIO control type could not be safely verified."
            ) from exc

        if not isinstance(control, dict):
            raise PlaywrightFieldWriterError(
                "RADIO control type could not be safely verified."
            )

        tag_name = control.get("tagName")
        input_type = control.get("type")

        if not isinstance(tag_name, str) or not isinstance(input_type, str):
            raise PlaywrightFieldWriterError(
                "RADIO control type could not be safely verified."
            )

        if (
            tag_name.strip().casefold() != "input"
            or input_type.strip().casefold() != "radio"
        ):
            raise PlaywrightFieldWriterError(
                "Resolved RADIO field is not a native HTML radio input."
            )

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

    def _resolve_radio_group(
        self,
        field: FormField,
    ):
        """
        Resolve a native RADIO group by its inspected field identifier.

        Unlike ordinary single-control resolution, multiple controls sharing
        the same name are expected for a RADIO group.
        """
        if not isinstance(field.field_id, str):
            raise PlaywrightFieldWriterError(
                "Field identifier must be a string."
            )

        field_id = field.field_id.strip()

        if not field_id:
            raise PlaywrightFieldWriterError(
                "Field identifier must not be empty."
            )

        group_locator = self._page.locator(
            f'[name="{self._css_escape(field_id)}"]'
        )

        if group_locator.count() < 1:
            raise PlaywrightFieldWriterError(
                "Field identifier could not resolve a radio group."
            )

        return group_locator

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
