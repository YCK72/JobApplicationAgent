from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FormFieldType(str, Enum):
    TEXT = "TEXT"
    TEXTAREA = "TEXTAREA"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SELECT = "SELECT"
    RADIO = "RADIO"
    CHECKBOX = "CHECKBOX"
    FILE = "FILE"
    UNKNOWN = "UNKNOWN"


class FormFieldOption(BaseModel):
    """
    One inspected selectable option.

    label is the human-visible semantic option used by deterministic
    planning.

    value is the exact provider/browser value observed during inspection.
    It is execution metadata only and does not independently authorize
    browser mutation or submission.
    """

    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class FormField(BaseModel):
    """
    ATS-independent representation of one application field.

    options preserves the human-visible semantic option labels used by
    deterministic answer resolution and planning.

    option_details may additionally preserve the exact provider/browser
    value associated with each inspected option. This allows execution
    layers to distinguish a semantic answer such as "Remote" from a DOM
    value such as "internal-option-101".

    This model describes a field only. It does not authorize filling,
    clicking, selecting, or submitting anything.
    """

    field_id: str = Field(min_length=1)
    label: str = Field(min_length=1)

    field_type: FormFieldType = FormFieldType.UNKNOWN

    required: bool = False

    options: list[str] = Field(
        default_factory=list
    )

    option_details: list[FormFieldOption] = Field(
        default_factory=list
    )

    current_value: Optional[str] = None

    current_checked: Optional[bool] = None


class ApplicationForm(BaseModel):
    """
    Normalized representation of an inspected application form.

    Future ATS adapters will convert provider-specific forms into
    this model before any answer-resolution logic runs.
    """

    provider: str = Field(min_length=1)
    job_url: str = Field(min_length=1)

    fields: list[FormField] = Field(
        default_factory=list
    )