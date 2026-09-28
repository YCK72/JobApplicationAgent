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
        ).strip().lower()

        role = (
            control.get_attribute("role") or ""
        ).strip().lower()

        autocomplete = (
            control.get_attribute("autocomplete") or ""
        ).strip().lower()

        class_name = (
            control.get_attribute("class") or ""
        ).strip()

        if self._should_ignore_control(
            tag_name=tag_name,
            input_type=input_type,
            role=role,
            class_name=class_name,
        ):
            return None

        field_id = self._field_id(
            control=control,
            index=index,
        )

        label = self._field_label(
            control=control,
            field_id=field_id,
            input_type=input_type,
            page=page,
        )

        field_type = self._field_type(
            tag_name=tag_name,
            input_type=input_type,
            role=role,
            autocomplete=autocomplete,
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

        current_checked = self._current_checked(
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
            current_checked=current_checked,
        )

    @staticmethod
    def _should_ignore_control(
        *,
        tag_name: str,
        input_type: str,
        role: str,
        class_name: str,
    ) -> bool:
        """
        Return True for controls that are implementation details rather
        than real application questions.

        Greenhouse uses hidden/action inputs as well as internal helper
        inputs for custom select widgets. The international telephone
        input library also injects its own country-search control.

        These controls must not become ApplicationForm fields.
        """
        if tag_name != "input":
            return False

        ignored_input_types = {
            "hidden",
            "submit",
            "button",
            "reset",
            "image",
        }

        if input_type in ignored_input_types:
            return True

        classes = set(class_name.split())

        # Greenhouse custom select widgets inject a separate required
        # helper input with a generated CSS prefix, for example:
        #
        # remix-css-1a0ro4n-requiredInput
        #
        # The generated prefix may change, so match the stable suffix
        # rather than one exact class name.
        if any(
            class_token.endswith("-requiredInput")
            for class_token in classes
        ):
            return True

        # intl-tel-input injects an internal searchable country picker.
        # It is part of the phone widget, not a separate application
        # question.
        if "iti__search-input" in classes:
            return True

        return False

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
        input_type: str,
        page: Page,
    ) -> str:
        """
        Resolve a human-readable field label without interacting with
        the control.

        Greenhouse file inputs may use generic action labels such as
        "Attach" instead of describing the semantic application field.
        For those file inputs, generic action labels are skipped so the
        semantic name or field identifier can be used instead.

        Resolution order:

        1. Meaningful native <label for="..."> association.
        2. Elements referenced by aria-labelledby.
        3. aria-label.
        4. placeholder.
        5. name.
        6. Normalized field identifier.
        """
        control_id = control.get_attribute("id")

        if control_id:
            label = page.locator(
                f'label[for="{cls._css_escape(control_id)}"]'
            )

            if label.count() > 0:
                text = cls._clean_text(
                    label.first.inner_text()
                )

                if (
                    text
                    and not cls._is_generic_file_label(
                        text=text,
                        input_type=input_type,
                    )
                ):
                    return text

        aria_labelledby = control.get_attribute(
            "aria-labelledby"
        )

        if aria_labelledby and aria_labelledby.strip():
            referenced_texts: list[str] = []

            for referenced_id in aria_labelledby.split():
                referenced_label = page.locator(
                    f"#{cls._css_escape(referenced_id)}"
                )

                if referenced_label.count() == 0:
                    continue

                text = cls._clean_text(
                    referenced_label.first.inner_text()
                )

                if text:
                    referenced_texts.append(text)

            if referenced_texts:
                text = cls._clean_text(
                    " ".join(referenced_texts)
                )

                if not cls._is_generic_file_label(
                    text=text,
                    input_type=input_type,
                ):
                    return text

        aria_label = control.get_attribute("aria-label")

        if aria_label and aria_label.strip():
            text = cls._clean_text(aria_label)

            if not cls._is_generic_file_label(
                text=text,
                input_type=input_type,
            ):
                return text

        placeholder = control.get_attribute("placeholder")

        if placeholder and placeholder.strip():
            return cls._clean_text(placeholder)

        name = control.get_attribute("name")

        if name and name.strip():
            return cls._humanize_identifier(name)

        return cls._humanize_identifier(field_id)

    @staticmethod
    def _is_generic_file_label(
        *,
        text: str,
        input_type: str,
    ) -> bool:
        """
        Return True when a file input label describes an upload action
        rather than the semantic application field.
        """
        if input_type != "file":
            return False

        normalized = " ".join(
            text.strip().lower().split()
        )

        generic_labels = {
            "attach",
            "upload",
            "choose file",
            "browse",
        }

        return normalized in generic_labels

    @staticmethod
    def _field_type(
        *,
        tag_name: str,
        input_type: str,
        role: str = "",
        autocomplete: str = "",
    ) -> FormFieldType:
        """
        Normalize the browser control into an ATS-independent field type.

        Greenhouse frequently implements dropdowns as text inputs with
        role="combobox", so semantic accessibility metadata takes
        precedence over the raw HTML input type.

        Greenhouse also currently renders its email control as
        type="text" while exposing autocomplete="email".
        """
        if tag_name == "textarea":
            return FormFieldType.TEXTAREA

        if tag_name == "select":
            return FormFieldType.SELECT

        if tag_name != "input":
            return FormFieldType.UNKNOWN

        if role == "combobox":
            return FormFieldType.SELECT

        if autocomplete == "email":
            return FormFieldType.EMAIL

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
        """
        Read options from native HTML select controls.

        Custom Greenhouse combobox options are intentionally not opened
        or clicked here. Until their DOM structure is inspected and
        tested independently, those controls normalize as SELECT with an
        empty options list.
        """
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
    def _current_checked(
            *,
            control: Locator,
            field_type: FormFieldType,
    ) -> bool | None:
        """
        Read the observed checked state of a native CHECKBOX control.

        Checked state is represented separately from current_value because an
        HTML checkbox's value attribute does not indicate whether the control
        is currently checked.

        This method only inspects browser state. It does not mutate the control
        or authorize checkbox execution.
        """
        if field_type != FormFieldType.CHECKBOX:
            return None

        return control.is_checked()

    @staticmethod
    def _clean_text(value: str) -> str:
        """
        Normalize human-readable Greenhouse text.

        Greenhouse commonly appends a visual "*" to required field labels.
        Requiredness is represented separately by FormField.required, so the
        decorative marker must not remain part of the semantic field label.

        Only trailing asterisks are removed. Asterisks elsewhere in the text
        are preserved.
        """
        cleaned = " ".join(value.split())

        while cleaned.endswith("*"):
            cleaned = cleaned[:-1].rstrip()

        return cleaned
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