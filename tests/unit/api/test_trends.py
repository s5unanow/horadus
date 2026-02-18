from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

import src.api.routes.trends as trends_module
from src.api.routes.trends import (
    TrendCreate,
    TrendUpdate,
    create_trend,
    delete_trend,
    get_trend,
    get_trend_calibration,
    get_trend_history,
    get_trend_retrospective,
    list_trend_evidence,
    list_trends,
    load_trends_from_config,
    record_trend_outcome,
    simulate_trend,
    update_trend,
)
from src.core.calibration import CalibrationBucket, CalibrationReport
from src.core.trend_engine import logodds_to_prob, prob_to_logodds
from src.storage.models import OutcomeType, Trend, TrendEvidence, TrendOutcome, TrendSnapshot

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_risk_presentation(monkeypatch) -> None:
    async def _fake_evidence_stats(*_args: object, **_kwargs: object) -> tuple[int, float, int]:
        return 8, 0.75, 1

    async def _fake_top_movers(*_args: object, **_kwargs: object) -> list[str]:
        return ["Signal corroborated across multiple outlets"]

    monkeypatch.setattr(trends_module, "_get_evidence_stats", _fake_evidence_stats)
    monkeypatch.setattr(trends_module, "_get_top_movers_7d", _fake_top_movers)


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
    assert result[0].risk_level == "guarded"
    assert result[0].probability_band[0] == pytest.approx(0.10235, rel=0.01)
    assert result[0].probability_band[1] == pytest.approx(0.29765, rel=0.01)
    assert result[0].confidence == "medium"
    assert len(result[0].top_movers_7d) == 1
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
            definition={"baseline_probability": 0.99},
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
    assert added.definition["baseline_probability"] == pytest.approx(0.08, rel=0.001)
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
    assert trend.definition["baseline_probability"] == pytest.approx(0.25, rel=0.001)
    assert float(trend.baseline_log_odds) == pytest.approx(prob_to_logodds(0.25), rel=0.001)
    assert float(trend.current_log_odds) == pytest.approx(prob_to_logodds(0.35), rel=0.001)
    assert trend.is_active is False
    assert result.current_probability == pytest.approx(0.35, rel=0.01)
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_update_trend_syncs_definition_baseline_without_definition_payload(
    mock_db_session,
) -> None:
    trend = _build_trend()
    trend.definition = {"id": "test-trend", "baseline_probability": 0.9}
    mock_db_session.get.return_value = trend

    await update_trend(
        trend_id=trend.id,
        trend=TrendUpdate(baseline_probability=0.2),
        session=mock_db_session,
    )

    assert float(trend.baseline_log_odds) == pytest.approx(prob_to_logodds(0.2), rel=0.001)
    assert trend.definition["baseline_probability"] == pytest.approx(0.2, rel=0.001)
    assert trend.definition["id"] == "test-trend"


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
    weight: 0.04
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
    assert added.definition["baseline_probability"] == pytest.approx(0.15, rel=0.001)
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_load_trends_from_config_supports_enhanced_fields(
    mock_db_session,
    tmp_path,
) -> None:
    config_file = tmp_path / "enhanced-trend.yaml"
    config_file.write_text(
        """
id: enhanced-trend
name: Enhanced Trend
baseline_probability: 0.20
decay_half_life_days: 15
disqualifiers:
  - signal: peace_treaty
    effect: reset_to_baseline
    description: Signed peace treaty
falsification_criteria:
  decrease_confidence:
    - Sustained de-escalation
indicators:
  military_movement:
    weight: 0.04
    direction: escalatory
    type: leading
    decay_half_life_days: 10
    keywords: ["troops"]
""".strip(),
        encoding="utf-8",
    )
    mock_db_session.scalar.side_effect = [None]

    result = await load_trends_from_config(mock_db_session, config_dir=str(tmp_path))

    assert result.created == 1
    assert result.errors == []
    added = mock_db_session.add.call_args.args[0]
    assert added.indicators["military_movement"]["type"] == "leading"
    assert added.indicators["military_movement"]["decay_half_life_days"] == 10
    assert added.definition["disqualifiers"][0]["effect"] == "reset_to_baseline"
    assert added.definition["falsification_criteria"]["decrease_confidence"] == [
        "Sustained de-escalation"
    ]


@pytest.mark.asyncio
async def test_load_trends_from_config_rejects_invalid_indicator_type(
    mock_db_session,
    tmp_path,
) -> None:
    config_file = tmp_path / "invalid-trend.yaml"
    config_file.write_text(
        """
id: invalid-trend
name: Invalid Trend
baseline_probability: 0.20
indicators:
  military_movement:
    weight: 0.04
    direction: escalatory
    type: invalid_kind
    keywords: ["troops"]
""".strip(),
        encoding="utf-8",
    )

    result = await load_trends_from_config(mock_db_session, config_dir=str(tmp_path))

    assert result.created == 0
    assert result.updated == 0
    assert len(result.errors) == 1
    assert "invalid-trend.yaml" in result.errors[0]
    mock_db_session.add.assert_not_called()


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
    assert result[0].is_invalidated is False
    assert result[0].invalidated_at is None
    assert result[0].invalidation_feedback_id is None
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
    query_text = str(query).lower()
    assert "trend_evidence.created_at >=" in query_text
    assert "trend_evidence.created_at <=" in query_text
    assert "trend_evidence.is_invalidated is false" in query_text


@pytest.mark.asyncio
async def test_list_trend_evidence_include_invalidated_omits_active_filter(
    mock_db_session,
) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    await list_trend_evidence(
        trend_id=trend.id,
        include_invalidated=True,
        session=mock_db_session,
    )

    query = mock_db_session.scalars.await_args.args[0]
    query_text = str(query).lower()
    assert "trend_evidence.is_invalidated is false" not in query_text


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
async def test_simulate_trend_injects_hypothetical_signal_without_db_mutation(
    mock_db_session,
) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend

    payload = trends_module.InjectHypotheticalSignalSimulationRequest(
        mode="inject_hypothetical_signal",
        signal_type="military_movement",
        indicator_weight=0.04,
        source_credibility=0.9,
        corroboration_count=3,
        novelty_score=1.0,
        direction="escalatory",
        severity=0.8,
        confidence=0.95,
    )
    expected_delta, _ = trends_module.calculate_evidence_delta(
        signal_type=payload.signal_type,
        indicator_weight=payload.indicator_weight,
        source_credibility=payload.source_credibility,
        corroboration_count=payload.corroboration_count,
        novelty_score=payload.novelty_score,
        direction=payload.direction,
        severity=payload.severity,
        confidence=payload.confidence,
    )

    result = await simulate_trend(
        trend_id=trend.id,
        payload=payload,
        session=mock_db_session,
    )

    assert result.mode == "inject_hypothetical_signal"
    assert result.trend_id == trend.id
    assert result.delta_log_odds == pytest.approx(expected_delta)
    assert result.projected_probability == pytest.approx(
        logodds_to_prob(float(trend.current_log_odds) + expected_delta),
    )
    assert result.factor_breakdown["base_weight"] == pytest.approx(payload.indicator_weight)
    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_called()


@pytest.mark.asyncio
async def test_simulate_trend_removes_event_impact_without_db_mutation(
    mock_db_session,
) -> None:
    trend = _build_trend()
    event_id = uuid4()
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [
            TrendEvidence(
                id=uuid4(),
                trend_id=trend.id,
                event_id=event_id,
                signal_type="military_movement",
                delta_log_odds=0.02,
            ),
            TrendEvidence(
                id=uuid4(),
                trend_id=trend.id,
                event_id=event_id,
                signal_type="diplomatic_breakdown",
                delta_log_odds=-0.01,
            ),
        ]
    )

    result = await simulate_trend(
        trend_id=trend.id,
        payload=trends_module.RemoveEventImpactSimulationRequest(
            mode="remove_event_impact",
            event_id=event_id,
        ),
        session=mock_db_session,
    )

    assert result.mode == "remove_event_impact"
    assert result.delta_log_odds == pytest.approx(-0.01)
    assert result.factor_breakdown["evidence_count"] == 2
    assert result.factor_breakdown["removed_sum_delta_log_odds"] == pytest.approx(0.01)
    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_called()


@pytest.mark.asyncio
async def test_simulate_trend_remove_event_returns_404_when_no_evidence(mock_db_session) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    with pytest.raises(HTTPException, match="No matching trend evidence found") as exc:
        await simulate_trend(
            trend_id=trend.id,
            payload=trends_module.RemoveEventImpactSimulationRequest(
                mode="remove_event_impact",
                event_id=uuid4(),
            ),
            session=mock_db_session,
        )

    assert exc.value.status_code == 404


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


@pytest.mark.asyncio
async def test_get_trend_retrospective_returns_analysis(mock_db_session, monkeypatch) -> None:
    trend = _build_trend(name="EU-Russia Risk")
    now = datetime.now(tz=UTC)
    start_date = now - timedelta(days=14)
    mock_db_session.get.return_value = trend

    class FakeAnalyzer:
        def __init__(self, session: object) -> None:
            assert session is mock_db_session

        async def analyze(
            self,
            *,
            trend: Trend,
            start_date: datetime,
            end_date: datetime,
        ) -> dict[str, object]:
            assert trend.id is not None
            assert start_date <= end_date
            return {
                "trend_id": trend.id,
                "trend_name": trend.name,
                "period_start": start_date,
                "period_end": end_date,
                "pivotal_events": [
                    {
                        "event_id": uuid4(),
                        "summary": "Border forces repositioned",
                        "categories": ["military"],
                        "evidence_count": 3,
                        "net_delta_log_odds": 0.14,
                        "abs_delta_log_odds": 0.14,
                        "direction": "up",
                    }
                ],
                "category_breakdown": {"military": 1},
                "predictive_signals": [
                    {
                        "signal_type": "military_movement",
                        "evidence_count": 4,
                        "net_delta_log_odds": 0.21,
                        "abs_delta_log_odds": 0.21,
                    }
                ],
                "accuracy_assessment": {
                    "outcome_count": 2,
                    "resolved_outcomes": 2,
                    "scored_outcomes": 2,
                    "mean_brier_score": 0.18,
                    "resolved_rate": 1.0,
                },
                "narrative": "Signals were dominated by military movement in the period.",
                "grounding_status": "grounded",
                "grounding_violation_count": 0,
                "grounding_references": None,
            }

    monkeypatch.setattr(trends_module, "RetrospectiveAnalyzer", FakeAnalyzer)

    result = await get_trend_retrospective(
        trend_id=trend.id,
        start_date=start_date,
        end_date=now,
        session=mock_db_session,
    )

    assert result.trend_id == trend.id
    assert result.trend_name == trend.name
    assert len(result.pivotal_events) == 1
    assert result.pivotal_events[0].direction == "up"
    assert result.predictive_signals[0].signal_type == "military_movement"
    assert result.accuracy_assessment["mean_brier_score"] == pytest.approx(0.18)
    assert result.grounding_status == "grounded"
    assert result.grounding_violation_count == 0


@pytest.mark.asyncio
async def test_get_trend_retrospective_rejects_invalid_date_range(mock_db_session) -> None:
    trend = _build_trend()
    now = datetime.now(tz=UTC)
    mock_db_session.get.return_value = trend

    with pytest.raises(
        HTTPException, match="start_date must be less than or equal to end_date"
    ) as exc:
        await get_trend_retrospective(
            trend_id=trend.id,
            start_date=now,
            end_date=now - timedelta(days=1),
            session=mock_db_session,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_record_trend_outcome_returns_created_payload(
    mock_db_session,
    monkeypatch,
) -> None:
    trend = _build_trend()
    now = datetime.now(tz=UTC)
    outcome_id = uuid4()
    mock_db_session.get.return_value = trend

    class FakeService:
        def __init__(self, session: object) -> None:
            assert session is mock_db_session

        async def record_outcome(
            self,
            *,
            trend_id: UUID,
            outcome: OutcomeType,
            outcome_date: datetime,
            notes: str | None,
            evidence: dict[str, object] | None,
            recorded_by: str | None,
        ) -> TrendOutcome:
            assert trend_id == trend.id
            assert outcome == OutcomeType.OCCURRED
            assert notes == "Confirmed by OSINT"
            assert evidence == {"items": ["x-1"]}
            assert recorded_by == "analyst@horadus"
            return TrendOutcome(
                id=outcome_id,
                trend_id=trend.id,
                prediction_date=outcome_date,
                predicted_probability=0.40,
                predicted_risk_level="elevated",
                probability_band_low=0.30,
                probability_band_high=0.50,
                outcome_date=outcome_date,
                outcome=outcome.value,
                outcome_notes=notes,
                outcome_evidence=evidence,
                brier_score=0.36,
                recorded_by=recorded_by,
                created_at=now,
            )

    monkeypatch.setattr(trends_module, "CalibrationService", FakeService)

    result = await record_trend_outcome(
        trend_id=trend.id,
        payload=trends_module.TrendOutcomeCreate(
            outcome=OutcomeType.OCCURRED,
            outcome_date=now,
            outcome_notes="Confirmed by OSINT",
            outcome_evidence={"items": ["x-1"]},
            recorded_by="analyst@horadus",
        ),
        session=mock_db_session,
    )

    assert result.id == outcome_id
    assert result.trend_id == trend.id
    assert result.predicted_probability == pytest.approx(0.40)
    assert result.probability_band_low == pytest.approx(0.30)
    assert result.probability_band_high == pytest.approx(0.50)
    assert result.outcome == "occurred"
    assert result.brier_score == pytest.approx(0.36)


@pytest.mark.asyncio
async def test_record_trend_outcome_returns_404_when_trend_missing(
    mock_db_session,
    monkeypatch,
) -> None:
    class FakeService:
        def __init__(self, _session: object) -> None:
            pass

        async def record_outcome(self, **_: object) -> TrendOutcome:
            raise ValueError("Trend not found")

    monkeypatch.setattr(trends_module, "CalibrationService", FakeService)

    with pytest.raises(HTTPException, match="Trend not found") as exc:
        await record_trend_outcome(
            trend_id=uuid4(),
            payload=trends_module.TrendOutcomeCreate(
                outcome=OutcomeType.DID_NOT_OCCUR,
                outcome_date=datetime.now(tz=UTC),
            ),
            session=mock_db_session,
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_trend_calibration_returns_report(mock_db_session, monkeypatch) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend

    class FakeService:
        def __init__(self, session: object) -> None:
            assert session is mock_db_session

        async def get_calibration_report(
            self,
            *,
            trend_id: UUID,
            start_date: datetime | None = None,
            end_date: datetime | None = None,
        ) -> CalibrationReport:
            assert trend_id == trend.id
            assert start_date is None
            assert end_date is None
            return CalibrationReport(
                total_predictions=12,
                resolved_predictions=9,
                mean_brier_score=0.18,
                overconfident=False,
                underconfident=True,
                buckets=[
                    CalibrationBucket(
                        bucket_start=0.2,
                        bucket_end=0.3,
                        prediction_count=4,
                        occurred_count=1,
                        actual_rate=0.25,
                        expected_rate=0.25,
                        calibration_error=0.0,
                    )
                ],
            )

    monkeypatch.setattr(trends_module, "CalibrationService", FakeService)

    result = await get_trend_calibration(
        trend_id=trend.id,
        session=mock_db_session,
    )

    assert result.trend_id == trend.id
    assert result.total_predictions == 12
    assert result.resolved_predictions == 9
    assert result.mean_brier_score == pytest.approx(0.18)
    assert result.overconfident is False
    assert result.underconfident is True
    assert len(result.buckets) == 1
    assert result.buckets[0].prediction_count == 4


@pytest.mark.asyncio
async def test_get_trend_calibration_rejects_invalid_date_range(mock_db_session) -> None:
    trend = _build_trend()
    now = datetime.now(tz=UTC)
    mock_db_session.get.return_value = trend

    with pytest.raises(
        HTTPException, match="start_date must be less than or equal to end_date"
    ) as exc:
        await get_trend_calibration(
            trend_id=trend.id,
            start_date=now,
            end_date=now - timedelta(days=1),
            session=mock_db_session,
        )

    assert exc.value.status_code == 400
