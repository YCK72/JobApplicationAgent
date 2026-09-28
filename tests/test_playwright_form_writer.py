from unittest.mock import MagicMock

import pytest

from app.applications.form_models import (
    FormControlKind,
    FormField,
    FormFieldOption,
    FormFieldType,
)

from app.browser.playwright_form_writer import (
    PlaywrightFieldWriter,
    PlaywrightFieldWriterError,
)


def make_field(
    *,
    field_id: str = "first_name",
    label: str = "First Name",
    field_type: FormFieldType = FormFieldType.TEXT,
) -> FormField:
    return FormField(
        field_id=field_id,
        label=label,
        field_type=field_type,
    )


def make_page_with_locator_counts(
    *,
    id_count: int,
    name_count: int = 0,
):
    page = MagicMock()

    id_locator = MagicMock()
    id_locator.count.return_value = id_count

    name_locator = MagicMock()
    name_locator.count.return_value = name_count

    page.locator.side_effect = [
        id_locator,
        name_locator,
    ]

    return page, id_locator, name_locator


def make_select_field(
    *,
    field_id: str = "country",
    label: str = "Country",
    options: list[str] | None = None,
) -> FormField:
    resolved_options = (
        options
        if options is not None
        else [
            "United States",
            "Canada",
        ]
    )

    return FormField(
        field_id=field_id,
        label=label,
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.NATIVE_SELECT,
        options=resolved_options,
        option_details=[
            FormFieldOption(
                label=option,
                value=option,
            )
            for option in resolved_options
        ],
    )

def make_radio_field(
    *,
    field_id: str = "country",
    label: str = "Country",
    options: list[str] | None = None,
) -> FormField:
    resolved_options = (
        options
        if options is not None
        else [
            "United States",
            "Canada",
        ]
    )

    return FormField(
        field_id=field_id,
        label=label,
        field_type=FormFieldType.RADIO,
        options=resolved_options,
        option_details=[
            FormFieldOption(
                label=option,
                value=option,
            )
            for option in resolved_options
        ],
    )

@pytest.mark.parametrize(
    "field_type",
    [
        FormFieldType.TEXT,
        FormFieldType.TEXTAREA,
        FormFieldType.EMAIL,
        FormFieldType.PHONE,
    ],
)
def test_supported_text_field_is_filled(
    field_type: FormFieldType,
):
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    writer.write_text(
        make_field(field_type=field_type),
        "Test Value",
    )

    page.locator.assert_called_once_with(
        '[id="first_name"]'
    )

    locator.fill.assert_called_once_with("Test Value")


def test_name_is_used_when_id_does_not_exist():
    page, id_locator, name_locator = (
        make_page_with_locator_counts(
            id_count=0,
            name_count=1,
        )
    )

    writer = PlaywrightFieldWriter(page)

    writer.write_text(
        make_field(field_id="candidate[email]"),
        "test@example.com",
    )

    assert page.locator.call_args_list[0].args == (
        '[id="candidate[email]"]',
    )
    assert page.locator.call_args_list[1].args == (
        '[name="candidate[email]"]',
    )

    id_locator.fill.assert_not_called()
    name_locator.fill.assert_called_once_with(
        "test@example.com"
    )


@pytest.mark.parametrize(
    "field_type",
    [
        FormFieldType.SELECT,
        FormFieldType.RADIO,
        FormFieldType.CHECKBOX,
        FormFieldType.FILE,
        FormFieldType.UNKNOWN,
    ],
)
def test_unsupported_field_type_is_rejected_without_dom_mutation(
    field_type: FormFieldType,
):
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not supported",
    ):
        writer.write_text(
            make_field(field_type=field_type),
            "value",
        )

    page.locator.assert_not_called()


def test_missing_locator_is_rejected():
    page, id_locator, name_locator = (
        make_page_with_locator_counts(
            id_count=0,
            name_count=0,
        )
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be resolved",
    ):
        writer.write_text(
            make_field(),
            "Test",
        )

    id_locator.fill.assert_not_called()
    name_locator.fill.assert_not_called()


def test_duplicate_id_is_rejected():
    page = MagicMock()

    id_locator = MagicMock()
    id_locator.count.return_value = 2
    page.locator.return_value = id_locator

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="multiple controls by id",
    ):
        writer.write_text(
            make_field(),
            "Test",
        )

    assert page.locator.call_count == 1
    id_locator.fill.assert_not_called()


def test_duplicate_name_is_rejected():
    page, id_locator, name_locator = (
        make_page_with_locator_counts(
            id_count=0,
            name_count=2,
        )
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="multiple controls by name",
    ):
        writer.write_text(
            make_field(),
            "Test",
        )

    id_locator.fill.assert_not_called()
    name_locator.fill.assert_not_called()


def test_value_must_be_string():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="must be a string",
    ):
        writer.write_text(
            make_field(),
            123,  # type: ignore[arg-type]
        )

    page.locator.assert_not_called()


def test_selector_escapes_quotes_and_backslashes():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    writer.write_text(
        make_field(
            field_id='candidate\\"name',
        ),
        "Test",
    )

    page.locator.assert_called_once_with(
        '[id="candidate\\\\\\"name"]'
    )

    locator.fill.assert_called_once_with("Test")


def test_current_url_exposes_page_url_without_mutation():
    page = MagicMock()
    page.url = "https://example.com/application"

    writer = PlaywrightFieldWriter(page)

    assert writer.current_url == "https://example.com/application"

    page.locator.assert_not_called()


def test_native_select_uses_exact_inspected_option_label():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = "SELECT"

    option_locator = MagicMock()
    option_locator.count.return_value = 1
    locator.locator.return_value = option_locator

    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_select_field(
        options=[
            "Select...",
            "United States",
            "Canada",
        ],
    )

    writer.select_option(
        field,
        "United States",
    )

    page.locator.assert_called_once_with(
        '[id="country"]'
    )

    locator.evaluate.assert_called_once_with(
        "element => element.tagName"
    )

    locator.select_option.assert_called_once_with(
        value="United States"
    )

    locator.fill.assert_not_called()


def test_select_uses_name_when_id_does_not_exist():
    page, id_locator, name_locator = (
        make_page_with_locator_counts(
            id_count=0,
            name_count=1,
        )
    )

    name_locator.evaluate.return_value = "SELECT"

    option_locator = MagicMock()
    option_locator.count.return_value = 1
    name_locator.locator.return_value = option_locator

    writer = PlaywrightFieldWriter(page)

    field = make_select_field(
        field_id="candidate[country]",
    )

    writer.select_option(
        field,
        "United States",
    )

    assert page.locator.call_args_list[0].args == (
        '[id="candidate[country]"]',
    )
    assert page.locator.call_args_list[1].args == (
        '[name="candidate[country]"]',
    )

    id_locator.select_option.assert_not_called()

    name_locator.evaluate.assert_called_once_with(
        "element => element.tagName"
    )

    name_locator.select_option.assert_called_once_with(
        value="United States"
    )


def test_select_rejects_non_select_field_without_dom_mutation():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not supported",
    ):
        writer.select_option(
            make_field(
                field_type=FormFieldType.TEXT,
            ),
            "United States",
        )

    page.locator.assert_not_called()


def test_select_rejects_missing_inspected_options():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    field = make_select_field(
        options=[],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="no inspected options",
    ):
        writer.select_option(
            field,
            "United States",
        )

    page.locator.assert_not_called()


def test_select_rejects_value_not_in_inspected_options():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    field = make_select_field()

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected option",
    ):
        writer.select_option(
            field,
            "US",
        )

    page.locator.assert_not_called()


def test_select_rejects_duplicate_exact_inspected_options():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    field = make_select_field(
        options=[
            "United States",
            "United States",
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected option",
    ):
        writer.select_option(
            field,
            "United States",
        )

    page.locator.assert_not_called()


def test_select_rejects_empty_value():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    field = make_select_field(
        options=[
            "United States",
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="must not be empty",
    ):
        writer.select_option(
            field,
            "   ",
        )

    page.locator.assert_not_called()


def test_select_missing_locator_is_rejected():
    page, id_locator, name_locator = (
        make_page_with_locator_counts(
            id_count=0,
            name_count=0,
        )
    )

    writer = PlaywrightFieldWriter(page)

    field = make_select_field(
        options=[
            "United States",
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be resolved",
    ):
        writer.select_option(
            field,
            "United States",
        )

    id_locator.select_option.assert_not_called()
    name_locator.select_option.assert_not_called()


def test_select_duplicate_id_is_rejected():
    page = MagicMock()

    id_locator = MagicMock()
    id_locator.count.return_value = 2
    page.locator.return_value = id_locator

    writer = PlaywrightFieldWriter(page)

    field = make_select_field(
        options=[
            "United States",
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="multiple controls by id",
    ):
        writer.select_option(
            field,
            "United States",
        )

    assert page.locator.call_count == 1
    id_locator.select_option.assert_not_called()


def test_select_duplicate_name_is_rejected():
    page, id_locator, name_locator = (
        make_page_with_locator_counts(
            id_count=0,
            name_count=2,
        )
    )

    writer = PlaywrightFieldWriter(page)

    field = make_select_field(
        options=[
            "United States",
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="multiple controls by name",
    ):
        writer.select_option(
            field,
            "United States",
        )

    id_locator.select_option.assert_not_called()
    name_locator.select_option.assert_not_called()


def test_select_rejects_custom_combobox_before_mutation():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = "INPUT"
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_select_field()

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not a native HTML select control",
    ):
        writer.select_option(
            field,
            "United States",
        )

    locator.evaluate.assert_called_once_with(
        "element => element.tagName"
    )
    locator.select_option.assert_not_called()
    locator.fill.assert_not_called()


@pytest.mark.parametrize(
    "tag_name",
    [
        "INPUT",
        "DIV",
        "BUTTON",
        "TEXTAREA",
    ],
)
def test_select_rejects_non_native_dom_controls(
    tag_name: str,
):
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = tag_name
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not a native HTML select control",
    ):
        writer.select_option(
            make_select_field(),
            "United States",
        )

    locator.select_option.assert_not_called()


def test_select_accepts_case_insensitive_native_tag_name():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = "select"

    option_locator = MagicMock()
    option_locator.count.return_value = 1
    locator.locator.return_value = option_locator

    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    writer.select_option(
        make_select_field(),
        "United States",
    )

    locator.select_option.assert_called_once_with(
        value="United States"
    )


def test_select_rejects_non_string_dom_tag_name():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = None
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be safely verified",
    ):
        writer.select_option(
            make_select_field(),
            "United States",
        )

    locator.select_option.assert_not_called()


def test_select_rejects_dom_tag_inspection_failure():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.side_effect = RuntimeError(
        "DOM inspection failed"
    )
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be safely verified",
    ):
        writer.select_option(
            make_select_field(),
            "United States",
        )

    locator.select_option.assert_not_called()

def test_native_file_input_uploads_exact_pdf(tmp_path):
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4 test")

    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "file",
    }
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="resume",
        label="Resume",
        field_type=FormFieldType.FILE,
    )

    writer.upload_file(
        field,
        str(resume_path),
    )

    page.locator.assert_called_once_with(
        '[id="resume"]'
    )

    locator.evaluate.assert_called_once()

    locator.set_input_files.assert_called_once_with(
        str(resume_path.resolve())
    )

    locator.fill.assert_not_called()
    locator.select_option.assert_not_called()


def test_file_upload_rejects_non_file_field(tmp_path):
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4 test")

    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not supported for file upload",
    ):
        writer.upload_file(
            make_field(field_type=FormFieldType.TEXT),
            str(resume_path),
        )

    page.locator.assert_not_called()


def test_file_upload_rejects_missing_file(tmp_path):
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    missing_path = tmp_path / "missing.pdf"

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be safely resolved",
    ):
        writer.upload_file(
            make_field(
                field_id="resume",
                label="Resume",
                field_type=FormFieldType.FILE,
            ),
            str(missing_path),
        )

    page.locator.assert_not_called()


def test_file_upload_rejects_non_pdf(tmp_path):
    document_path = tmp_path / "resume.txt"
    document_path.write_text(
        "not a resume pdf",
        encoding="utf-8",
    )

    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="Only PDF files",
    ):
        writer.upload_file(
            make_field(
                field_id="resume",
                label="Resume",
                field_type=FormFieldType.FILE,
            ),
            str(document_path),
        )

    page.locator.assert_not_called()


@pytest.mark.parametrize(
    ("tag_name", "input_type"),
    [
        ("DIV", "file"),
        ("INPUT", "text"),
        ("BUTTON", "button"),
        ("SELECT", "select-one"),
    ],
)
def test_file_upload_rejects_non_native_file_controls(
    tmp_path,
    tag_name: str,
    input_type: str,
):
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4 test")

    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": tag_name,
        "type": input_type,
    }
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not a native HTML file input",
    ):
        writer.upload_file(
            make_field(
                field_id="resume",
                label="Resume",
                field_type=FormFieldType.FILE,
            ),
            str(resume_path),
        )

    locator.set_input_files.assert_not_called()


def test_file_upload_rejects_unverifiable_dom_control(tmp_path):
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4 test")

    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = None
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be safely verified",
    ):
        writer.upload_file(
            make_field(
                field_id="resume",
                label="Resume",
                field_type=FormFieldType.FILE,
            ),
            str(resume_path),
        )

    locator.set_input_files.assert_not_called()


def test_file_upload_rejects_dom_inspection_failure(tmp_path):
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4 test")

    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.side_effect = RuntimeError(
        "DOM inspection failed"
    )
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be safely verified",
    ):
        writer.upload_file(
            make_field(
                field_id="resume",
                label="Resume",
                field_type=FormFieldType.FILE,
            ),
            str(resume_path),
        )

    locator.set_input_files.assert_not_called()

def test_native_radio_selects_exact_inspected_option():
    page = MagicMock()

    group_locator = MagicMock()
    group_locator.count.return_value = 2

    option_locator = MagicMock()
    option_locator.count.return_value = 1
    option_locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "radio",
    }

    page.locator.side_effect = [
        group_locator,
        option_locator,
    ]

    writer = PlaywrightFieldWriter(page)

    field = make_radio_field()

    writer.select_radio_option(
        field,
        "United States",
    )

    assert page.locator.call_args_list[0].args == (
        '[name="country"]',
    )

    option_locator.check.assert_called_once_with()

    option_locator.fill.assert_not_called()
    option_locator.select_option.assert_not_called()


def test_radio_rejects_non_radio_field_without_dom_mutation():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not supported",
    ):
        writer.select_radio_option(
            make_field(
                field_type=FormFieldType.TEXT,
            ),
            "United States",
        )

    page.locator.assert_not_called()


def test_radio_rejects_missing_inspected_options():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    field = make_radio_field(
        options=[],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="no inspected options",
    ):
        writer.select_radio_option(
            field,
            "United States",
        )

    page.locator.assert_not_called()


def test_radio_rejects_value_not_in_inspected_options():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected option",
    ):
        writer.select_radio_option(
            make_radio_field(),
            "US",
        )

    page.locator.assert_not_called()


def test_radio_rejects_duplicate_exact_inspected_options():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    field = make_radio_field(
        options=[
            "United States",
            "United States",
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected option",
    ):
        writer.select_radio_option(
            field,
            "United States",
        )

    page.locator.assert_not_called()


def test_radio_rejects_empty_value():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="must not be empty",
    ):
        writer.select_radio_option(
            make_radio_field(),
            "   ",
        )

    page.locator.assert_not_called()


def test_radio_rejects_missing_group():
    page = MagicMock()

    group_locator = MagicMock()
    group_locator.count.return_value = 0

    page.locator.return_value = group_locator

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="radio group",
    ):
        writer.select_radio_option(
            make_radio_field(),
            "United States",
        )

    group_locator.check.assert_not_called()


def test_radio_rejects_ambiguous_matching_option():
    page = MagicMock()

    group_locator = MagicMock()
    group_locator.count.return_value = 2

    option_locator = MagicMock()
    option_locator.count.return_value = 2

    page.locator.side_effect = [
        group_locator,
        option_locator,
    ]

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one",
    ):
        writer.select_radio_option(
            make_radio_field(),
            "United States",
        )

    option_locator.check.assert_not_called()


@pytest.mark.parametrize(
    ("tag_name", "input_type"),
    [
        ("DIV", "radio"),
        ("INPUT", "checkbox"),
        ("BUTTON", "button"),
        ("SELECT", "select-one"),
    ],
)
def test_radio_rejects_non_native_radio_control(
    tag_name: str,
    input_type: str,
):
    page = MagicMock()

    group_locator = MagicMock()
    group_locator.count.return_value = 2

    option_locator = MagicMock()
    option_locator.count.return_value = 1
    option_locator.evaluate.return_value = {
        "tagName": tag_name,
        "type": input_type,
    }

    page.locator.side_effect = [
        group_locator,
        option_locator,
    ]

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not a native HTML radio input",
    ):
        writer.select_radio_option(
            make_radio_field(),
            "United States",
        )

    option_locator.check.assert_not_called()


def test_radio_rejects_unverifiable_dom_control():
    page = MagicMock()

    group_locator = MagicMock()
    group_locator.count.return_value = 2

    option_locator = MagicMock()
    option_locator.count.return_value = 1
    option_locator.evaluate.return_value = None

    page.locator.side_effect = [
        group_locator,
        option_locator,
    ]

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be safely verified",
    ):
        writer.select_radio_option(
            make_radio_field(),
            "United States",
        )

    option_locator.check.assert_not_called()

def test_native_checkbox_checks_when_currently_unchecked():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "checkbox",
    }
    locator.is_checked.return_value = False
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    writer.set_checkbox_state(
        field=field,
        checked=True,
    )

    page.locator.assert_called_once_with(
        '[id="preferred_name"]'
    )

    locator.is_checked.assert_called_once_with()
    locator.check.assert_called_once_with()

    locator.uncheck.assert_not_called()
    locator.click.assert_not_called()
    locator.fill.assert_not_called()
    locator.select_option.assert_not_called()


def test_native_checkbox_unchecks_when_currently_checked():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "checkbox",
    }
    locator.is_checked.return_value = True
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="phone_contact",
        label="Use my verified phone number for application contact.",
        field_type=FormFieldType.CHECKBOX,
    )

    writer.set_checkbox_state(
        field=field,
        checked=False,
    )

    locator.is_checked.assert_called_once_with()
    locator.uncheck.assert_called_once_with()

    locator.check.assert_not_called()
    locator.click.assert_not_called()
    locator.fill.assert_not_called()
    locator.select_option.assert_not_called()


@pytest.mark.parametrize(
    ("current_checked", "desired_checked"),
    [
        (False, False),
        (True, True),
    ],
)
def test_checkbox_is_noop_when_already_in_desired_state(
    current_checked: bool,
    desired_checked: bool,
):
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "checkbox",
    }
    locator.is_checked.return_value = current_checked
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    writer.set_checkbox_state(
        field=field,
        checked=desired_checked,
    )

    locator.is_checked.assert_called_once_with()

    locator.check.assert_not_called()
    locator.uncheck.assert_not_called()
    locator.click.assert_not_called()


def test_checkbox_rejects_non_checkbox_field_without_dom_mutation():
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not supported",
    ):
        writer.set_checkbox_state(
            field=make_field(
                field_type=FormFieldType.TEXT,
            ),
            checked=True,
        )

    page.locator.assert_not_called()


@pytest.mark.parametrize(
    "checked",
    [
        None,
        "true",
        "false",
        1,
        0,
    ],
)
def test_checkbox_rejects_non_boolean_desired_state(
    checked,
):
    page = MagicMock()
    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="boolean",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=checked,
        )

    page.locator.assert_not_called()


def test_checkbox_missing_locator_is_rejected():
    page, id_locator, name_locator = (
        make_page_with_locator_counts(
            id_count=0,
            name_count=0,
        )
    )

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be resolved",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=True,
        )

    id_locator.check.assert_not_called()
    id_locator.uncheck.assert_not_called()
    name_locator.check.assert_not_called()
    name_locator.uncheck.assert_not_called()


def test_checkbox_duplicate_id_is_rejected():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 2
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="multiple controls by id",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=True,
        )

    locator.check.assert_not_called()
    locator.uncheck.assert_not_called()
    locator.click.assert_not_called()


def test_checkbox_duplicate_name_is_rejected():
    page, id_locator, name_locator = (
        make_page_with_locator_counts(
            id_count=0,
            name_count=2,
        )
    )

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="multiple controls by name",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=True,
        )

    id_locator.check.assert_not_called()
    name_locator.check.assert_not_called()
    name_locator.uncheck.assert_not_called()


@pytest.mark.parametrize(
    ("tag_name", "input_type"),
    [
        ("DIV", "checkbox"),
        ("BUTTON", "checkbox"),
        ("INPUT", "radio"),
        ("INPUT", "text"),
        ("SELECT", "select-one"),
    ],
)
def test_checkbox_rejects_non_native_checkbox_controls(
    tag_name: str,
    input_type: str,
):
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": tag_name,
        "type": input_type,
    }
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="not a native HTML checkbox input",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=True,
        )

    locator.is_checked.assert_not_called()
    locator.check.assert_not_called()
    locator.uncheck.assert_not_called()
    locator.click.assert_not_called()


def test_checkbox_rejects_unverifiable_dom_control():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = None
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be safely verified",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=True,
        )

    locator.is_checked.assert_not_called()
    locator.check.assert_not_called()
    locator.uncheck.assert_not_called()


def test_checkbox_rejects_dom_inspection_failure():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.side_effect = RuntimeError(
        "DOM inspection failed"
    )
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="could not be safely verified",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=True,
        )

    locator.is_checked.assert_not_called()
    locator.check.assert_not_called()
    locator.uncheck.assert_not_called()


def test_checkbox_rejects_non_boolean_browser_state():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "checkbox",
    }
    locator.is_checked.return_value = "false"
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="state could not be safely verified",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=True,
        )

    locator.check.assert_not_called()
    locator.uncheck.assert_not_called()
    locator.click.assert_not_called()


def test_checkbox_rejects_browser_state_inspection_failure():
    page = MagicMock()

    locator = MagicMock()
    locator.count.return_value = 1
    locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "checkbox",
    }
    locator.is_checked.side_effect = RuntimeError(
        "State inspection failed"
    )
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    field = make_field(
        field_id="preferred_name",
        label="Use my verified preferred name on this application.",
        field_type=FormFieldType.CHECKBOX,
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="state could not be safely verified",
    ):
        writer.set_checkbox_state(
            field=field,
            checked=True,
        )

    locator.check.assert_not_called()
    locator.uncheck.assert_not_called()
    locator.click.assert_not_called()

def test_select_radio_option_uses_inspected_native_value_mapping() -> None:
    page = MagicMock()
    group_locator = MagicMock()
    option_locator = MagicMock()

    page.locator.side_effect = (
        lambda selector: (
            group_locator
            if selector == '[name="work_location"]'
            else option_locator
        )
    )

    group_locator.count.return_value = 2
    option_locator.count.return_value = 1
    option_locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "radio",
    }

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
                value="internal-101",
            ),
            FormFieldOption(
                label="Hybrid",
                value="internal-102",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    writer.select_radio_option(
        field,
        "Remote",
    )

    page.locator.assert_any_call(
        '[name="work_location"]'
        '[value="internal-101"]'
    )

    option_locator.check.assert_called_once_with()

def test_select_radio_option_blocks_without_native_value_mapping() -> None:
    page = MagicMock()

    field = FormField(
        field_id="work_location",
        label="Work location",
        field_type=FormFieldType.RADIO,
        options=[
            "Remote",
            "Hybrid",
        ],
        option_details=[],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="native value",
    ):
        writer.select_radio_option(
            field,
            "Remote",
        )

    page.locator.assert_not_called()

def test_select_radio_option_blocks_ambiguous_native_value_mapping() -> None:
    page = MagicMock()

    field = FormField(
        field_id="work_location",
        label="Work location",
        field_type=FormFieldType.RADIO,
        options=[
            "Remote",
        ],
        option_details=[
            FormFieldOption(
                label="Remote",
                value="internal-101",
            ),
            FormFieldOption(
                label="Remote",
                value="internal-999",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one native value",
    ):
        writer.select_radio_option(
            field,
            "Remote",
        )

    page.locator.assert_not_called()

def test_radio_rejects_duplicate_semantic_label_mappings() -> None:
    page = MagicMock()

    field = FormField(
        field_id="work_location",
        label="Work location",
        field_type=FormFieldType.RADIO,
        options=["Remote"],
        option_details=[
            FormFieldOption(
                label="Remote",
                value="internal-101",
            ),
            FormFieldOption(
                label="Remote",
                value="internal-102",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one native value",
    ):
        writer.select_radio_option(
            field,
            "Remote",
        )

    page.locator.assert_not_called()


def test_radio_rejects_missing_mapping_for_requested_option() -> None:
    page = MagicMock()

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
                label="Hybrid",
                value="internal-102",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="no inspected native value mapping",
    ):
        writer.select_radio_option(
            field,
            "Remote",
        )

    page.locator.assert_not_called()


def test_radio_rejects_semantic_value_not_in_inspected_options() -> None:
    page = MagicMock()

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
                value="internal-101",
            ),
            FormFieldOption(
                label="Hybrid",
                value="internal-102",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected option",
    ):
        writer.select_radio_option(
            field,
            "On-site",
        )

    page.locator.assert_not_called()


def test_radio_rejects_stale_native_value_without_mutation() -> None:
    page = MagicMock()

    group_locator = MagicMock()
    group_locator.count.return_value = 2

    stale_option_locator = MagicMock()
    stale_option_locator.count.return_value = 0

    page.locator.side_effect = [
        group_locator,
        stale_option_locator,
    ]

    field = FormField(
        field_id="work_location",
        label="Work location",
        field_type=FormFieldType.RADIO,
        options=["Remote"],
        option_details=[
            FormFieldOption(
                label="Remote",
                value="internal-101",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one browser control",
    ):
        writer.select_radio_option(
            field,
            "Remote",
        )

    stale_option_locator.check.assert_not_called()


def test_radio_uses_exact_case_sensitive_semantic_matching() -> None:
    page = MagicMock()

    field = FormField(
        field_id="work_location",
        label="Work location",
        field_type=FormFieldType.RADIO,
        options=["Remote"],
        option_details=[
            FormFieldOption(
                label="Remote",
                value="internal-101",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected option",
    ):
        writer.select_radio_option(
            field,
            "remote",
        )

    page.locator.assert_not_called()

def test_custom_combobox_cannot_use_native_select_execution() -> None:
    page = MagicMock()

    writer = PlaywrightFieldWriter(page)

    field = FormField(
        field_id="question_123",
        label="Preferred location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.CUSTOM_COMBOBOX,
        options=["Seattle"],
    )

    try:
        writer.select_option(
            field=field,
            value="Seattle",
        )
    except PlaywrightFieldWriterError as exc:
        assert "native select" in str(exc).lower()
    else:
        raise AssertionError(
            "Expected custom combobox execution to be rejected."
        )

    page.locator.assert_not_called()

def test_native_select_uses_inspected_native_value_mapping() -> None:
    page = MagicMock()
    locator = MagicMock()

    page.locator.return_value = locator
    locator.count.return_value = 1
    locator.evaluate.return_value = "SELECT"

    option_locator = MagicMock()
    option_locator.count.return_value = 1
    locator.locator.return_value = option_locator

    writer = PlaywrightFieldWriter(page)

    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.NATIVE_SELECT,
        options=[
            "Seattle",
            "New York",
        ],
        option_details=[
            FormFieldOption(
                label="Seattle",
                value="internal-101",
            ),
            FormFieldOption(
                label="New York",
                value="internal-102",
            ),
        ],
    )

    writer.select_option(
        field=field,
        value="Seattle",
    )

    locator.select_option.assert_called_once_with(
        value="internal-101"
    )

def test_native_select_rejects_missing_native_value_mapping() -> None:
    page = MagicMock()

    writer = PlaywrightFieldWriter(page)

    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.NATIVE_SELECT,
        options=["Seattle"],
        option_details=[],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected native-value mapping",
    ):
        writer.select_option(
            field=field,
            value="Seattle",
        )

    page.locator.assert_not_called()


def test_native_select_rejects_ambiguous_native_value_mapping() -> None:
    page = MagicMock()

    writer = PlaywrightFieldWriter(page)

    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.NATIVE_SELECT,
        options=["Seattle"],
        option_details=[
            FormFieldOption(
                label="Seattle",
                value="internal-101",
            ),
            FormFieldOption(
                label="Seattle",
                value="internal-999",
            ),
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected native-value mapping",
    ):
        writer.select_option(
            field=field,
            value="Seattle",
        )

    page.locator.assert_not_called()


def test_native_select_semantic_matching_is_case_sensitive() -> None:
    page = MagicMock()

    writer = PlaywrightFieldWriter(page)

    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.NATIVE_SELECT,
        options=["Seattle"],
        option_details=[
            FormFieldOption(
                label="Seattle",
                value="internal-101",
            ),
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected option",
    ):
        writer.select_option(
            field=field,
            value="seattle",
        )

    page.locator.assert_not_called()


def test_native_select_rejects_duplicate_semantic_options() -> None:
    page = MagicMock()

    writer = PlaywrightFieldWriter(page)

    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.NATIVE_SELECT,
        options=[
            "Seattle",
            "Seattle",
        ],
        option_details=[
            FormFieldOption(
                label="Seattle",
                value="internal-101",
            ),
        ],
    )

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="exactly one inspected option",
    ):
        writer.select_option(
            field=field,
            value="Seattle",
        )

    page.locator.assert_not_called()

def test_native_select_rejects_stale_native_value_without_mutation() -> None:
    page = MagicMock()

    select_locator = MagicMock()
    select_locator.count.return_value = 1
    select_locator.evaluate.return_value = "SELECT"

    option_locator = MagicMock()
    option_locator.count.return_value = 0

    page.locator.return_value = select_locator
    select_locator.locator.return_value = option_locator

    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.NATIVE_SELECT,
        options=["Seattle"],
        option_details=[
            FormFieldOption(
                label="Seattle",
                value="internal-101",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="native value did not resolve to exactly one option",
    ):
        writer.select_option(
            field=field,
            value="Seattle",
        )

    select_locator.locator.assert_called_once_with(
        'option[value="internal-101"]'
    )

    select_locator.select_option.assert_not_called()

def test_native_select_rejects_ambiguous_native_value_without_mutation() -> None:
    page = MagicMock()

    select_locator = MagicMock()
    select_locator.count.return_value = 1
    select_locator.evaluate.return_value = "SELECT"

    option_locator = MagicMock()
    option_locator.count.return_value = 2

    page.locator.return_value = select_locator
    select_locator.locator.return_value = option_locator

    field = FormField(
        field_id="location",
        label="Location",
        field_type=FormFieldType.SELECT,
        control_kind=FormControlKind.NATIVE_SELECT,
        options=["Seattle"],
        option_details=[
            FormFieldOption(
                label="Seattle",
                value="internal-101",
            ),
        ],
    )

    writer = PlaywrightFieldWriter(page)

    with pytest.raises(
        PlaywrightFieldWriterError,
        match="native value did not resolve to exactly one option",
    ):
        writer.select_option(
            field=field,
            value="Seattle",
        )

    select_locator.select_option.assert_not_called()
