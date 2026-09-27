from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ApplicationAnswerConfigError(ValueError):
    """Raised when application-answer configuration is invalid."""


class ApplicationAnswerLoader:
    """
    Loads verified candidate answers from a private YAML file.

    Only explicitly approved ordinary profile fields may enter
    the automatic-answer system.
    """

    ALLOWED_FIELDS = frozenset(
        {
            "first_name",
            "last_name",
            "full_name",
            "preferred_name",
            "email",
            "phone",
            "linkedin",
            "github",
            "portfolio",
            "website",
            "address",
            "city",
            "state",
            "postal_code",
            "country",
        }
    )

    FORBIDDEN_FIELDS = frozenset(
        {
            "work_authorization",
            "employment_authorization",
            "visa",
            "visa_status",
            "immigration_status",
            "sponsorship",
            "requires_sponsorship",
            "citizenship",
            "permanent_resident",
            "green_card",
            "race",
            "ethnicity",
            "gender",
            "sex",
            "sexual_orientation",
            "disability",
            "veteran_status",
            "military_status",
            "criminal_history",
            "background_check",
            "conflict_of_interest",
            "signature",
            "attestation",
        }
    )

    def load(
        self,
        path: str | Path,
    ) -> dict[str, str]:
        config_path = Path(path)

        if not config_path.is_file():
            raise FileNotFoundError(
                f"Application answer configuration does not exist: "
                f"{config_path}"
            )

        try:
            with config_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = yaml.safe_load(file)
        except yaml.YAMLError as exc:
            raise ApplicationAnswerConfigError(
                "Application answer configuration contains "
                "invalid YAML."
            ) from exc

        return self._validate(data)

    def _validate(
        self,
        data: Any,
    ) -> dict[str, str]:
        if data is None:
            return {}

        if not isinstance(data, dict):
            raise ApplicationAnswerConfigError(
                "Application answer configuration must be "
                "a mapping."
            )

        validated: dict[str, str] = {}

        for raw_key, raw_value in data.items():
            if not isinstance(raw_key, str):
                raise ApplicationAnswerConfigError(
                    "Application answer field names must "
                    "be strings."
                )

            key = raw_key.strip()

            if not key:
                raise ApplicationAnswerConfigError(
                    "Application answer field names must "
                    "not be empty."
                )

            if key in self.FORBIDDEN_FIELDS:
                raise ApplicationAnswerConfigError(
                    f"Sensitive or manual field '{key}' cannot "
                    f"be stored in the automatic answer config."
                )

            if key not in self.ALLOWED_FIELDS:
                raise ApplicationAnswerConfigError(
                    f"Unknown application answer field: '{key}'."
                )

            if not isinstance(raw_value, str):
                raise ApplicationAnswerConfigError(
                    f"Application answer '{key}' must be "
                    f"a string."
                )

            value = raw_value.strip()

            if not value:
                raise ApplicationAnswerConfigError(
                    f"Application answer '{key}' must not "
                    f"be empty."
                )

            validated[key] = value

        return validated