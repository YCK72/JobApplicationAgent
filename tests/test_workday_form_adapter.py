from unittest.mock import MagicMock

import pytest

from app.applications.adapters.workday import WorkdayFormAdapter
from app.applications.form_models import FormControlKind, FormFieldType


WORKDAY_URL = (
    "https://example.wd1.myworkdayjobs.com/en-US/External/job/"
    "Software-Engineer_R123/apply/applyManually"
)


def text_locator(
    text: str | None = None,
    *,
    attributes: dict[str, str | None] | None = None,
) -> MagicMock:
    locator = MagicMock()
    locator.count.return_value = 1 if text is not None else 0
    attributes = attributes or {}
    if text is not None:
        locator.first.inner_text.return_value = text
        locator.first.get_attribute.side_effect = lambda name: attributes.get(name)
    return locator


def make_control(
    *,
    tag_name: str = "input",
    attributes: dict[str, str | None] | None = None,
    value: str = "",
    options: list[tuple[str, str]] | None = None,
    checked: bool = False,
    group_label_id: str | None = None,
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
        if selector == "xpath=ancestor::*[@role='group'][1]":
            locator = text_locator("group" if group_label_id else None)
            if group_label_id:
                locator.first.get_attribute.side_effect = (
                    lambda name: group_label_id if name == "aria-labelledby" else None
                )
            return locator
        return text_locator(None)

    control.locator.side_effect = locate
    return control


def make_page(
    controls: list[MagicMock],
    *,
    labels: dict[str, str] | None = None,
    referenced_labels: dict[str, str] | None = None,
) -> MagicMock:
    page = MagicMock()
    controls_locator = MagicMock()
    controls_locator.count.return_value = len(controls)
    controls_locator.nth.side_effect = lambda index: controls[index]
    labels = labels or {}
    referenced_labels = referenced_labels or {}

    def locate(selector: str):
        if selector == "input, textarea, select, button[id][name]":
            return controls_locator
        for field_id, label in labels.items():
            if selector == f'label[for="{field_id}"]':
                return text_locator(label)
        for field_id, label in referenced_labels.items():
            if selector == f"#{field_id}":
                return text_locator(label)
        return text_locator(None)

    page.locator.side_effect = locate
    return page


def make_session(page: MagicMock, *, started: bool = True) -> MagicMock:
    session = MagicMock()
    session.is_started = started
    session.page = page
    session.start.return_value = page
    return session


def test_provider_name_and_empty_url_validation() -> None:
    assert WorkdayFormAdapter(WORKDAY_URL, MagicMock()).provider_name == "WORKDAY"

    with pytest.raises(ValueError, match="job_url must not be empty"):
        WorkdayFormAdapter(" ", MagicMock())


def test_visible_native_controls_are_normalized_before_review_boundary() -> None:
    controls = [
        make_control(
            attributes={
                "id": "name--legalName--firstName",
                "name": "legalName--firstName",
                "type": "text",
                "aria-required": "true",
            },
        ),
        make_control(
            attributes={
                "id": "emailAddress--emailAddress",
                "name": "emailAddress",
                "type": "text",
            },
        ),
        make_control(
            attributes={
                "id": "phoneNumber--phoneNumber",
                "name": "phoneNumber",
                "type": "text",
            },
        ),
        make_control(tag_name="textarea", attributes={"id": "comments"}),
        make_control(
            tag_name="select",
            attributes={"id": "state", "name": "state"},
            options=[("California", "CA"), ("Washington", "WA")],
            value="WA",
        ),
        make_control(
            attributes={"id": "preferredCheck", "type": "checkbox"},
            value="on",
        ),
        make_control(attributes={"id": "resume", "type": "file"}),
    ]
    page = make_page(
        controls,
        labels={
            "name--legalName--firstName": "First Name*",
            "emailAddress--emailAddress": "Email*",
            "phoneNumber--phoneNumber": "Phone Number*",
            "comments": "Comments",
            "state": "State",
            "preferredCheck": "I have a preferred name",
            "resume": "Resume",
        },
    )
    session = make_session(page)

    form = WorkdayFormAdapter(WORKDAY_URL, session).inspect()

    session.navigate.assert_called_once_with(WORKDAY_URL)
    session.close.assert_called_once_with()
    assert form.provider == "WORKDAY"
    assert [field.field_type for field in form.fields[:-1]] == [
        FormFieldType.TEXT,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
        FormFieldType.TEXTAREA,
        FormFieldType.SELECT,
        FormFieldType.CHECKBOX,
        FormFieldType.FILE,
    ]
    assert form.fields[0].required is True
    assert form.fields[4].current_value == "Washington"
    assert form.fields[5].current_value is None
    assert form.fields[5].current_checked is False
    assert form.fields[-1].field_type == FormFieldType.UNKNOWN
    assert "multi-step" in form.fields[-1].label.lower()


def test_workday_custom_select_is_preserved_without_opening() -> None:
    button = make_control(
        tag_name="button",
        attributes={
            "id": "source--source",
            "name": "source",
            "type": "button",
            "aria-label": "How Did You Hear About Us? Select One Required",
        },
        value="Select One",
    )
    button.inner_text.return_value = "Select One"
    page = make_page(
        [button],
        labels={"source--source": "How Did You Hear About Us?*"},
    )

    form = WorkdayFormAdapter(WORKDAY_URL, make_session(page)).inspect()

    field = form.fields[0]
    assert field.label == "How Did You Hear About Us?"
    assert field.field_type == FormFieldType.SELECT
    assert field.control_kind == FormControlKind.CUSTOM_COMBOBOX
    assert field.options == []
    button.click.assert_not_called()


def test_radio_group_uses_accessible_question_and_semantic_options() -> None:
    yes = make_control(
        attributes={
            "id": "yes",
            "name": "candidateIsPreviousWorker",
            "type": "radio",
            "value": "yes",
        },
        checked=True,
        group_label_id="previousWorker-section",
    )
    no = make_control(
        attributes={
            "id": "no",
            "name": "candidateIsPreviousWorker",
            "type": "radio",
            "value": "no",
        },
        group_label_id="previousWorker-section",
    )
    page = make_page(
        [yes, no],
        labels={"yes": "Yes", "no": "No"},
        referenced_labels={
            "previousWorker-section": "Have you previously worked here?*"
        },
    )

    form = WorkdayFormAdapter(WORKDAY_URL, make_session(page)).inspect()

    field = form.fields[0]
    assert field.label == "Have you previously worked here?"
    assert field.field_type == FormFieldType.RADIO
    assert field.required is True
    assert field.options == ["Yes", "No"]
    assert field.current_value == "Yes"


def test_custom_select_helper_input_without_identity_is_ignored() -> None:
    helper = make_control(attributes={"type": "text", "class": "generated"})
    visible = make_control(attributes={"id": "firstName", "type": "text"})
    page = make_page([helper, visible], labels={"firstName": "First Name"})

    form = WorkdayFormAdapter(WORKDAY_URL, make_session(page)).inspect()

    assert [field.field_id for field in form.fields[:-1]] == ["firstName"]


def test_empty_visible_step_fails_closed() -> None:
    session = make_session(make_page([]))

    with pytest.raises(ValueError, match="did not expose any application fields"):
        WorkdayFormAdapter(WORKDAY_URL, session).inspect()

    session.close.assert_called_once_with()


def test_inspection_starts_session_and_never_mutates_controls() -> None:
    control = make_control(attributes={"id": "firstName", "type": "text"})
    session = make_session(
        make_page([control], labels={"firstName": "First Name"}),
        started=False,
    )

    WorkdayFormAdapter(WORKDAY_URL, session).inspect()

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
        WorkdayFormAdapter(WORKDAY_URL, session).inspect()
    session.close.assert_called_once_with()

    session = make_session(make_page([]))
    adapter = WorkdayFormAdapter(WORKDAY_URL, session)
    monkeypatch.setattr(
        adapter,
        "_inspect_fields",
        MagicMock(side_effect=RuntimeError("inspection failed")),
    )
    with pytest.raises(RuntimeError, match="inspection failed"):
        adapter.inspect()
    session.close.assert_called_once_with()
