from __future__ import annotations

from enum import Enum
from typing import Any


class FitTier(str, Enum):
    """
    Policy tier produced from a numeric job-fit score.
    """

    LOW = "LOW"
    REVIEW = "REVIEW"
    HIGH = "HIGH"


class FitGate:
    """
    Deterministic policy for converting a fit score into a routing tier.

    FitGate does not modify Job objects or application state. It only
    interprets an already-computed score using configured thresholds.
    """

    def __init__(
        self,
        role_config: dict[str, Any],
    ) -> None:
        if not isinstance(role_config, dict):
            raise ValueError(
                "Role configuration must be a dictionary."
            )

        fit_scoring = role_config.get("fit_scoring")

        if not isinstance(fit_scoring, dict):
            raise ValueError(
                "roles.yaml must contain a 'fit_scoring' dictionary."
            )

        self.auto_ready_minimum = self._validate_threshold(
            fit_scoring.get("auto_ready_minimum"),
            "auto_ready_minimum",
        )

        self.manual_review_minimum = self._validate_threshold(
            fit_scoring.get("manual_review_minimum"),
            "manual_review_minimum",
        )

        if self.manual_review_minimum > self.auto_ready_minimum:
            raise ValueError(
                "manual_review_minimum must be less than or equal "
                "to auto_ready_minimum."
            )

    @staticmethod
    def _validate_threshold(
        value: Any,
        name: str,
    ) -> float:
        if isinstance(value, bool) or not isinstance(
            value,
            (int, float),
        ):
            raise ValueError(
                f"fit_scoring.{name} must be a number."
            )

        threshold = float(value)

        if not 0.0 <= threshold <= 100.0:
            raise ValueError(
                f"fit_scoring.{name} must be between 0 and 100."
            )

        return threshold

    def evaluate(
        self,
        score: float,
    ) -> FitTier:
        """
        Convert a numeric fit score into LOW, REVIEW, or HIGH.
        """

        if isinstance(score, bool) or not isinstance(
            score,
            (int, float),
        ):
            raise ValueError(
                "Fit score must be a number."
            )

        numeric_score = float(score)

        if not 0.0 <= numeric_score <= 100.0:
            raise ValueError(
                "Fit score must be between 0 and 100."
            )

        if numeric_score >= self.auto_ready_minimum:
            return FitTier.HIGH

        if numeric_score >= self.manual_review_minimum:
            return FitTier.REVIEW

        return FitTier.LOW