from pathlib import Path

import pytest
import yaml

from app.utils import config


def test_load_valid_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    test_file = config_dir / "test.yaml"

    test_file.write_text(
        "name: Job Application Agent\n"
        "enabled: true\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        config,
        "CONFIG_DIR",
        config_dir,
    )

    result = config.load_yaml_config(
        "test.yaml"
    )

    assert result["name"] == (
        "Job Application Agent"
    )

    assert result["enabled"] is True


def test_missing_config_raises_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "CONFIG_DIR",
        tmp_path,
    )

    with pytest.raises(config.ConfigError):
        config.load_yaml_config(
            "missing.yaml"
        )


def test_invalid_yaml_raises_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_file = tmp_path / "invalid.yaml"

    test_file.write_text(
        "invalid: [yaml",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        config,
        "CONFIG_DIR",
        tmp_path,
    )

    with pytest.raises(config.ConfigError):
        config.load_yaml_config(
            "invalid.yaml"
        )


def test_empty_yaml_returns_dictionary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_file = tmp_path / "empty.yaml"

    test_file.write_text(
        "",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        config,
        "CONFIG_DIR",
        tmp_path,
    )

    result = config.load_yaml_config(
        "empty.yaml"
    )

    assert result == {}