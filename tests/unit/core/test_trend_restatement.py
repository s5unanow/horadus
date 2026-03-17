from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.trend_restatement import (
    _as_utc,
    apply_compensating_restatement,
    build_trend_projection_check,
)
from src.storage.models import Trend, TrendEvidence, TrendRestatement

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_build_trend_projection_check_replays_evidence_and_restatements_with_decay(
    mock_db_session,
) -> None:
    created_at = datetime(2026, 3, 1, tzinfo=UTC)
    trend = Trend(
        id=uuid4(),
        name="Projection Trend",
        runtime_trend_id="projection-trend",
        definition={"id": "projection-trend"},
        baseline_log_odds=0.0,
        current_log_odds=0.05,
        indicators={},
        decay_half_life_days=10,
        is_active=True,
        created_at=created_at,
        updated_at=created_at + timedelta(days=20),
    )
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.4,
        created_at=created_at,
    )
    restatement = TrendRestatement(
        id=uuid4(),
        trend_id=trend.id,
        trend_evidence_id=evidence.id,
        restatement_kind="partial_restatement",
        source="event_feedback",
        original_evidence_delta_log_odds=0.4,
        compensation_delta_log_odds=-0.1,
        recorded_at=created_at + timedelta(days=10),
    )
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=lambda: [restatement]),
    ]

    result = await build_trend_projection_check(session=mock_db_session, trend=trend)

    assert result.evidence_count == 1
    assert result.restatement_count == 1
    assert result.projected_log_odds == pytest.approx(0.05, rel=1e-6)
    assert result.drift_log_odds == pytest.approx(0.0, abs=1e-9)
    assert result.matches_projection is True


def test_as_utc_normalizes_naive_datetime() -> None:
    value = datetime(2026, 3, 17, 12, 0, tzinfo=UTC).replace(tzinfo=None)

    normalized = _as_utc(value)

    assert normalized.tzinfo is UTC


@pytest.mark.asyncio
async def test_apply_compensating_restatement_requires_trend_id() -> None:
    trend = Trend(
        id=None,
        name="Invalid Trend",
        runtime_trend_id="invalid-trend",
        definition={"id": "invalid-trend"},
        baseline_log_odds=0.0,
        current_log_odds=0.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )

    with pytest.raises(ValueError, match="Trend must have an id"):
        await apply_compensating_restatement(
            trend_engine=SimpleNamespace(session=None),
            trend=trend,
            compensation_delta_log_odds=0.1,
            restatement_kind="manual_compensation",
            source="trend_override",
        )


@pytest.mark.asyncio
async def test_apply_compensating_restatement_leaves_in_memory_trend_when_delta_result_unchanged() -> (
    None
):
    trend = Trend(
        id=uuid4(),
        name="No-op Trend",
        runtime_trend_id="noop-trend",
        definition={"id": "noop-trend"},
        baseline_log_odds=0.0,
        current_log_odds=0.4,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )

    class _Engine:
        session = None

        async def apply_log_odds_delta(self, **kwargs) -> tuple[float, float]:
            return (0.4, 0.4)

    await apply_compensating_restatement(
        trend_engine=_Engine(),
        trend=trend,
        compensation_delta_log_odds=0.1,
        restatement_kind="manual_compensation",
        source="trend_override",
    )

    assert float(trend.current_log_odds) == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_build_trend_projection_check_requires_trend_id(mock_db_session) -> None:
    trend = Trend(
        id=None,
        name="Missing Id",
        runtime_trend_id="missing-id",
        definition={"id": "missing-id"},
        baseline_log_odds=0.0,
        current_log_odds=0.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )

    with pytest.raises(ValueError, match="Trend must have an id"):
        await build_trend_projection_check(session=mock_db_session, trend=trend)
