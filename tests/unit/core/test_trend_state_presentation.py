from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.trend_state_presentation import (
    EvidenceWindowStats,
    TrendUncertaintyLevel,
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
