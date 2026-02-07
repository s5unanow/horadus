from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.calibration import build_calibration_buckets, calculate_brier_score
from src.storage.models import OutcomeType, TrendOutcome

pytestmark = pytest.mark.unit


def _build_outcome(
    *,
    probability: float,
    outcome: OutcomeType,
) -> TrendOutcome:
    return TrendOutcome(
        trend_id=uuid4(),
        prediction_date=datetime.now(tz=UTC),
        predicted_probability=probability,
        predicted_risk_level="elevated",
        probability_band_low=max(0.001, probability - 0.1),
        probability_band_high=min(0.999, probability + 0.1),
        outcome_date=datetime.now(tz=UTC),
        outcome=outcome.value,
    )


def test_calculate_brier_score_perfect_prediction() -> None:
    score = calculate_brier_score(1.0, OutcomeType.OCCURRED)
    assert score == pytest.approx(0.0)


def test_calculate_brier_score_worst_prediction() -> None:
    score = calculate_brier_score(0.0, OutcomeType.OCCURRED)
    assert score == pytest.approx(1.0)


def test_calculate_brier_score_partial_outcome() -> None:
    score = calculate_brier_score(0.8, OutcomeType.PARTIAL)
    assert score == pytest.approx(0.09)


def test_calculate_brier_score_unscored_outcome() -> None:
    score = calculate_brier_score(0.8, OutcomeType.ONGOING)
    assert score is None


def test_build_calibration_buckets_groups_predictions() -> None:
    outcomes = [
        _build_outcome(probability=0.22, outcome=OutcomeType.DID_NOT_OCCUR),
        _build_outcome(probability=0.25, outcome=OutcomeType.OCCURRED),
        _build_outcome(probability=0.88, outcome=OutcomeType.OCCURRED),
    ]

    buckets = build_calibration_buckets(outcomes, bucket_count=10)

    assert len(buckets) == 2
    first_bucket = buckets[0]
    assert first_bucket.bucket_start == pytest.approx(0.2)
    assert first_bucket.bucket_end == pytest.approx(0.3)
    assert first_bucket.prediction_count == 2
    assert first_bucket.occurred_count == 1
    assert first_bucket.actual_rate == pytest.approx(0.5)
