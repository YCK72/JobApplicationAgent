import pytest
from pydantic import ValidationError

from app.applications.form_models import (
    ApplicationForm,
    FormField,
    FormFieldType,
)
from app.applications.form_models import (
    FormControlKind,
    FormField,
    FormFieldOption,
    FormFieldType,
)


def test_create_text_field():
    field = FormField(
        field_id="first_name",
        label="First Name",
        field_type=FormFieldType.TEXT,
        required=True,
    )

    assert field.field_id == "first_name"
    assert field.label == "First Name"
    assert field.field_type == FormFieldType.TEXT
    assert field.required is True
    assert field.options == []
    assert field.current_value is None


def test_current_checked_defaults_to_none():
    field = FormField(
        field_id="first_name",
        label="First Name",
        field_type=FormFieldType.TEXT,
    )

    assert field.current_checked is None


def test_checkbox_preserves_explicit_checked_state():
    unchecked = FormField(
        field_id="remote",
        label="Remote",
        field_type=FormFieldType.CHECKBOX,
        current_checked=False,
    )

    checked = FormField(
        field_id="newsletter",
        label="Newsletter",
        field_type=FormFieldType.CHECKBOX,
        current_checked=True,
    )

    assert unchecked.current_checked is False
    assert checked.current_checked is True


def test_select_field_preserves_options():
    field = FormField(
        field_id="state",
        label="State",
        field_type=FormFieldType.SELECT,
        required=True,
        options=[
            "Washington",
            "California",
            "Texas",
        ],
    )

    assert field.options == [
        "Washington",
        "California",
        "Texas",
    ]


def test_form_contains_normalized_fields():
    form = ApplicationForm(
        provider="Greenhouse",
        job_url="https://example.com/jobs/123",
        fields=[
            FormField(
                field_id="first_name",
                label="First Name",
                field_type=FormFieldType.TEXT,
            ),
            FormField(
                field_id="email",
                label="Email",
                field_type=FormFieldType.EMAIL,
            ),
        ],
    )

    assert form.provider == "Greenhouse"
    assert len(form.fields) == 2

    assert form.fields[0].label == "First Name"
    assert form.fields[1].label == "Email"


def test_form_allows_no_fields():
    form = ApplicationForm(
        provider="Unknown",
        job_url="https://example.com/jobs/123",
    )

    assert form.fields == []


@pytest.mark.parametrize(
    "field_type",
    list(FormFieldType),
)
def test_all_field_types_are_supported(field_type):
    field = FormField(
        field_id="test-field",
        label="Test Field",
        field_type=field_type,
    )

    assert field.field_type == field_type


def test_empty_field_id_is_rejected():
    with pytest.raises(ValidationError):
        FormField(
            field_id="",
            label="First Name",
        )


def test_empty_label_is_rejected():
    with pytest.raises(ValidationError):
        FormField(
            field_id="first_name",
            label="",
        )


def test_empty_provider_is_rejected():
    with pytest.raises(ValidationError):
        ApplicationForm(
            provider="",
            job_url="https://example.com/jobs/123",
        )


def test_empty_job_url_is_rejected():
    with pytest.raises(ValidationError):
        ApplicationForm(
            provider="Greenhouse",
            job_url="",
        )

def test_form_field_supports_radio_option_details() -> None:
    from app.applications.form_models import (
        FormField,
        FormFieldOption,
        FormFieldType,
    )

    field = FormField(
        field_id="work_location",
        label="Work location",
        field_type=FormFieldType.RADIO,
        options=[
            "Remote",
            "Hybrid",
        ],
        option_details=[
            FormFieldOption(
                label="Remote",
                value="101",
            ),
            FormFieldOption(
                label="Hybrid",
                value="102",
            ),
        ],
    )

    assert field.options == [
        "Remote",
        "Hybrid",
    ]

    assert field.option_details == [
        FormFieldOption(
            label="Remote",
            value="101",
        ),
        FormFieldOption(
            label="Hybrid",
            value="102",
        ),
    ]


def test_form_field_option_preserves_distinct_label_and_native_value() -> None:
    from app.applications.form_models import FormFieldOption

    option = FormFieldOption(
        label="Remote",
        value="internal-option-101",
    )

    assert option.label == "Remote"
    assert option.value == "internal-option-101"

def test_form_field_defaults_to_unknown_control_kind() -> None:
    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
    )

    assert field.control_kind == FormControlKind.UNKNOWN


def test_form_field_preserves_inspected_control_kind() -> None:
    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.CUSTOM_COMBOBOX,
    )

    assert (
        field.control_kind
        == FormControlKind.CUSTOM_COMBOBOX
    )