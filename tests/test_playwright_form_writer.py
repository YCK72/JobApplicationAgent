from unittest.mock import MagicMock

import pytest

from app.applications.form_models import (
    FormField,
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
    return FormField(
        field_id=field_id,
        label=label,
        field_type=FormFieldType.SELECT,
        options=(
            options
            if options is not None
            else [
                "United States",
                "Canada",
            ]
        ),
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
        label="United States"
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
        label="United States"
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
    page.locator.return_value = locator

    writer = PlaywrightFieldWriter(page)

    writer.select_option(
        make_select_field(),
        "United States",
    )

    locator.select_option.assert_called_once_with(
        label="United States"
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