from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


class ConfigError(Exception):
    """Raised when application configuration cannot be loaded."""


def load_yaml_config(filename: str) -> dict[str, Any]:
    """
    Load a YAML configuration file from the config directory.
    """

    path = CONFIG_DIR / filename

    if not path.exists():
        raise ConfigError(
            f"Configuration file does not exist: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = yaml.safe_load(file)

    except yaml.YAMLError as exc:
        raise ConfigError(
            f"Invalid YAML in {path}: {exc}"
        ) from exc

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ConfigError(
            f"Expected YAML object in {path}."
        )

    return data


def load_candidate_config() -> dict[str, Any]:
    return load_yaml_config("candidate.yaml")


def load_company_rules() -> dict[str, Any]:
    return load_yaml_config("company_rules.yaml")


def load_role_config() -> dict[str, Any]:
    return load_yaml_config("roles.yaml")


def load_application_answers() -> dict[str, Any]:
    return load_yaml_config("application_answers.yaml")