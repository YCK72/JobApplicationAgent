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