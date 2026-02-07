from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.trends import (
    TrendCreate,
    TrendUpdate,
    create_trend,
    delete_trend,
    get_trend,
    get_trend_history,
    list_trend_evidence,
    list_trends,
    load_trends_from_config,
    update_trend,
)
from src.core.trend_engine import logodds_to_prob, prob_to_logodds
from src.storage.models import Trend, TrendEvidence, TrendSnapshot

pytestmark = pytest.mark.unit


def _build_trend(
    *,
    trend_id: UUID | None = None,
    name: str = "Test Trend",
    is_active: bool = True,
) -> Trend:
    now = datetime.now(tz=UTC)
    return Trend(
        id=trend_id or uuid4(),
        name=name,
        description="Trend description",
        definition={"id": "test-trend"},
        baseline_log_odds=prob_to_logodds(0.1),
        current_log_odds=prob_to_logodds(0.2),
        indicators={"signal": {"direction": "escalatory", "keywords": ["x"]}},
        decay_half_life_days=30,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_list_trends_returns_response_models(mock_db_session) -> None:
    trend = _build_trend()
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [trend])

    result = await list_trends(session=mock_db_session, sync_from_config=False)

    assert len(result) == 1
    assert result[0].id == trend.id
    assert result[0].name == trend.name
    assert result[0].baseline_probability == pytest.approx(0.1, rel=0.01)
    assert result[0].current_probability == pytest.approx(0.2, rel=0.01)
    assert mock_db_session.scalars.await_count == 1


@pytest.mark.asyncio
async def test_create_trend_persists_new_record(mock_db_session) -> None:
    created_id = uuid4()
    mock_db_session.scalar.return_value = None

    async def flush_side_effect() -> None:
        trend_record = mock_db_session.add.call_args.args[0]
        trend_record.id = created_id
        trend_record.updated_at = datetime.now(tz=UTC)

    mock_db_session.flush.side_effect = flush_side_effect

    result = await create_trend(
        trend=TrendCreate(
            name="EU-Russia Conflict",
            description="Tracks conflict probability",
            definition={},
            baseline_probability=0.08,
            indicators={"military_movement": {"direction": "escalatory"}},
        ),
        session=mock_db_session,
    )

    added = mock_db_session.add.call_args.args[0]
    assert result.id == created_id
    assert result.name == "EU-Russia Conflict"
    assert result.current_probability == pytest.approx(0.08, rel=0.01)
    assert added.definition["id"] == "eu-russia-conflict"
    assert float(added.baseline_log_odds) == pytest.approx(prob_to_logodds(0.08), rel=0.001)
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_create_trend_returns_409_when_name_exists(mock_db_session) -> None:
    mock_db_session.scalar.return_value = uuid4()

    with pytest.raises(HTTPException, match="already exists") as exc_info:
        await create_trend(
            trend=TrendCreate(
                name="Duplicate",
                baseline_probability=0.1,
                indicators={"x": {"direction": "escalatory"}},
            ),
            session=mock_db_session,
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_get_trend_returns_404_when_missing(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc_info:
        await get_trend(trend_id=uuid4(), session=mock_db_session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_trend_updates_fields_and_probabilities(mock_db_session) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend
    mock_db_session.scalar.return_value = None

    result = await update_trend(
        trend_id=trend.id,
        trend=TrendUpdate(
            name="Updated Trend",
            baseline_probability=0.25,
            current_probability=0.35,
            is_active=False,
            definition={},
        ),
        session=mock_db_session,
    )

    assert trend.name == "Updated Trend"
    assert trend.definition["id"] == "updated-trend"
    assert float(trend.baseline_log_odds) == pytest.approx(prob_to_logodds(0.25), rel=0.001)
    assert float(trend.current_log_odds) == pytest.approx(prob_to_logodds(0.35), rel=0.001)
    assert trend.is_active is False
    assert result.current_probability == pytest.approx(0.35, rel=0.01)
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_delete_trend_deactivates_record(mock_db_session) -> None:
    trend = _build_trend(is_active=True)
    mock_db_session.get.return_value = trend

    await delete_trend(trend_id=trend.id, session=mock_db_session)

    assert trend.is_active is False
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_load_trends_from_config_creates_records(mock_db_session, tmp_path) -> None:
    config_file = tmp_path / "sample-trend.yaml"
    config_file.write_text(
        """
id: sample-trend
name: Sample Trend
description: Sample description
baseline_probability: 0.15
decay_half_life_days: 20
indicators:
  test_signal:
    direction: escalatory
    keywords: ["alpha"]
""".strip(),
        encoding="utf-8",
    )
    mock_db_session.scalar.side_effect = [None]

    result = await load_trends_from_config(mock_db_session, config_dir=str(tmp_path))

    assert result.loaded_files == 1
    assert result.created == 1
    assert result.updated == 0
    assert result.errors == []
    added = mock_db_session.add.call_args.args[0]
    assert added.name == "Sample Trend"
    assert logodds_to_prob(float(added.baseline_log_odds)) == pytest.approx(0.15, rel=0.01)
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_list_trend_evidence_returns_records(mock_db_session) -> None:
    trend = _build_trend()
    evidence_id = uuid4()
    event_id = uuid4()
    created_at = datetime.now(tz=UTC)
    evidence = TrendEvidence(
        id=evidence_id,
        trend_id=trend.id,
        event_id=event_id,
        signal_type="military_movement",
        credibility_score=0.9,
        corroboration_factor=0.67,
        novelty_score=1.0,
        severity_score=0.8,
        confidence_score=0.95,
        delta_log_odds=0.02,
        reasoning="Multiple sources corroborate force buildup",
        created_at=created_at,
    )
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [evidence])

    result = await list_trend_evidence(trend_id=trend.id, session=mock_db_session)

    assert len(result) == 1
    assert result[0].id == evidence_id
    assert result[0].trend_id == trend.id
    assert result[0].event_id == event_id
    assert result[0].signal_type == "military_movement"
    assert result[0].credibility_score == pytest.approx(0.9)
    assert result[0].corroboration_factor == pytest.approx(0.67)
    assert result[0].novelty_score == pytest.approx(1.0)
    assert result[0].severity_score == pytest.approx(0.8)
    assert result[0].confidence_score == pytest.approx(0.95)
    assert result[0].delta_log_odds == pytest.approx(0.02)
    assert result[0].reasoning == "Multiple sources corroborate force buildup"
    assert result[0].created_at == created_at
    assert mock_db_session.scalars.await_count == 1


@pytest.mark.asyncio
async def test_list_trend_evidence_filters_by_date_range(mock_db_session) -> None:
    trend = _build_trend()
    now = datetime.now(tz=UTC)
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    await list_trend_evidence(
        trend_id=trend.id,
        start_at=now - timedelta(days=7),
        end_at=now,
        limit=25,
        session=mock_db_session,
    )

    query = mock_db_session.scalars.await_args.args[0]
    query_text = str(query)
    assert "trend_evidence.created_at >=" in query_text
    assert "trend_evidence.created_at <=" in query_text


@pytest.mark.asyncio
async def test_list_trend_evidence_rejects_invalid_date_range(mock_db_session) -> None:
    trend = _build_trend()
    now = datetime.now(tz=UTC)
    mock_db_session.get.return_value = trend

    with pytest.raises(HTTPException, match="start_at must be less than or equal to end_at") as exc:
        await list_trend_evidence(
            trend_id=trend.id,
            start_at=now,
            end_at=now - timedelta(minutes=1),
            session=mock_db_session,
        )

    assert exc.value.status_code == 400
    mock_db_session.scalars.assert_not_called()


@pytest.mark.asyncio
async def test_get_trend_history_returns_snapshots(mock_db_session) -> None:
    trend = _build_trend()
    now = datetime.now(tz=UTC)
    snapshots = [
        TrendSnapshot(
            trend_id=trend.id,
            timestamp=now - timedelta(hours=2),
            log_odds=prob_to_logodds(0.20),
        ),
        TrendSnapshot(
            trend_id=trend.id,
            timestamp=now - timedelta(hours=1),
            log_odds=prob_to_logodds(0.24),
        ),
    ]
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: snapshots)

    result = await get_trend_history(trend_id=trend.id, session=mock_db_session)

    assert len(result) == 2
    assert result[0].timestamp == snapshots[0].timestamp
    assert result[0].probability == pytest.approx(0.20, rel=0.01)
    assert result[1].timestamp == snapshots[1].timestamp
    assert result[1].probability == pytest.approx(0.24, rel=0.01)


@pytest.mark.asyncio
async def test_get_trend_history_downsamples_daily(mock_db_session) -> None:
    trend = _build_trend()
    start = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
    snapshots = [
        TrendSnapshot(
            trend_id=trend.id,
            timestamp=start,
            log_odds=prob_to_logodds(0.20),
        ),
        TrendSnapshot(
            trend_id=trend.id,
            timestamp=start + timedelta(hours=8),
            log_odds=prob_to_logodds(0.25),
        ),
        TrendSnapshot(
            trend_id=trend.id,
            timestamp=start + timedelta(days=1, hours=1),
            log_odds=prob_to_logodds(0.30),
        ),
    ]
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: snapshots)

    result = await get_trend_history(
        trend_id=trend.id,
        interval="daily",
        session=mock_db_session,
    )

    assert len(result) == 2
    assert result[0].timestamp == snapshots[1].timestamp
    assert result[0].probability == pytest.approx(0.25, rel=0.01)
    assert result[1].timestamp == snapshots[2].timestamp
    assert result[1].probability == pytest.approx(0.30, rel=0.01)


@pytest.mark.asyncio
async def test_get_trend_history_rejects_invalid_date_range(mock_db_session) -> None:
    trend = _build_trend()
    now = datetime.now(tz=UTC)
    mock_db_session.get.return_value = trend

    with pytest.raises(HTTPException, match="start_at must be less than or equal to end_at") as exc:
        await get_trend_history(
            trend_id=trend.id,
            start_at=now,
            end_at=now - timedelta(minutes=1),
            session=mock_db_session,
        )

    assert exc.value.status_code == 400
    mock_db_session.scalars.assert_not_called()
