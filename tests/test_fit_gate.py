import pytest

from app.scoring.fit_gate import (
    FitGate,
    FitTier,
)


@pytest.fixture
def role_config():
    return {
        "fit_scoring": {
            "auto_ready_minimum": 70,
            "manual_review_minimum": 50,
        }
    }


@pytest.fixture
def gate(role_config):
    return FitGate(role_config)


def test_score_above_auto_ready_threshold_is_high(gate):
    assert gate.evaluate(85) == FitTier.HIGH


def test_score_at_auto_ready_threshold_is_high(gate):
    assert gate.evaluate(70) == FitTier.HIGH


def test_score_just_below_auto_ready_threshold_is_review(gate):
    assert gate.evaluate(69.99) == FitTier.REVIEW


def test_score_in_review_range_is_review(gate):
    assert gate.evaluate(60) == FitTier.REVIEW


def test_score_at_manual_review_threshold_is_review(gate):
    assert gate.evaluate(50) == FitTier.REVIEW


def test_score_just_below_manual_review_threshold_is_low(gate):
    assert gate.evaluate(49.99) == FitTier.LOW


def test_zero_score_is_low(gate):
    assert gate.evaluate(0) == FitTier.LOW


def test_score_of_100_is_high(gate):
    assert gate.evaluate(100) == FitTier.HIGH


def test_custom_thresholds_are_respected():
    gate = FitGate(
        {
            "fit_scoring": {
                "auto_ready_minimum": 80,
                "manual_review_minimum": 60,
            }
        }
    )

    assert gate.evaluate(79) == FitTier.REVIEW
    assert gate.evaluate(59) == FitTier.LOW
    assert gate.evaluate(80) == FitTier.HIGH


def test_missing_fit_scoring_config_is_rejected():
    with pytest.raises(ValueError):
        FitGate({})


def test_missing_auto_ready_threshold_is_rejected():
    with pytest.raises(ValueError):
        FitGate(
            {
                "fit_scoring": {
                    "manual_review_minimum": 50,
                }
            }
        )


def test_missing_manual_review_threshold_is_rejected():
    with pytest.raises(ValueError):
        FitGate(
            {
                "fit_scoring": {
                    "auto_ready_minimum": 70,
                }
            }
        )


def test_review_threshold_cannot_exceed_auto_threshold():
    with pytest.raises(ValueError):
        FitGate(
            {
                "fit_scoring": {
                    "auto_ready_minimum": 50,
                    "manual_review_minimum": 70,
                }
            }
        )


@pytest.mark.parametrize(
    "threshold",
    [
        -1,
        101,
    ],
)
def test_auto_ready_threshold_must_be_between_zero_and_100(
    threshold,
):
    with pytest.raises(ValueError):
        FitGate(
            {
                "fit_scoring": {
                    "auto_ready_minimum": threshold,
                    "manual_review_minimum": 50,
                }
            }
        )


@pytest.mark.parametrize(
    "threshold",
    [
        -1,
        101,
    ],
)
def test_manual_review_threshold_must_be_between_zero_and_100(
    threshold,
):
    with pytest.raises(ValueError):
        FitGate(
            {
                "fit_scoring": {
                    "auto_ready_minimum": 70,
                    "manual_review_minimum": threshold,
                }
            }
        )


@pytest.mark.parametrize(
    "score",
    [
        -0.01,
        100.01,
    ],
)
def test_fit_score_must_be_between_zero_and_100(
    gate,
    score,
):
    with pytest.raises(ValueError):
        gate.evaluate(score)


@pytest.mark.parametrize(
    "score",
    [
        None,
        "70",
        True,
    ],
)
def test_non_numeric_fit_score_is_rejected(
    gate,
    score,
):
    with pytest.raises(ValueError):
        gate.evaluate(score)