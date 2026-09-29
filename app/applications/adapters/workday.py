from __future__ import annotations

from playwright.sync_api import Locator, Page

from app.applications.adapters.greenhouse import GreenhouseFormAdapter
from app.applications.form_models import (
    FormControlKind,
    FormField,
    FormFieldOption,
    FormFieldType,
)


class WorkdayFormAdapter(GreenhouseFormAdapter):
    """Read-only inspector for one visible Workday application step.

    Workday applications span several pages whose later questions are not
    visible until earlier pages are completed. The adapter therefore records
    the current page and always appends an UNKNOWN review boundary. This keeps
    deterministic planning from authorizing execution from a partial form.
    """

    @property
    def provider_name(self) -> str:
        return "WORKDAY"

    def _inspect_fields(self, page: Page) -> list[FormField]:
        controls = page.locator(
            "input, textarea, select, button[id][name]"
        )
        fields: list[FormField] = []
        processed_radio_names: set[str] = set()

        for index in range(controls.count()):
            control = controls.nth(index)
            tag_name = control.evaluate(
                "(element) => element.tagName.toLowerCase()"
            )
            input_type = (control.get_attribute("type") or "").strip().lower()

            if tag_name == "input" and input_type == "radio":
                radio_name = (control.get_attribute("name") or "").strip()
                if radio_name:
                    if radio_name in processed_radio_names:
                        continue
                    field = self._normalize_radio_group(
                        controls=controls,
                        radio_name=radio_name,
                        page=page,
                    )
                    processed_radio_names.add(radio_name)
                    if field is not None:
                        fields.append(field)
                    continue

            field = self._normalize_control(
                control=control,
                index=index,
                page=page,
            )
            if field is not None:
                fields.append(field)

        if not fields:
            raise ValueError(
                "Workday application page did not expose any application fields."
            )

        fields.append(
            FormField(
                field_id="workday-multi-step-review",
                label="Workday multi-step application requires human review",
                field_type=FormFieldType.UNKNOWN,
                control_kind=FormControlKind.UNKNOWN,
                required=True,
            )
        )
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
        control_id = (control.get_attribute("id") or "").strip()
        control_name = (control.get_attribute("name") or "").strip()
        placeholder = (control.get_attribute("placeholder") or "").strip()
        role = (control.get_attribute("role") or "").strip()

        if (
            tag_name == "input"
            and not control_id
            and not control_name
            and not placeholder
            and not role
        ):
            return None

        if tag_name == "button":
            field_id = self._field_id(control=control, index=index)
            label = self._field_label(
                control=control,
                field_id=field_id,
                input_type="button",
                page=page,
            )
            aria_label = (control.get_attribute("aria-label") or "").strip()
            current_value = self._clean_text(control.inner_text())
            if current_value.lower() in {"", "select one"}:
                current_value = None
            return FormField(
                field_id=field_id,
                label=label,
                field_type=FormFieldType.SELECT,
                control_kind=FormControlKind.CUSTOM_COMBOBOX,
                required=(
                    self._is_required(control)
                    or aria_label.lower().endswith(" required")
                ),
                current_value=current_value,
            )

        field = super()._normalize_control(
            control=control,
            index=index,
            page=page,
        )
        if field is None or field.field_type != FormFieldType.TEXT:
            return field

        identity = f"{control_id} {control_name}".lower()
        if "email" in identity:
            return field.model_copy(update={"field_type": FormFieldType.EMAIL})
        if "phonenumber" in identity or "phone-number" in identity:
            return field.model_copy(update={"field_type": FormFieldType.PHONE})
        return field

    def _normalize_radio_group(
        self,
        *,
        controls: Locator,
        radio_name: str,
        page: Page,
    ) -> FormField | None:
        field = super()._normalize_radio_group(
            controls=controls,
            radio_name=radio_name,
            page=page,
        )
        if field is None:
            return None

        first_radio: Locator | None = None
        for index in range(controls.count()):
            candidate = controls.nth(index)
            if (
                candidate.evaluate("(element) => element.tagName.toLowerCase()")
                == "input"
                and (candidate.get_attribute("type") or "").lower() == "radio"
                and (candidate.get_attribute("name") or "").strip() == radio_name
            ):
                first_radio = candidate
                break

        if first_radio is None:
            return field

        group = first_radio.locator("xpath=ancestor::*[@role='group'][1]")
        if group.count() == 0:
            return field
        labelled_by = (group.first.get_attribute("aria-labelledby") or "").strip()
        if not labelled_by:
            return field

        parts: list[str] = []
        raw_parts: list[str] = []
        for referenced_id in labelled_by.split():
            referenced = page.locator(f"#{self._css_escape(referenced_id)}")
            if referenced.count() == 0:
                continue
            raw = " ".join(referenced.first.inner_text().split())
            if raw:
                raw_parts.append(raw)
                parts.append(self._clean_text(raw))
        label = self._clean_text(" ".join(parts))
        if not label:
            return field
        return field.model_copy(
            update={
                "label": label,
                "required": field.required
                or any(part.endswith(("*", "✱")) for part in raw_parts),
            }
        )

    @staticmethod
    def _field_id(*, control: Locator, index: int) -> str:
        for attribute in ("id", "name"):
            value = control.get_attribute(attribute)
            if value and value.strip():
                return value.strip()
        return f"workday-field-{index}"

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

    @staticmethod
    def _clean_text(value: str) -> str:
        cleaned = " ".join(value.split())
        while cleaned.endswith(("*", "✱")):
            cleaned = cleaned[:-1].rstrip()
        return cleaned
