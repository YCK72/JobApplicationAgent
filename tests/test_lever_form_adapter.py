from unittest.mock import MagicMock

import pytest

from app.applications.adapters.lever import LeverFormAdapter
from app.applications.form_models import FormControlKind, FormFieldType


LEVER_URL = "https://jobs.lever.co/example/123/apply"


def make_control(
    *,
    tag_name: str = "input",
    attributes: dict[str, str | None] | None = None,
    value: str = "",
    options: list[tuple[str, str]] | None = None,
    checked: bool = False,
    wrapped_label: str | None = None,
    question_label: str | None = None,
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
            lambda name, value=native_value: value if name == "value" else None
        )
        option_objects.append(option)
    option_locator.nth.side_effect = lambda index: option_objects[index]

    def locate(selector: str):
        if selector == "option":
            return option_locator
        locator = MagicMock()
        text = None
        if selector == "xpath=ancestor::label[1]":
            text = wrapped_label
        elif "application-question" in selector:
            text = question_label
        locator.count.return_value = 1 if text is not None else 0
        if text is not None:
            locator.first.inner_text.return_value = text
        return locator

    control.locator.side_effect = locate
    return control


def make_page(
    controls: list[MagicMock],
    labels: dict[str, str] | None = None,
) -> MagicMock:
    page = MagicMock()
    controls_locator = MagicMock()
    controls_locator.count.return_value = len(controls)
    controls_locator.nth.side_effect = lambda index: controls[index]
    labels = labels or {}

    def locate(selector: str):
        if selector == "input, textarea, select":
            return controls_locator
        locator = MagicMock()
        text = None
        for field_id, label in labels.items():
            if selector == f'label[for="{field_id}"]':
                text = label
                break
        locator.count.return_value = 1 if text is not None else 0
        if text is not None:
            locator.first.inner_text.return_value = text
        return locator

    page.locator.side_effect = locate
    return page


def make_session(page: MagicMock, *, started: bool = True) -> MagicMock:
    session = MagicMock()
    session.is_started = started
    session.page = page
    session.start.return_value = page
    return session


def test_provider_name_and_empty_url_validation() -> None:
    adapter = LeverFormAdapter(LEVER_URL, MagicMock())
    assert adapter.provider_name == "LEVER"

    with pytest.raises(ValueError, match="job_url must not be empty"):
        LeverFormAdapter("  ", MagicMock())


def test_inspect_normalizes_supported_native_controls_and_closes() -> None:
    controls = [
        make_control(attributes={"id": "name", "type": "text"}),
        make_control(attributes={"id": "email", "type": "email"}),
        make_control(attributes={"id": "phone", "type": "tel"}),
        make_control(tag_name="textarea", attributes={"id": "comments"}),
        make_control(
            tag_name="select",
            attributes={"id": "location"},
            options=[("Seattle", "sea-1"), ("New York", "nyc-2")],
            value="sea-1",
        ),
        make_control(attributes={"id": "consent", "type": "checkbox"}),
        make_control(attributes={"id": "resume", "type": "file"}),
    ]
    page = make_page(controls)
    session = make_session(page)

    form = LeverFormAdapter(LEVER_URL, session).inspect()

    session.navigate.assert_called_once_with(LEVER_URL)
    session.close.assert_called_once_with()
    assert form.provider == "LEVER"
    assert form.job_url == LEVER_URL
    assert [field.field_type for field in form.fields] == [
        FormFieldType.TEXT,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
        FormFieldType.TEXTAREA,
        FormFieldType.SELECT,
        FormFieldType.CHECKBOX,
        FormFieldType.FILE,
    ]
    assert form.fields[3].control_kind == FormControlKind.NATIVE_TEXTAREA
    assert form.fields[4].control_kind == FormControlKind.NATIVE_SELECT
    assert form.fields[4].current_value == "Seattle"
    assert [(item.label, item.value) for item in form.fields[4].option_details] == [
        ("Seattle", "sea-1"),
        ("New York", "nyc-2"),
    ]
    assert form.fields[5].current_checked is False
    assert form.fields[6].current_value is None


def test_lever_question_container_supplies_semantic_label() -> None:
    control = make_control(
        attributes={"name": "cards[abc][field0]", "type": "text", "required": ""},
        question_label="Why do you want to join us? ✱",
    )
    form = LeverFormAdapter(LEVER_URL, make_session(make_page([control]))).inspect()

    assert form.fields[0].field_id == "cards[abc][field0]"
    assert form.fields[0].label == "Why do you want to join us?"
    assert form.fields[0].required is True


def test_wrapping_label_takes_precedence_for_radio_option() -> None:
    yes = make_control(
        attributes={"id": "yes", "name": "relocate", "type": "radio", "value": "1"},
        wrapped_label="Yes",
        checked=True,
    )
    no = make_control(
        attributes={"id": "no", "name": "relocate", "type": "radio", "value": "0"},
        wrapped_label="No",
    )
    form = LeverFormAdapter(
        LEVER_URL,
        make_session(make_page([yes, no])),
    ).inspect()

    assert len(form.fields) == 1
    field = form.fields[0]
    assert field.field_id == "relocate"
    assert field.field_type == FormFieldType.RADIO
    assert field.options == ["Yes", "No"]
    assert [(item.label, item.value) for item in field.option_details] == [
        ("Yes", "1"),
        ("No", "0"),
    ]
    assert field.current_value == "Yes"


@pytest.mark.parametrize("input_type", ["hidden", "submit", "button", "reset", "image"])
def test_hidden_and_action_controls_are_ignored(input_type: str) -> None:
    hidden = make_control(attributes={"id": input_type, "type": input_type})
    form = LeverFormAdapter(
        LEVER_URL,
        make_session(make_page([hidden])),
    ).inspect()
    assert form.fields == []


def test_inspection_starts_session_and_never_mutates_controls() -> None:
    control = make_control(attributes={"id": "name", "type": "text"})
    session = make_session(make_page([control]), started=False)

    LeverFormAdapter(LEVER_URL, session).inspect()

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
        LeverFormAdapter(LEVER_URL, session).inspect()
    session.close.assert_called_once_with()

    session = make_session(make_page([]))
    adapter = LeverFormAdapter(LEVER_URL, session)
    monkeypatch.setattr(
        adapter,
        "_inspect_fields",
        MagicMock(side_effect=RuntimeError("inspection failed")),
    )
    with pytest.raises(RuntimeError, match="inspection failed"):
        adapter.inspect()
    session.close.assert_called_once_with()
