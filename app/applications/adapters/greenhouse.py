from __future__ import annotations

from collections.abc import Iterable

from playwright.sync_api import Locator, Page

from app.applications.adapters.base import (
    ApplicationFormAdapter,
)
from app.applications.form_models import (
    ApplicationForm,
    FormField,
    FormFieldType,
)
from app.browser import BrowserSession


class GreenhouseFormAdapter(ApplicationFormAdapter):
    """
    Read-only Greenhouse application-form inspector.

    The adapter navigates to one Greenhouse application URL and
    normalizes visible form controls into the ATS-independent
    ApplicationForm model.

    It does not fill fields, click controls, upload files, resolve
    answers, or submit applications.
    """

    def __init__(
        self,
        job_url: str,
        browser_session: BrowserSession,
    ) -> None:
        if not job_url or not job_url.strip():
            raise ValueError("job_url must not be empty.")

        self.job_url = job_url.strip()
        self.browser_session = browser_session

    @property
    def provider_name(self) -> str:
        return "GREENHOUSE"

    def inspect(self) -> ApplicationForm:
        """
        Navigate to the Greenhouse application page, inspect it in
        read-only mode, and always release browser resources.
        """
        try:
            page = self._get_page()

            self.browser_session.navigate(self.job_url)

            fields = self._inspect_fields(page)

            return ApplicationForm(
                provider=self.provider_name,
                job_url=self.job_url,
                fields=fields,
            )

        finally:
            self.browser_session.close()

    def _get_page(self) -> Page:
        """
        Return the active browser page, starting the session when
        necessary.
        """
        if not self.browser_session.is_started:
            return self.browser_session.start()

        return self.browser_session.page

    def _inspect_fields(
        self,
        page: Page,
    ) -> list[FormField]:
        """
        Inspect supported form controls without interacting with them.
        """
        controls = page.locator(
            "input, textarea, select"
        )

        fields: list[FormField] = []

        for index in range(controls.count()):
            control = controls.nth(index)

            field = self._normalize_control(
                control=control,
                index=index,
                page=page,
            )

            if field is not None:
                fields.append(field)

        return fields

    def _normalize_control(
        self,
        *,
        control: Locator,
        index: int,
        page: Page,
    ) -> FormField | None:
        tag_name = control.evaluate(
            "(element) => element.tagName.toLowerCase()"
        )

        input_type = (
            control.get_attribute("type") or ""
        ).lower()

        if self._should_ignore_control(
            tag_name=tag_name,
            input_type=input_type,
        ):
            return None

        field_id = self._field_id(
            control=control,
            index=index,
        )

        label = self._field_label(
            control=control,
            field_id=field_id,
            page=page,
        )

        field_type = self._field_type(
            tag_name=tag_name,
            input_type=input_type,
        )

        required = self._is_required(control)

        options = self._options(
            control=control,
            field_type=field_type,
        )

        current_value = self._current_value(
            control=control,
            field_type=field_type,
        )

        return FormField(
            field_id=field_id,
            label=label,
            field_type=field_type,
            required=required,
            options=options,
            current_value=current_value,
        )

    @staticmethod
    def _should_ignore_control(
        *,
        tag_name: str,
        input_type: str,
    ) -> bool:
        if tag_name != "input":
            return False

        return input_type in {
            "hidden",
            "submit",
            "button",
            "reset",
            "image",
        }

    @staticmethod
    def _field_id(
        *,
        control: Locator,
        index: int,
    ) -> str:
        for attribute in ("id", "name"):
            value = control.get_attribute(attribute)

            if value and value.strip():
                return value.strip()

        return f"greenhouse-field-{index}"

    @classmethod
    def _field_label(
        cls,
        *,
        control: Locator,
        field_id: str,
        page: Page,
    ) -> str:
        control_id = control.get_attribute("id")

        if control_id:
            label = page.locator(
                f'label[for="{cls._css_escape(control_id)}"]'
            )

            if label.count() > 0:
                text = cls._clean_text(
                    label.first.inner_text()
                )

                if text:
                    return text

        aria_label = control.get_attribute("aria-label")

        if aria_label and aria_label.strip():
            return cls._clean_text(aria_label)

        placeholder = control.get_attribute("placeholder")

        if placeholder and placeholder.strip():
            return cls._clean_text(placeholder)

        name = control.get_attribute("name")

        if name and name.strip():
            return cls._humanize_identifier(name)

        return cls._humanize_identifier(field_id)

    @staticmethod
    def _field_type(
        *,
        tag_name: str,
        input_type: str,
    ) -> FormFieldType:
        if tag_name == "textarea":
            return FormFieldType.TEXTAREA

        if tag_name == "select":
            return FormFieldType.SELECT

        if tag_name != "input":
            return FormFieldType.UNKNOWN

        mapping = {
            "": FormFieldType.TEXT,
            "text": FormFieldType.TEXT,
            "email": FormFieldType.EMAIL,
            "tel": FormFieldType.PHONE,
            "file": FormFieldType.FILE,
            "radio": FormFieldType.RADIO,
            "checkbox": FormFieldType.CHECKBOX,
        }

        return mapping.get(
            input_type,
            FormFieldType.UNKNOWN,
        )

    @staticmethod
    def _is_required(
        control: Locator,
    ) -> bool:
        required = control.get_attribute("required")

        aria_required = (
            control.get_attribute("aria-required") or ""
        ).lower()

        return (
            required is not None
            or aria_required == "true"
        )

    @classmethod
    def _options(
        cls,
        *,
        control: Locator,
        field_type: FormFieldType,
    ) -> list[str]:
        if field_type != FormFieldType.SELECT:
            return []

        option_locators = control.locator("option")

        values: list[str] = []

        for index in range(option_locators.count()):
            option = option_locators.nth(index)

            text = cls._clean_text(
                option.inner_text()
            )

            if text:
                values.append(text)

        return cls._deduplicate(values)

    @staticmethod
    def _current_value(
        *,
        control: Locator,
        field_type: FormFieldType,
    ) -> str | None:
        if field_type == FormFieldType.FILE:
            return None

        value = control.input_value()

        if not value:
            return None

        return value

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split())

    @classmethod
    def _humanize_identifier(
        cls,
        value: str,
    ) -> str:
        cleaned = (
            value.replace("[", " ")
            .replace("]", " ")
            .replace("_", " ")
            .replace("-", " ")
            .replace(".", " ")
        )

        cleaned = cls._clean_text(cleaned)

        return cleaned or "Unknown field"

    @staticmethod
    def _deduplicate(
        values: Iterable[str],
    ) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)

        return result

    @staticmethod
    def _css_escape(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
        )