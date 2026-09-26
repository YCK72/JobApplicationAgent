import pytest

from app.applications.adapters.base import (
    ApplicationFormAdapter,
)
from app.applications.form_models import (
    ApplicationForm,
    FormField,
    FormFieldType,
)


class FakeAdapter(ApplicationFormAdapter):
    @property
    def provider_name(self) -> str:
        return "Fake ATS"

    def inspect(self) -> ApplicationForm:
        return ApplicationForm(
            provider=self.provider_name,
            job_url="https://example.com/jobs/123",
            fields=[
                FormField(
                    field_id="first_name",
                    label="First Name",
                    field_type=FormFieldType.TEXT,
                    required=True,
                ),
                FormField(
                    field_id="email",
                    label="Email",
                    field_type=FormFieldType.EMAIL,
                    required=True,
                ),
            ],
        )


def test_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ApplicationFormAdapter()


def test_concrete_adapter_exposes_provider_name():
    adapter = FakeAdapter()

    assert adapter.provider_name == "Fake ATS"


def test_concrete_adapter_returns_normalized_form():
    adapter = FakeAdapter()

    form = adapter.inspect()

    assert isinstance(form, ApplicationForm)
    assert form.provider == "Fake ATS"
    assert form.job_url == "https://example.com/jobs/123"
    assert len(form.fields) == 2


def test_adapter_normalizes_field_types():
    adapter = FakeAdapter()

    form = adapter.inspect()

    assert (
        form.fields[0].field_type
        == FormFieldType.TEXT
    )

    assert (
        form.fields[1].field_type
        == FormFieldType.EMAIL
    )


def test_adapter_preserves_required_state():
    adapter = FakeAdapter()

    form = adapter.inspect()

    assert form.fields[0].required is True
    assert form.fields[1].required is True