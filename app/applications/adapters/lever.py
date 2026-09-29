from __future__ import annotations

from playwright.sync_api import Locator, Page

from app.applications.adapters.greenhouse import GreenhouseFormAdapter


class LeverFormAdapter(GreenhouseFormAdapter):
    """Read-only Lever application-form inspector.

    Lever and Greenhouse both expose their application questions through
    native inputs, textareas, selects, radios, checkboxes, and file inputs.
    This adapter reuses the already validated native-control normalization
    while specializing provider identity, generated field IDs, and Lever's
    unassociated question-container labels.

    Inspection never fills, clicks, uploads, bypasses verification, or
    submits a form. The browser session is always closed after inspection.
    """

    @property
    def provider_name(self) -> str:
        return "LEVER"

    @staticmethod
    def _field_id(*, control: Locator, index: int) -> str:
        for attribute in ("id", "name"):
            value = control.get_attribute(attribute)
            if value and value.strip():
                return value.strip()
        return f"lever-field-{index}"

    @classmethod
    def _field_label(
        cls,
        *,
        control: Locator,
        field_id: str,
        input_type: str,
        page: Page,
    ) -> str:
        """Resolve Lever labels without interacting with the form.

        Lever commonly renders a question label beside its control without a
        ``for`` attribute. Native associations and ARIA metadata remain the
        first choices. A wrapping label or the nearest application-question
        label is then used before generic placeholder/name fallbacks.
        """
        control_id = control.get_attribute("id")
        if control_id:
            label = page.locator(
                f'label[for="{cls._css_escape(control_id)}"]'
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

        wrapping_label = control.locator("xpath=ancestor::label[1]")
        text = cls._first_locator_text(wrapping_label)
        if text and not cls._is_generic_file_label(
            text=text,
            input_type=input_type,
        ):
            return text

        question_label = control.locator(
            "xpath=ancestor::*[contains(concat(' ', "
            "normalize-space(@class), ' '), "
            "' application-question ')][1]/label[1]"
        )
        text = cls._first_locator_text(question_label)
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
