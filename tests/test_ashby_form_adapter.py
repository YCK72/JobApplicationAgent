from unittest.mock import MagicMock

import pytest

from app.applications.adapters.ashby import AshbyFormAdapter
from app.applications.form_models import FormControlKind, FormFieldType


ASHBY_URL = "https://jobs.ashbyhq.com/example/123/application"


def make_text_locator(text: str | None, *, class_name: str = "") -> MagicMock:
    locator = MagicMock()
    locator.count.return_value = 1 if text is not None else 0
    if text is not None:
        locator.first.inner_text.return_value = text
        locator.first.get_attribute.side_effect = (
            lambda name: class_name if name == "class" else None
        )
    return locator


def make_control(
    *,
    tag_name: str = "input",
    attributes: dict[str, str | None] | None = None,
    value: str = "",
    options: list[tuple[str, str]] | None = None,
    checked: bool = False,
    entry_label: str | None = None,
    entry_label_class: str = "",
    autofill_helper: bool = False,
) -> MagicMock:
    control = MagicMock()
    attributes = attributes or {}
    control.evaluate.return_value = tag_name
    control.get_attribute.side_effect = lambda name: attributes.get(name)
    control.input_value.return_value = value
    control.is_checked.return_value = checked

    option_locator = MagicMock()
    option_values = options or []
    option_locator.count.return_value = len(option_values)
    option_objects = []
    for label, native_value in option_values:
        option = MagicMock()
        option.inner_text.return_value = label
        option.get_attribute.side_effect = (
            lambda name, current=native_value: current if name == "value" else None
        )
        option_objects.append(option)
    option_locator.nth.side_effect = lambda index: option_objects[index]

    def locate(selector: str):
        if selector == "option":
            return option_locator
        if "application-form-autofill-input-root" in selector:
            locator = MagicMock()
            locator.count.return_value = 1 if autofill_helper else 0
            return locator
        if "application-form-field-entry" in selector:
            return make_text_locator(
                entry_label,
                class_name=entry_label_class,
            )
        return make_text_locator(None)

    control.locator.side_effect = locate
    return control


def make_page(
    controls: list[MagicMock],
    labels: dict[str, str] | None = None,
    field_entry_count: int = 0,
) -> MagicMock:
    page = MagicMock()
    controls_locator = MagicMock()
    controls_locator.count.return_value = len(controls)
    controls_locator.nth.side_effect = lambda index: controls[index]
    labels = labels or {}

    def locate(selector: str):
        if selector == "input, textarea, select":
            return controls_locator
        if selector == ".ashby-application-form-field-entry":
            locator = MagicMock()
            locator.count.return_value = field_entry_count
            return locator
        for field_id, label in labels.items():
            if selector == f'label[for="{field_id}"]':
                return make_text_locator(label)
        return make_text_locator(None)

    page.locator.side_effect = locate
    return page


def make_session(page: MagicMock, *, started: bool = True) -> MagicMock:
    session = MagicMock()
    session.is_started = started
    session.page = page
    session.start.return_value = page
    return session


def test_provider_name_and_empty_url_validation() -> None:
    assert AshbyFormAdapter(ASHBY_URL, MagicMock()).provider_name == "ASHBY"

    with pytest.raises(ValueError, match="job_url must not be empty"):
        AshbyFormAdapter("  ", MagicMock())


def test_inspect_normalizes_native_and_ashby_url_controls() -> None:
    controls = [
        make_control(attributes={"id": "name", "type": "text"}),
        make_control(attributes={"id": "email", "type": "email"}),
        make_control(attributes={"id": "phone", "type": "tel"}),
        make_control(attributes={"id": "linkedin", "type": "url"}),
        make_control(tag_name="textarea", attributes={"id": "comments"}),
        make_control(
            tag_name="select",
            attributes={"id": "location"},
            options=[("Seattle", "sea-1"), ("New York", "nyc-2")],
            value="nyc-2",
        ),
        make_control(
            attributes={"id": "consent", "type": "checkbox"},
            value="on",
        ),
        make_control(attributes={"id": "resume", "type": "file"}),
    ]
    session = make_session(make_page(controls))

    form = AshbyFormAdapter(ASHBY_URL, session).inspect()

    session.navigate.assert_called_once_with(ASHBY_URL)
    session.close.assert_called_once_with()
    assert form.provider == "ASHBY"
    assert [field.field_type for field in form.fields] == [
        FormFieldType.TEXT,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.SELECT,
        FormFieldType.CHECKBOX,
        FormFieldType.FILE,
    ]
    assert form.fields[5].control_kind == FormControlKind.NATIVE_SELECT
    assert form.fields[5].current_value == "New York"
    assert form.fields[6].current_checked is False
    assert form.fields[6].current_value is None
    assert form.fields[7].current_value is None


def test_ashby_field_container_supplies_label_and_requiredness() -> None:
    control = make_control(
        attributes={"name": "question-123", "type": "text"},
        entry_label="Why Ashby?",
        entry_label_class=(
            "_heading_hash _required_hash "
            "ashby-application-form-question-title"
        ),
    )

    form = AshbyFormAdapter(
        ASHBY_URL,
        make_session(make_page([control])),
    ).inspect()

    assert form.fields[0].field_id == "question-123"
    assert form.fields[0].label == "Why Ashby?"
    assert form.fields[0].required is True


def test_name_associated_label_is_used_when_control_has_no_id() -> None:
    control = make_control(
        attributes={"name": "choice-123", "type": "checkbox"},
        entry_label="Are you willing to relocate?",
        entry_label_class="ashby-application-form-question-title",
    )
    page = make_page([control], labels={"choice-123": "Relocation"})

    form = AshbyFormAdapter(ASHBY_URL, make_session(page)).inspect()

    assert form.fields[0].label == "Relocation"
    assert form.fields[0].field_type == FormFieldType.CHECKBOX


def test_custom_location_combobox_is_preserved_for_review() -> None:
    control = make_control(
        attributes={
            "role": "combobox",
            "placeholder": "Start typing...",
            "class": "ashby-application-form-input-autocomplete",
        },
        entry_label="Location",
        entry_label_class="ashby-application-form-question-title",
    )
    form = AshbyFormAdapter(
        ASHBY_URL,
        make_session(make_page([control])),
    ).inspect()

    assert form.fields[0].label == "Location"
    assert form.fields[0].field_type == FormFieldType.SELECT
    assert form.fields[0].control_kind == FormControlKind.CUSTOM_COMBOBOX
    assert form.fields[0].options == []


def test_autofill_helper_and_recaptcha_response_are_ignored() -> None:
    autofill = make_control(
        attributes={"type": "file"},
        autofill_helper=True,
    )
    recaptcha = make_control(
        tag_name="textarea",
        attributes={
            "id": "g-recaptcha-response-100000",
            "class": "g-recaptcha-response",
        },
    )
    visible = make_control(attributes={"id": "name", "type": "text"})

    form = AshbyFormAdapter(
        ASHBY_URL,
        make_session(make_page([autofill, recaptcha, visible])),
    ).inspect()

    assert [field.field_id for field in form.fields] == ["name"]


def test_inspection_starts_session_and_never_mutates_controls() -> None:
    control = make_control(attributes={"id": "name", "type": "text"})
    session = make_session(make_page([control]), started=False)

    AshbyFormAdapter(ASHBY_URL, session).inspect()

    session.start.assert_called_once_with()
    control.fill.assert_not_called()
    control.click.assert_not_called()
    control.check.assert_not_called()
    control.select_option.assert_not_called()
    control.set_input_files.assert_not_called()


def test_browser_closes_when_navigation_or_inspection_fails(monkeypatch) -> None:
    session = make_session(make_page([]))
    session.navigate.side_effect = RuntimeError("navigation failed")
    with pytest.raises(RuntimeError, match="navigation failed"):
        AshbyFormAdapter(ASHBY_URL, session).inspect()
    session.close.assert_called_once_with()

    session = make_session(make_page([]))
    adapter = AshbyFormAdapter(ASHBY_URL, session)
    monkeypatch.setattr(
        adapter,
        "_inspect_fields",
        MagicMock(side_effect=RuntimeError("inspection failed")),
    )
    with pytest.raises(RuntimeError, match="inspection failed"):
        adapter.inspect()
    session.close.assert_called_once_with()


def test_empty_rendered_form_fails_closed_and_closes_browser() -> None:
    session = make_session(make_page([]))

    with pytest.raises(ValueError, match="did not expose any application fields"):
        AshbyFormAdapter(ASHBY_URL, session).inspect()

    session.close.assert_called_once_with()


def test_unrepresented_custom_field_entry_fails_closed() -> None:
    visible = make_control(attributes={"id": "name", "type": "text"})
    session = make_session(
        make_page([visible], field_entry_count=2)
    )

    with pytest.raises(ValueError, match="unsupported application controls"):
        AshbyFormAdapter(ASHBY_URL, session).inspect()

    session.close.assert_called_once_with()
