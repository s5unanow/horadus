from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.trend_state_presentation import (
    EvidenceWindowStats,
    TrendMomentumState,
    TrendUncertaintyLevel,
    TrendUncertaintyState,
    _momentum_direction,
    build_momentum_state,
    build_uncertainty_state,
    load_evidence_window_stats,
)

pytestmark = pytest.mark.unit


def test_build_uncertainty_state_stays_low_when_recent_evidence_is_dense() -> None:
    state = build_uncertainty_state(
        probability=0.42,
        evidence_stats=EvidenceWindowStats(
            evidence_count=30,
            avg_corroboration=0.85,
            days_since_last_evidence=0,
        ),
    )

    assert state.level == TrendUncertaintyLevel.LOW
    assert 0 <= state.score < 0.2
    assert state.band_width < 0.10


def test_build_uncertainty_state_marks_sparse_stale_coverage_as_high() -> None:
    state = build_uncertainty_state(
        probability=0.42,
        evidence_stats=EvidenceWindowStats(
            evidence_count=0,
            avg_corroboration=0.5,
            days_since_last_evidence=30,
        ),
    )

    assert state.level == TrendUncertaintyLevel.HIGH
    assert state.score > 0.7
    assert state.band_width > 0.4


def test_state_payload_to_dict_rounds_values_and_preserves_none() -> None:
    uncertainty = TrendUncertaintyState(
        score=0.1234567,
        level=TrendUncertaintyLevel.MEDIUM,
        band_width=0.2345678,
        evidence_count_30d=9,
        avg_corroboration_30d=0.7654321,
        days_since_last_evidence=2,
    )
    momentum = TrendMomentumState(
        direction="stable",
        window_days=7,
        delta_probability=0.0123456,
        previous_window_delta=None,
        acceleration=None,
        evidence_count_window=3,
    )

    assert uncertainty.to_dict() == {
        "score": 0.123457,
        "level": "medium",
        "band_width": 0.234568,
        "evidence_count_30d": 9,
        "avg_corroboration_30d": 0.765432,
        "days_since_last_evidence": 2,
    }
    assert momentum.to_dict() == {
        "direction": "stable",
        "window_days": 7,
        "delta_probability": 0.012346,
        "previous_window_delta": None,
        "acceleration": None,
        "evidence_count_window": 3,
    }


@pytest.mark.parametrize(
    ("delta_probability", "expected"),
    [(0.02, "rising"), (-0.02, "falling"), (-0.07, "falling_fast"), (0.0, "stable")],
)
def test_momentum_direction_branches_cover_intermediate_cases(
    delta_probability: float,
    expected: str,
) -> None:
    assert _momentum_direction(delta_probability) == expected


@pytest.mark.asyncio
async def test_load_evidence_window_stats_uses_safe_defaults_without_recent_rows(
    mock_db_session,
) -> None:
    mock_db_session.execute.return_value = SimpleNamespace(one=lambda: (0, None, None))

    result = await load_evidence_window_stats(
        mock_db_session,
        trend_id=uuid4(),
    )

    assert result.evidence_count == 0
    assert result.avg_corroboration == pytest.approx(0.5)
    assert result.days_since_last_evidence == 30


@pytest.mark.asyncio
async def test_load_evidence_window_stats_normalizes_naive_recent_time_and_filters_state(
    mock_db_session,
) -> None:
    recent = datetime(2026, 3, 25, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None)
    mock_db_session.execute.return_value = SimpleNamespace(one=lambda: (4, 0.8, recent))
    state_version_id = uuid4()
    now = datetime(2026, 3, 26, 12, 0, 0, tzinfo=UTC)

    result = await load_evidence_window_stats(
        mock_db_session,
        trend_id=uuid4(),
        state_version_id=state_version_id,
        now=now,
    )

    assert result.evidence_count == 4
    assert result.avg_corroboration == pytest.approx(0.8)
    assert result.days_since_last_evidence == 1
    assert "trend_evidence.state_version_id" in str(mock_db_session.execute.await_args.args[0])


@pytest.mark.asyncio
async def test_build_momentum_state_reports_acceleration_and_recent_evidence(
    mock_db_session,
) -> None:
    trend = SimpleNamespace(id=uuid4())
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.60,
        get_probability_at=AsyncMock(side_effect=[0.52, 0.50]),
    )
    mock_db_session.scalar.return_value = 5

    state = await build_momentum_state(
        mock_db_session,
        trend_engine=trend_engine,
        trend=trend,
        now=datetime(2026, 3, 26, tzinfo=UTC),
    )

    assert state.direction == "rising_fast"
    assert state.delta_probability == pytest.approx(0.08)
    assert state.previous_window_delta == pytest.approx(0.02)
    assert state.acceleration == pytest.approx(0.06)
    assert state.evidence_count_window == 5


@pytest.mark.asyncio
async def test_build_momentum_state_degrades_to_stable_without_snapshot_history(
    mock_db_session,
) -> None:
    trend = SimpleNamespace(id=uuid4())
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.40,
        get_probability_at=AsyncMock(side_effect=[None, None]),
    )
    mock_db_session.scalar.return_value = 0

    state = await build_momentum_state(
        mock_db_session,
        trend_engine=trend_engine,
        trend=trend,
        now=datetime.now(tz=UTC) - timedelta(days=1),
    )

    assert state.direction == "stable"
    assert state.delta_probability == 0.0
    assert state.previous_window_delta is None
    assert state.acceleration is None
    assert state.evidence_count_window == 0


@pytest.mark.asyncio
async def test_build_momentum_state_requires_trend_id(mock_db_session) -> None:
    trend_engine = SimpleNamespace(get_probability=lambda _trend: 0.4)

    with pytest.raises(ValueError, match="Trend id is required"):
        await build_momentum_state(
            mock_db_session,
            trend_engine=trend_engine,
            trend=SimpleNamespace(id=None),
        )


@pytest.mark.asyncio
async def test_build_momentum_state_handles_missing_previous_window_and_state_filter(
    mock_db_session,
) -> None:
    trend = SimpleNamespace(id=uuid4())
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.50,
        get_probability_at=AsyncMock(side_effect=[0.48, None]),
    )
    state_version_id = uuid4()
    mock_db_session.scalar.return_value = 2

    state = await build_momentum_state(
        mock_db_session,
        trend_engine=trend_engine,
        trend=trend,
        state_version_id=state_version_id,
        now=datetime(2026, 3, 26, tzinfo=UTC),
    )

    assert state.direction == "rising"
    assert state.delta_probability == pytest.approx(0.02)
    assert state.previous_window_delta is None
    assert state.acceleration is None
    assert "trend_evidence.state_version_id" in str(mock_db_session.scalar.await_args.args[0])
