from __future__ import annotations

from playwright.sync_api import Locator, Page

from app.applications.adapters.greenhouse import GreenhouseFormAdapter
from app.applications.form_models import (
    ApplicationForm,
    FormControlKind,
    FormField,
    FormFieldOption,
    FormFieldType,
)


class AshbyFormAdapter(GreenhouseFormAdapter):
    """Read-only Ashby application-form inspector.

    Ashby renders ordinary questions with native controls while location and
    some choice widgets use custom controls. Native controls share the proven
    normalization used by the existing adapters. Ashby-specific field-entry
    labels, URL inputs, required markers, and implementation-only controls are
    handled here.

    Custom comboboxes are preserved without opening them or inventing options,
    which forces deterministic planning to require review. Inspection never
    fills, clicks, uploads, bypasses verification, or submits a form.
    """

    _FIELD_ENTRY_LABEL = (
        "xpath=ancestor::*[contains(concat(' ', "
        "normalize-space(@class), ' '), "
        "' ashby-application-form-field-entry ')][1]/label[1]"
    )
    _AUTOFILL_ROOT = (
        "xpath=ancestor::*[contains(concat(' ', "
        "normalize-space(@class), ' '), "
        "' ashby-application-form-autofill-input-root ')][1]"
    )

    @property
    def provider_name(self) -> str:
        return "ASHBY"

    def inspect(self) -> ApplicationForm:
        form = super().inspect()
        if not form.fields:
            raise ValueError(
                "Ashby application page did not expose any application fields."
            )
        return form

    def _normalize_control(
        self,
        *,
        control: Locator,
        index: int,
        page: Page,
    ) -> FormField | None:
        if control.locator(self._AUTOFILL_ROOT).count() > 0:
            return None
        return super()._normalize_control(
            control=control,
            index=index,
            page=page,
        )

    def _inspect_fields(self, page: Page) -> list[FormField]:
        fields = super()._inspect_fields(page)
        rendered_entries = page.locator(
            ".ashby-application-form-field-entry"
        ).count()
        if len(fields) < rendered_entries:
            raise ValueError(
                "Ashby application form contains unsupported application "
                "controls that cannot be represented safely."
            )
        return fields

    @staticmethod
    def _field_id(*, control: Locator, index: int) -> str:
        for attribute in ("id", "name"):
            value = control.get_attribute(attribute)
            if value and value.strip():
                return value.strip()
        return f"ashby-field-{index}"

    @classmethod
    def _field_label(
        cls,
        *,
        control: Locator,
        field_id: str,
        input_type: str,
        page: Page,
    ) -> str:
        identifiers = []
        for attribute in ("id", "name"):
            value = control.get_attribute(attribute)
            if value and value.strip() and value.strip() not in identifiers:
                identifiers.append(value.strip())

        for identifier in identifiers:
            label = page.locator(
                f'label[for="{cls._css_escape(identifier)}"]'
            )
            text = cls._first_locator_text(label)
            if text and not cls._is_generic_file_label(
                text=text,
                input_type=input_type,
            ):
                return text

        aria_labelledby = control.get_attribute("aria-labelledby")
        if aria_labelledby and aria_labelledby.strip():
            referenced_texts = []
            for referenced_id in aria_labelledby.split():
                referenced = page.locator(
                    f"#{cls._css_escape(referenced_id)}"
                )
                text = cls._first_locator_text(referenced)
                if text:
                    referenced_texts.append(text)
            if referenced_texts:
                text = cls._clean_text(" ".join(referenced_texts))
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

        text = cls._first_locator_text(
            control.locator(cls._FIELD_ENTRY_LABEL)
        )
        if text and not cls._is_generic_file_label(
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

    @classmethod
    def _is_required(cls, control: Locator) -> bool:
        if GreenhouseFormAdapter._is_required(control):
            return True

        label = control.locator(cls._FIELD_ENTRY_LABEL)
        if label.count() == 0:
            return False

        class_name = label.first.get_attribute("class") or ""
        return any(
            token.startswith("_required_")
            for token in class_name.split()
        )

    @staticmethod
    def _should_ignore_control(
        *,
        tag_name: str,
        input_type: str,
        role: str,
        class_name: str,
    ) -> bool:
        if "g-recaptcha-response" in class_name.split():
            return True
        return GreenhouseFormAdapter._should_ignore_control(
            tag_name=tag_name,
            input_type=input_type,
            role=role,
            class_name=class_name,
        )

    @staticmethod
    def _field_type(
        *,
        tag_name: str,
        input_type: str,
        role: str = "",
        autocomplete: str = "",
    ) -> FormFieldType:
        if tag_name == "input" and input_type == "url":
            return FormFieldType.TEXT
        return GreenhouseFormAdapter._field_type(
            tag_name=tag_name,
            input_type=input_type,
            role=role,
            autocomplete=autocomplete,
        )

    @staticmethod
    def _current_value(
        *,
        control: Locator,
        field_type: FormFieldType,
        control_kind: FormControlKind,
        option_details: list[FormFieldOption],
    ) -> str | None:
        if field_type == FormFieldType.CHECKBOX:
            return None
        return GreenhouseFormAdapter._current_value(
            control=control,
            field_type=field_type,
            control_kind=control_kind,
            option_details=option_details,
        )

    @classmethod
    def _first_locator_text(cls, locator: Locator) -> str | None:
        if locator.count() == 0:
            return None
        text = cls._clean_text(locator.first.inner_text())
        return text or None

    @staticmethod
    def _clean_text(value: str) -> str:
        cleaned = " ".join(value.split())
        while cleaned.endswith(("*", "✱")):
            cleaned = cleaned[:-1].rstrip()
        return cleaned
