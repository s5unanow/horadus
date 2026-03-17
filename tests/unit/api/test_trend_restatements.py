from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

import src.api.routes.trend_restatements as restatement_routes
from src.api.routes.trend_restatements import get_trend_projection, list_trend_restatements
from src.core.trend_restatement import TrendProjectionCheck
from src.storage.models import Trend, TrendEvidence, TrendRestatement

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_list_trend_restatements_returns_net_effects_newest_first(mock_db_session) -> None:
    trend = Trend(
        id=uuid4(),
        name="Restatement Trend",
        runtime_trend_id="restatement-trend",
        definition={"id": "restatement-trend"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.3,
    )
    first = TrendRestatement(
        id=uuid4(),
        trend_id=trend.id,
        trend_evidence_id=evidence.id,
        restatement_kind="partial_restatement",
        source="event_feedback",
        original_evidence_delta_log_odds=0.3,
        compensation_delta_log_odds=-0.1,
        recorded_at=datetime(2026, 3, 17, 10, 0, tzinfo=UTC),
    )
    second = TrendRestatement(
        id=uuid4(),
        trend_id=trend.id,
        trend_evidence_id=evidence.id,
        restatement_kind="partial_restatement",
        source="event_feedback",
        original_evidence_delta_log_odds=0.3,
        compensation_delta_log_odds=-0.05,
        recorded_at=datetime(2026, 3, 17, 11, 0, tzinfo=UTC),
    )
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [first, second]),
        SimpleNamespace(all=lambda: [evidence]),
    ]

    result = await list_trend_restatements(trend_id=trend.id, limit=100, session=mock_db_session)

    assert [row.id for row in result] == [second.id, first.id]
    assert result[0].net_evidence_delta_log_odds == pytest.approx(0.15)
    assert result[1].net_evidence_delta_log_odds == pytest.approx(0.2)
    assert result[0].historical_artifact_policy == "belief_at_time"


@pytest.mark.asyncio
async def test_list_trend_restatements_handles_manual_rows_without_evidence(
    mock_db_session,
) -> None:
    trend = Trend(
        id=uuid4(),
        name="Manual Trend",
        runtime_trend_id="manual-trend",
        definition={"id": "manual-trend"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    row = TrendRestatement(
        id=uuid4(),
        trend_id=trend.id,
        restatement_kind="manual_compensation",
        source="trend_override",
        compensation_delta_log_odds=-0.1,
        recorded_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
    )
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [row])

    result = await list_trend_restatements(trend_id=trend.id, limit=100, session=mock_db_session)

    assert len(result) == 1
    assert result[0].signal_type is None
    assert result[0].net_evidence_delta_log_odds is None


@pytest.mark.asyncio
async def test_list_trend_restatements_handles_missing_original_delta(mock_db_session) -> None:
    trend = Trend(
        id=uuid4(),
        name="Linked Trend",
        runtime_trend_id="linked-trend",
        definition={"id": "linked-trend"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.3,
    )
    row = TrendRestatement(
        id=uuid4(),
        trend_id=trend.id,
        trend_evidence_id=evidence.id,
        restatement_kind="reclassification",
        source="tier2_reconciliation",
        original_evidence_delta_log_odds=None,
        compensation_delta_log_odds=-0.3,
        recorded_at=datetime(2026, 3, 17, 12, 30, tzinfo=UTC),
    )
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [row]),
        SimpleNamespace(all=lambda: [evidence]),
    ]

    result = await list_trend_restatements(trend_id=trend.id, limit=100, session=mock_db_session)

    assert len(result) == 1
    assert result[0].signal_type == "military_movement"
    assert result[0].net_evidence_delta_log_odds is None


@pytest.mark.asyncio
async def test_list_trend_restatements_returns_404_for_unknown_trend(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc:
        await list_trend_restatements(trend_id=uuid4(), limit=100, session=mock_db_session)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_trend_projection_uses_projection_helper(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend = Trend(
        id=uuid4(),
        name="Projection Trend",
        runtime_trend_id="projection-trend",
        definition={"id": "projection-trend"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.1,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
        updated_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
    )

    async def _fake_build(*, session, trend, as_of):
        assert session is mock_db_session
        assert trend.id is not None
        return TrendProjectionCheck(
            as_of=as_of,
            stored_log_odds=-1.1,
            projected_log_odds=-1.1,
            drift_log_odds=0.0,
            evidence_count=2,
            restatement_count=1,
            entry_count=3,
        )

    monkeypatch.setattr(restatement_routes, "build_trend_projection_check", _fake_build)
    mock_db_session.get.return_value = trend

    result = await get_trend_projection(trend_id=trend.id, as_of=None, session=mock_db_session)

    assert result.matches_projection is True
    assert result.evidence_count == 2
    assert result.restatement_count == 1
    assert result.historical_artifact_policy == "belief_at_time"
