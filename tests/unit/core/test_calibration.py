from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.core.calibration import (
    CalibrationService,
    _actual_value,
    build_calibration_buckets,
    calculate_brier_score,
    get_probability_band,
    get_risk_level,
    normalize_utc,
)
from src.core.trend_engine import prob_to_logodds
from src.storage.models import OutcomeType, RiskLevel, Trend, TrendOutcome, TrendSnapshot

pytestmark = pytest.mark.unit


class _ScalarResult:
    def __init__(self, values: list[TrendOutcome]):
        self._values = values

    def all(self) -> list[TrendOutcome]:
        return self._values


def _build_outcome(
    *,
    probability: float,
    outcome: OutcomeType | str | None,
    brier_score: float | None = None,
) -> TrendOutcome:
    return TrendOutcome(
        trend_id=uuid4(),
        prediction_date=datetime.now(tz=UTC),
        predicted_probability=probability,
        predicted_risk_level="elevated",
        probability_band_low=max(0.001, probability - 0.1),
        probability_band_high=min(0.999, probability + 0.1),
        outcome_date=datetime.now(tz=UTC),
        outcome=outcome.value if isinstance(outcome, OutcomeType) else outcome,
        brier_score=brier_score,
    )


def _build_trend(*, probability: float) -> Trend:
    log_odds = prob_to_logodds(probability)
    return Trend(
        id=uuid4(),
        name="Trend",
        description="desc",
        runtime_trend_id="trend",
        definition={"baseline_probability": probability},
        baseline_log_odds=log_odds,
        current_log_odds=log_odds,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )


def test_normalize_utc_makes_naive_datetime_utc_aware() -> None:
    value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC).replace(tzinfo=None)

    normalized = normalize_utc(value)

    assert normalized.tzinfo is UTC
    assert normalized.hour == 3


def test_normalize_utc_converts_aware_datetime() -> None:
    value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2)))

    normalized = normalize_utc(value)

    assert normalized == datetime(2026, 1, 2, 1, 4, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.00, RiskLevel.LOW),
        (0.10, RiskLevel.GUARDED),
        (0.25, RiskLevel.ELEVATED),
        (0.50, RiskLevel.HIGH),
        (0.75, RiskLevel.SEVERE),
    ],
)
def test_get_risk_level_uses_expected_bands(
    probability: float,
    expected: RiskLevel,
) -> None:
    assert get_risk_level(probability) == expected


def test_get_probability_band_clamps_to_supported_range() -> None:
    assert get_probability_band(0.05) == pytest.approx((0.001, 0.15))
    assert get_probability_band(0.95) == pytest.approx((0.85, 0.999))


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (OutcomeType.OCCURRED, 1.0),
        (OutcomeType.DID_NOT_OCCUR, 0.0),
        (OutcomeType.PARTIAL, 0.5),
        (OutcomeType.ONGOING, None),
    ],
)
def test_actual_value_maps_only_scored_outcomes(
    outcome: OutcomeType,
    expected: float | None,
) -> None:
    assert _actual_value(outcome) == expected


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


def test_build_calibration_buckets_rejects_invalid_bucket_count() -> None:
    with pytest.raises(ValueError, match="bucket_count must be >= 1"):
        build_calibration_buckets([], bucket_count=0)


def test_build_calibration_buckets_skips_unscored_invalid_and_clamps_probability() -> None:
    outcomes = [
        _build_outcome(probability=1.2, outcome=OutcomeType.OCCURRED),
        _build_outcome(probability=0.05, outcome=OutcomeType.ONGOING),
        _build_outcome(probability=0.15, outcome="bogus"),
        _build_outcome(probability=0.35, outcome=None),
    ]

    buckets = build_calibration_buckets(outcomes, bucket_count=5)

    assert len(buckets) == 1
    assert buckets[0].bucket_start == pytest.approx(0.8)
    assert buckets[0].bucket_end == pytest.approx(1.0)
    assert buckets[0].prediction_count == 1
    assert buckets[0].occurred_count == 1
    assert buckets[0].actual_rate == pytest.approx(1.0)


async def test_record_outcome_rejects_unknown_trend(mock_db_session) -> None:
    service = CalibrationService(mock_db_session)
    trend_id = uuid4()

    mock_db_session.get.return_value = None

    with pytest.raises(ValueError, match=str(trend_id)):
        await service.record_outcome(
            trend_id=trend_id,
            outcome=OutcomeType.OCCURRED,
            outcome_date=datetime.now(tz=UTC),
        )


async def test_record_outcome_uses_latest_snapshot_probability(mock_db_session) -> None:
    service = CalibrationService(mock_db_session)
    trend = _build_trend(probability=0.2)
    snapshot = TrendSnapshot(
        trend_id=trend.id,
        timestamp=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        log_odds=prob_to_logodds(0.8),
        event_count_24h=3,
    )
    outcome_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=2)))

    mock_db_session.get.return_value = trend
    mock_db_session.scalar.return_value = snapshot

    record = await service.record_outcome(
        trend_id=trend.id,
        outcome=OutcomeType.PARTIAL,
        outcome_date=outcome_date,
        notes="needs nuance",
        evidence={"source": "snapshot"},
        recorded_by="tester",
    )

    added = mock_db_session.add.call_args[0][0]
    assert record is added
    assert float(record.predicted_probability) == pytest.approx(0.8, rel=1e-3)
    assert record.predicted_risk_level == RiskLevel.SEVERE.value
    assert float(record.probability_band_low) == pytest.approx(0.7, rel=1e-3)
    assert float(record.probability_band_high) == pytest.approx(0.9, rel=1e-3)
    assert float(record.brier_score) == pytest.approx(0.09, rel=1e-3)
    assert record.prediction_date == datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    assert record.outcome_notes == "needs nuance"
    assert record.outcome_evidence == {"source": "snapshot"}
    assert record.recorded_by == "tester"
    mock_db_session.flush.assert_awaited_once()


async def test_record_outcome_falls_back_to_current_trend_probability(mock_db_session) -> None:
    service = CalibrationService(mock_db_session)
    trend = _build_trend(probability=0.35)

    mock_db_session.get.return_value = trend
    mock_db_session.scalar.return_value = None

    record = await service.record_outcome(
        trend_id=trend.id,
        outcome=OutcomeType.DID_NOT_OCCUR,
        outcome_date=datetime(2026, 1, 2, 0, 0, tzinfo=UTC).replace(tzinfo=None),
    )

    assert float(record.predicted_probability) == pytest.approx(0.35, rel=1e-3)
    assert record.prediction_date.tzinfo is UTC
    assert record.predicted_risk_level == RiskLevel.ELEVATED.value
    assert float(record.brier_score) == pytest.approx(0.1225, rel=1e-3)


async def test_get_calibration_report_computes_brier_and_bias_flags(mock_db_session) -> None:
    service = CalibrationService(mock_db_session)
    trend_id = uuid4()
    outcomes = [
        _build_outcome(probability=0.9, outcome=OutcomeType.DID_NOT_OCCUR, brier_score=None),
        _build_outcome(probability=0.8, outcome=OutcomeType.DID_NOT_OCCUR, brier_score=0.64),
        _build_outcome(probability=0.2, outcome=OutcomeType.ONGOING, brier_score=None),
        _build_outcome(probability=0.3, outcome="invalid", brier_score=None),
        _build_outcome(probability=0.4, outcome=None, brier_score=None),
    ]
    for outcome in outcomes:
        outcome.trend_id = trend_id
    mock_db_session.scalars.return_value = _ScalarResult(outcomes)

    report = await service.get_calibration_report(
        trend_id=trend_id,
        start_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC).replace(tzinfo=None),
        end_date=datetime(2026, 1, 10, 12, 0, tzinfo=timezone(timedelta(hours=2))),
    )

    assert report.total_predictions == 5
    assert report.resolved_predictions == 2
    assert report.mean_brier_score == pytest.approx((0.81 + 0.64) / 2)
    assert len(report.buckets) == 2
    assert report.overconfident is True
    assert report.underconfident is False
    mock_db_session.scalars.assert_awaited_once()


async def test_get_calibration_report_marks_underconfidence_when_actuals_exceed_predictions(
    mock_db_session,
) -> None:
    service = CalibrationService(mock_db_session)
    trend_id = uuid4()
    outcomes = [
        _build_outcome(probability=0.1, outcome=OutcomeType.OCCURRED, brier_score=0.81),
        _build_outcome(probability=0.2, outcome=OutcomeType.OCCURRED, brier_score=0.64),
    ]
    for outcome in outcomes:
        outcome.trend_id = trend_id
    mock_db_session.scalars.return_value = _ScalarResult(outcomes)

    report = await service.get_calibration_report(trend_id=trend_id)

    assert report.total_predictions == 2
    assert report.resolved_predictions == 2
    assert report.mean_brier_score == pytest.approx(0.725)
    assert report.overconfident is False
    assert report.underconfident is True


@pytest.mark.asyncio
async def test_get_calibration_report_skips_none_scores_and_snapshot_fallbacks(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CalibrationService(mock_db_session)
    trend_id = uuid4()
    outcomes = [
        _build_outcome(probability=0.4, outcome=OutcomeType.OCCURRED, brier_score=None),
        _build_outcome(probability=0.2, outcome=OutcomeType.DID_NOT_OCCUR, brier_score=0.04),
    ]
    for outcome in outcomes:
        outcome.trend_id = trend_id
    mock_db_session.scalars.return_value = _ScalarResult(outcomes)

    monkeypatch.setattr(
        "src.core.calibration.calculate_brier_score",
        lambda predicted_probability, _outcome: None if predicted_probability == 0.4 else 0.0,
    )
    report = await service.get_calibration_report(trend_id=trend_id)

    assert report.total_predictions == 2
    assert report.resolved_predictions == 2
    assert report.mean_brier_score == pytest.approx(0.04)
    assert report.overconfident is False
    assert report.underconfident is True

    trend = _build_trend(probability=0.35)
    mock_db_session.scalar.return_value = None
    assert await service._get_predicted_probability(trend, datetime.now(tz=UTC)) == pytest.approx(
        0.35
    )

    snapshot = TrendSnapshot(
        trend_id=trend.id,
        timestamp=datetime.now(tz=UTC),
        log_odds=prob_to_logodds(0.8),
        event_count_24h=3,
    )
    mock_db_session.scalar.return_value = snapshot
    assert await service._get_predicted_probability(trend, datetime.now(tz=UTC)) == pytest.approx(
        0.8
    )


@pytest.mark.asyncio
async def test_get_calibration_report_skips_none_actual_in_signed_error_loop(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CalibrationService(mock_db_session)
    trend_id = uuid4()
    outcome = _build_outcome(probability=0.4, outcome=OutcomeType.OCCURRED, brier_score=0.36)
    outcome.trend_id = trend_id
    mock_db_session.scalars.return_value = _ScalarResult([outcome])

    calls = {"count": 0}

    def fake_actual_value(_outcome_type: OutcomeType) -> float | None:
        calls["count"] += 1
        if calls["count"] >= 3:
            return None
        return 1.0

    monkeypatch.setattr("src.core.calibration._actual_value", fake_actual_value)

    report = await service.get_calibration_report(trend_id=trend_id)

    assert report.total_predictions == 1
    assert report.resolved_predictions == 1
    assert report.mean_brier_score == pytest.approx(0.36)
    assert report.overconfident is False
    assert report.underconfident is False
