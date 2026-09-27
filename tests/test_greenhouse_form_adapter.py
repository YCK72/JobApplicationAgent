from unittest.mock import MagicMock

from app.applications.adapters.greenhouse import (
    GreenhouseFormAdapter,
)
from app.applications.form_models import (
    FormFieldType,
)


def make_control(
    *,
    tag_name: str = "input",
    attributes: dict[str, str | None] | None = None,
    value: str = "",
    options: list[str] | None = None,
) -> MagicMock:
    control = MagicMock()

    attributes = attributes or {}

    control.evaluate.return_value = tag_name

    control.get_attribute.side_effect = (
        lambda name: attributes.get(name)
    )

    control.input_value.return_value = value

    option_locator = MagicMock()

    option_values = options or []

    option_locator.count.return_value = len(option_values)

    option_objects = []

    for option_text in option_values:
        option = MagicMock()
        option.inner_text.return_value = option_text
        option_objects.append(option)

    option_locator.nth.side_effect = (
        lambda index: option_objects[index]
    )

    control.locator.return_value = option_locator

    return control


def make_page(
    controls: list[MagicMock],
    labels: dict[str, str] | None = None,
    labelled_by: dict[str, str] | None = None,
) -> MagicMock:
    page = MagicMock()

    controls_locator = MagicMock()
    controls_locator.count.return_value = len(controls)
    controls_locator.nth.side_effect = (
        lambda index: controls[index]
    )

    page.locator.side_effect = lambda selector: (
        controls_locator
        if selector == "input, textarea, select"
        else make_label_locator(
            selector=selector,
            labels=labels or {},
            labelled_by=labelled_by or {},
        )
    )

    return page


def make_label_locator(
    *,
    selector: str,
    labels: dict[str, str],
    labelled_by: dict[str, str] | None = None,
) -> MagicMock:
    locator = MagicMock()

    matched_text = None

    for field_id, label_text in labels.items():
        expected = f'label[for="{field_id}"]'

        if selector == expected:
            matched_text = label_text
            break

    if matched_text is None:
        for label_id, label_text in (
            labelled_by or {}
        ).items():
            expected = f"#{label_id}"

            if selector == expected:
                matched_text = label_text
                break

    if matched_text is None:
        locator.count.return_value = 0
        return locator

    locator.count.return_value = 1

    label = MagicMock()
    label.inner_text.return_value = matched_text

    locator.first = label

    return locator


def make_browser_session(
    page: MagicMock,
    *,
    started: bool = True,
) -> MagicMock:
    session = MagicMock()

    session.is_started = started
    session.page = page
    session.start.return_value = page

    return session


def test_provider_name() -> None:
    session = MagicMock()

    adapter = GreenhouseFormAdapter(
        job_url="https://boards.greenhouse.io/example/jobs/123",
        browser_session=session,
    )

    assert adapter.provider_name == "GREENHOUSE"


def test_empty_job_url_is_rejected() -> None:
    session = MagicMock()

    try:
        GreenhouseFormAdapter(
            job_url="   ",
            browser_session=session,
        )
    except ValueError as exc:
        assert "job_url must not be empty" in str(exc)
    else:
        raise AssertionError(
            "Expected empty job URL to raise ValueError."
        )


def test_inspect_navigates_and_returns_application_form() -> None:
    first_name = make_control(
        attributes={
            "id": "first_name",
            "name": "first_name",
            "type": "text",
            "required": "",
        },
    )

    email = make_control(
        attributes={
            "id": "email",
            "name": "email",
            "type": "email",
        },
    )

    page = make_page(
        controls=[first_name, email],
        labels={
            "first_name": "First Name",
            "email": "Email",
        },
    )

    session = make_browser_session(page)

    url = "https://boards.greenhouse.io/example/jobs/123"

    adapter = GreenhouseFormAdapter(
        job_url=url,
        browser_session=session,
    )

    form = adapter.inspect()

    session.navigate.assert_called_once_with(url)

    assert form.provider == "GREENHOUSE"
    assert form.job_url == url
    assert len(form.fields) == 2

    assert form.fields[0].field_id == "first_name"
    assert form.fields[0].label == "First Name"
    assert form.fields[0].field_type == FormFieldType.TEXT
    assert form.fields[0].required is True

    assert form.fields[1].field_id == "email"
    assert form.fields[1].label == "Email"
    assert form.fields[1].field_type == FormFieldType.EMAIL


def test_inspect_starts_browser_when_not_started() -> None:
    page = make_page([])

    session = make_browser_session(
        page,
        started=False,
    )

    adapter = GreenhouseFormAdapter(
        job_url="https://boards.greenhouse.io/example/jobs/123",
        browser_session=session,
    )

    adapter.inspect()

    session.start.assert_called_once_with()
    session.navigate.assert_called_once()


def test_supported_field_types_are_normalized() -> None:
    controls = [
        make_control(
            attributes={
                "id": "name",
                "type": "text",
            },
        ),
        make_control(
            attributes={
                "id": "email",
                "type": "email",
            },
        ),
        make_control(
            attributes={
                "id": "phone",
                "type": "tel",
            },
        ),
        make_control(
            tag_name="textarea",
            attributes={
                "id": "cover_letter",
            },
        ),
        make_control(
            tag_name="select",
            attributes={
                "id": "location",
            },
            options=[
                "Select...",
                "Seattle",
                "New York",
            ],
        ),
        make_control(
            attributes={
                "id": "remote",
                "type": "radio",
            },
        ),
        make_control(
            attributes={
                "id": "consent",
                "type": "checkbox",
            },
        ),
        make_control(
            attributes={
                "id": "resume",
                "type": "file",
            },
        ),
    ]

    page = make_page(controls)

    session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url="https://boards.greenhouse.io/example/jobs/123",
        browser_session=session,
    )

    form = adapter.inspect()

    assert [
        field.field_type
        for field in form.fields
    ] == [
        FormFieldType.TEXT,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
        FormFieldType.TEXTAREA,
        FormFieldType.SELECT,
        FormFieldType.RADIO,
        FormFieldType.CHECKBOX,
        FormFieldType.FILE,
    ]

    assert form.fields[4].options == [
        "Select...",
        "Seattle",
        "New York",
    ]

    assert form.fields[7].current_value is None


def test_hidden_and_action_controls_are_ignored() -> None:
    controls = [
        make_control(
            attributes={
                "id": "visible",
                "type": "text",
            },
        ),
        make_control(
            attributes={
                "id": "hidden",
                "type": "hidden",
            },
        ),
        make_control(
            attributes={
                "id": "submit",
                "type": "submit",
            },
        ),
        make_control(
            attributes={
                "id": "button",
                "type": "button",
            },
        ),
        make_control(
            attributes={
                "id": "reset",
                "type": "reset",
            },
        ),
        make_control(
            attributes={
                "id": "image",
                "type": "image",
            },
        ),
    ]

    page = make_page(controls)

    session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url="https://boards.greenhouse.io/example/jobs/123",
        browser_session=session,
    )

    form = adapter.inspect()

    assert len(form.fields) == 1
    assert form.fields[0].field_id == "visible"


def test_label_fallback_order() -> None:
    labelled = make_control(
        attributes={
            "id": "first_name",
            "type": "text",
            "aria-label": "Ignored aria",
            "placeholder": "Ignored placeholder",
            "name": "ignored_name",
        },
    )

    aria = make_control(
        attributes={
            "id": "email",
            "type": "email",
            "aria-label": "Email Address",
            "placeholder": "Ignored placeholder",
            "name": "ignored_name",
        },
    )

    placeholder = make_control(
        attributes={
            "id": "phone",
            "type": "tel",
            "placeholder": "Phone Number",
            "name": "ignored_name",
        },
    )

    name = make_control(
        attributes={
            "id": "location",
            "type": "text",
            "name": "preferred_location",
        },
    )

    page = make_page(
        controls=[
            labelled,
            aria,
            placeholder,
            name,
        ],
        labels={
            "first_name": "First Name",
        },
    )

    session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url="https://boards.greenhouse.io/example/jobs/123",
        browser_session=session,
    )

    form = adapter.inspect()

    assert form.fields[0].label == "First Name"
    assert form.fields[1].label == "Email Address"
    assert form.fields[2].label == "Phone Number"
    assert form.fields[3].label == "preferred location"


def test_required_supports_required_and_aria_required() -> None:
    required = make_control(
        attributes={
            "id": "first",
            "type": "text",
            "required": "",
        },
    )

    aria_required = make_control(
        attributes={
            "id": "second",
            "type": "text",
            "aria-required": "true",
        },
    )

    optional = make_control(
        attributes={
            "id": "third",
            "type": "text",
        },
    )

    page = make_page(
        [
            required,
            aria_required,
            optional,
        ]
    )

    session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url="https://boards.greenhouse.io/example/jobs/123",
        browser_session=session,
    )

    form = adapter.inspect()

    assert form.fields[0].required is True
    assert form.fields[1].required is True
    assert form.fields[2].required is False


def test_field_id_falls_back_to_name_then_generated_id() -> None:
    name_only = make_control(
        attributes={
            "name": "candidate_name",
            "type": "text",
        },
    )

    no_identifier = make_control(
        attributes={
            "type": "text",
            "placeholder": "Portfolio",
        },
    )

    page = make_page(
        [
            name_only,
            no_identifier,
        ]
    )

    session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url="https://boards.greenhouse.io/example/jobs/123",
        browser_session=session,
    )

    form = adapter.inspect()

    assert form.fields[0].field_id == "candidate_name"
    assert form.fields[1].field_id == "greenhouse-field-1"


def test_current_value_is_read_without_modifying_control() -> None:
    control = make_control(
        attributes={
            "id": "first_name",
            "type": "text",
        },
        value="Existing Value",
    )

    page = make_page([control])

    session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url="https://boards.greenhouse.io/example/jobs/123",
        browser_session=session,
    )

    form = adapter.inspect()

    assert form.fields[0].current_value == "Existing Value"

    control.input_value.assert_called_once_with()


def test_inspect_closes_browser_after_success() -> None:
    page = make_page([])

    session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=session,
    )

    form = adapter.inspect()

    assert form.provider == "GREENHOUSE"

    session.close.assert_called_once_with()


def test_inspect_closes_browser_when_navigation_fails() -> None:
    page = make_page([])

    session = make_browser_session(page)

    session.navigate.side_effect = RuntimeError(
        "Navigation failed"
    )

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=session,
    )

    try:
        adapter.inspect()
    except RuntimeError as exc:
        assert str(exc) == "Navigation failed"
    else:
        raise AssertionError(
            "Expected navigation failure."
        )

    session.close.assert_called_once_with()


def test_inspect_closes_browser_when_form_inspection_fails(
    monkeypatch,
) -> None:
    page = make_page([])

    session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=session,
    )

    def fail_inspection(page):
        raise RuntimeError(
            "Form inspection failed"
        )

    monkeypatch.setattr(
        adapter,
        "_inspect_fields",
        fail_inspection,
    )

    try:
        adapter.inspect()
    except RuntimeError as exc:
        assert str(exc) == "Form inspection failed"
    else:
        raise AssertionError(
            "Expected form inspection failure."
        )

    session.close.assert_called_once_with()


def test_greenhouse_internal_required_helper_is_ignored():
    helper = make_control(
        tag_name="input",
        attributes={
            "class": "remix-css-1a0ro4n-requiredInput",
            "required": "",
        },
    )

    page = make_page([helper])
    browser_session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://job-boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=browser_session,
    )

    form = adapter.inspect()

    assert form.fields == []


def test_phone_country_search_input_is_ignored():
    search_input = make_control(
        tag_name="input",
        attributes={
            "id": "iti-0__search-input",
            "type": "search",
            "role": "combobox",
            "aria-label": "Search",
            "class": "iti__search-input",
        },
    )

    page = make_page([search_input])
    browser_session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://job-boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=browser_session,
    )

    form = adapter.inspect()

    assert form.fields == []


def test_email_autocomplete_is_normalized_as_email():
    email_input = make_control(
        tag_name="input",
        attributes={
            "id": "email",
            "type": "text",
            "autocomplete": "email",
            "aria-label": "Email",
            "aria-required": "true",
        },
    )

    page = make_page([email_input])
    browser_session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://job-boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=browser_session,
    )

    form = adapter.inspect()

    assert len(form.fields) == 1
    assert form.fields[0].field_type == FormFieldType.EMAIL


def test_greenhouse_combobox_is_normalized_as_select():
    combobox = make_control(
        tag_name="input",
        attributes={
            "id": "question_123",
            "type": "text",
            "role": "combobox",
            "aria-labelledby": "question_123-label",
            "aria-required": "true",
            "class": "select__input",
        },
    )

    page = make_page([combobox])
    browser_session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://job-boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=browser_session,
    )

    form = adapter.inspect()

    assert len(form.fields) == 1
    assert form.fields[0].field_type == FormFieldType.SELECT
    assert form.fields[0].required is True


def test_file_input_uses_semantic_id_for_label_when_visible_label_is_generic():
    resume = make_control(
        tag_name="input",
        attributes={
            "id": "resume",
            "type": "file",
        },
    )

    page = make_page(
        [resume],
        labels={
            "resume": "Attach",
        },
    )
    browser_session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://job-boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=browser_session,
    )

    form = adapter.inspect()

    assert len(form.fields) == 1
    assert form.fields[0].field_type == FormFieldType.FILE
    assert form.fields[0].label.lower() == "resume"

def test_greenhouse_combobox_uses_aria_labelledby_for_label():
    combobox = make_control(
        tag_name="input",
        attributes={
            "id": "question_12836847007",
            "type": "text",
            "role": "combobox",
            "aria-labelledby": (
                "question_12836847007-label"
            ),
            "aria-required": "true",
            "class": "select__input",
        },
    )

    page = make_page(
        [combobox],
        labelled_by={
            "question_12836847007-label": (
                "Are you authorized to work in the U.S.?*"
            ),
        },
    )

    browser_session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://job-boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=browser_session,
    )

    form = adapter.inspect()

    assert len(form.fields) == 1

    field = form.fields[0]

    assert field.field_id == "question_12836847007"
    assert field.field_type == FormFieldType.SELECT
    assert field.required is True
    assert (
        field.label
        == "Are you authorized to work in the U.S.?*"
    )


def test_cover_letter_file_input_uses_semantic_id_for_label():
    cover_letter = make_control(
        tag_name="input",
        attributes={
            "id": "cover_letter",
            "type": "file",
        },
    )

    page = make_page(
        [cover_letter],
        labels={
            "cover_letter": "Attach",
        },
    )
    browser_session = make_browser_session(page)

    adapter = GreenhouseFormAdapter(
        job_url=(
            "https://job-boards.greenhouse.io/"
            "example/jobs/123"
        ),
        browser_session=browser_session,
    )

    form = adapter.inspect()

    assert len(form.fields) == 1

    field = form.fields[0]

    assert field.field_id == "cover_letter"
    assert field.field_type == FormFieldType.FILE
    assert field.label.lower() == "cover letter"