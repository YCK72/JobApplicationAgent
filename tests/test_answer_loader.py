from pathlib import Path

import pytest

from app.applications.answer_loader import (
    ApplicationAnswerConfigError,
    ApplicationAnswerLoader,
)


@pytest.fixture
def loader():
    return ApplicationAnswerLoader()


def write_yaml(
    tmp_path: Path,
    content: str,
) -> Path:
    path = tmp_path / "application_answers.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_allowed_verified_answers(
    loader,
    tmp_path,
):
    path = write_yaml(
        tmp_path,
        """
first_name: Test
last_name: Candidate
email: candidate@example.com
city: Example City
state: WA
""",
    )

    result = loader.load(path)

    assert result == {
        "first_name": "Test",
        "last_name": "Candidate",
        "email": "candidate@example.com",
        "city": "Example City",
        "state": "WA",
    }


def test_values_are_trimmed(
    loader,
    tmp_path,
):
    path = write_yaml(
        tmp_path,
        """
first_name: "  Test  "
email: "  candidate@example.com  "
""",
    )

    result = loader.load(path)

    assert result["first_name"] == "Test"
    assert result["email"] == "candidate@example.com"


def test_empty_yaml_returns_empty_mapping(
    loader,
    tmp_path,
):
    path = write_yaml(tmp_path, "")

    assert loader.load(path) == {}


def test_missing_file_is_rejected(
    loader,
    tmp_path,
):
    path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError):
        loader.load(path)


def test_list_root_is_rejected(
    loader,
    tmp_path,
):
    path = write_yaml(
        tmp_path,
        """
- first_name
- email
""",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        loader.load(path)


def test_unknown_field_is_rejected(
    loader,
    tmp_path,
):
    path = write_yaml(
        tmp_path,
        """
favorite_color: blue
""",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        loader.load(path)


@pytest.mark.parametrize(
    "field",
    [
        "work_authorization",
        "visa_status",
        "immigration_status",
        "sponsorship",
        "citizenship",
        "race",
        "ethnicity",
        "gender",
        "disability",
        "veteran_status",
        "criminal_history",
        "signature",
        "attestation",
    ],
)
def test_sensitive_and_manual_fields_are_rejected(
    loader,
    tmp_path,
    field,
):
    path = write_yaml(
        tmp_path,
        f"{field}: test-value\n",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        loader.load(path)


def test_non_string_value_is_rejected(
    loader,
    tmp_path,
):
    path = write_yaml(
        tmp_path,
        """
phone: 1234567890
""",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        loader.load(path)


def test_empty_value_is_rejected(
    loader,
    tmp_path,
):
    path = write_yaml(
        tmp_path,
        """
email: "   "
""",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        loader.load(path)


def test_invalid_yaml_is_rejected(
    loader,
    tmp_path,
):
    path = write_yaml(
        tmp_path,
        """
first_name: [
""",
    )

    with pytest.raises(ApplicationAnswerConfigError):
        loader.load(path)