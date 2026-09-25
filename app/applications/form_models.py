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


class FormField(BaseModel):
    """
    ATS-independent representation of one application field.

    This model describes a field only. It does not authorize
    filling, clicking, or submitting anything.
    """

    field_id: str = Field(min_length=1)
    label: str = Field(min_length=1)

    field_type: FormFieldType = FormFieldType.UNKNOWN

    required: bool = False

    options: list[str] = Field(
        default_factory=list
    )

    current_value: Optional[str] = None


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