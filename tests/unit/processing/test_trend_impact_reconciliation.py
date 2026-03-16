from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.trend_engine import EvidenceFactors, TrendEngine
from src.processing.trend_impact_reconciliation import (
    DesiredTrendEvidence,
    ParsedTrendImpact,
    _append_reconciliation_history,
    _evidence_matches,
    _float_matches,
    _invalidate_absent_evidence,
    _invalidate_active_evidence,
    _invalidate_existing_match,
    _lineage_entry,
    _load_active_event_evidence,
    _reconcile_desired_evidence,
    _taxonomy_gap_details,
    _trend_for_evidence,
    impact_reasoning,
    parse_trend_impact,
    reconcile_event_trend_impacts,
)
from src.storage.models import Event, TrendEvidence

pytestmark = pytest.mark.unit


def _factors(*, severity: float = 0.5, confidence: float = 0.6) -> EvidenceFactors:
    return EvidenceFactors(
        base_weight=0.04,
        severity=severity,
        confidence=confidence,
        credibility=0.8,
        corroboration=0.33,
        novelty=1.0,
        evidence_age_days=0.0,
        temporal_decay_multiplier=1.0,
        direction_multiplier=1.0,
        raw_delta=0.01,
        clamped_delta=0.01,
    )


def _desired(*, trend, reasoning: str = "because") -> DesiredTrendEvidence:
    return DesiredTrendEvidence(
        trend=trend,
        impact=ParsedTrendImpact(
            trend_id="trend-a",
            signal_type="military_movement",
            direction="escalatory",
            severity=0.5,
            confidence=0.6,
            rationale=reasoning,
        ),
        delta=0.01,
        factors=_factors(),
        reasoning=reasoning,
    )


def _evidence(
    *, trend_id, event_id, evidence_id=None, delta=0.01, reasoning="because"
) -> TrendEvidence:
    return TrendEvidence(
        id=evidence_id or uuid4(),
        trend_id=trend_id,
        event_id=event_id,
        signal_type="military_movement",
        base_weight=0.04,
        direction_multiplier=1.0,
        trend_definition_hash=TrendEngine._definition_hash({"id": "trend-a"}),
        credibility_score=0.8,
        corroboration_factor=0.33,
        novelty_score=1.0,
        evidence_age_days=0.0,
        temporal_decay_factor=1.0,
        severity_score=0.5,
        confidence_score=0.6,
        delta_log_odds=delta,
        reasoning=reasoning,
    )


def test_reconciliation_helper_primitives_cover_guard_paths() -> None:
    no_id_trend = SimpleNamespace(id=None)
    desired_without_id = _desired(trend=no_id_trend)
    with pytest.raises(ValueError, match="must have an id"):
        _ = desired_without_id.key

    assert parse_trend_impact("bad") is None
    parsed = parse_trend_impact(
        {
            "trend_id": " trend-a ",
            "signal_type": " military_movement ",
            "direction": "escalatory",
            "severity": 2,
            "confidence": -1,
            "rationale": " rationale ",
        }
    )
    assert parsed == ParsedTrendImpact(
        trend_id="trend-a",
        signal_type="military_movement",
        direction="escalatory",
        severity=1.0,
        confidence=0.0,
        rationale="rationale",
    )
    assert impact_reasoning(parsed) == "rationale"
    assert (
        impact_reasoning(
            ParsedTrendImpact(
                trend_id="trend-a",
                signal_type="signal",
                direction="de_escalatory",
                severity=0.4,
                confidence=0.5,
                rationale=None,
            )
        )
        == "Tier 2 classified signal as de_escalatory"
    )

    trend = SimpleNamespace(id=uuid4(), definition={"id": "trend-a"}, runtime_trend_id="trend-a")
    desired = _desired(trend=trend)
    evidence = _evidence(trend_id=trend.id, event_id=uuid4())
    assert _evidence_matches(
        evidence,
        desired,
        desired_hash=TrendEngine._definition_hash(trend.definition),
    )
    assert _float_matches(None, None) is True
    assert _float_matches(None, 1.0) is False
    assert _float_matches(1.0, 1.0) is True
    assert _taxonomy_gap_details(parsed) == {
        "direction": "escalatory",
        "severity": 1.0,
        "confidence": 0.0,
        "rationale": "rationale",
    }

    entry = _lineage_entry(
        evidence=evidence,
        trend_runtime_id="trend-a",
        invalidated_at=datetime.now(tz=UTC),
        replacement=desired,
        change_type="replaced",
    )
    assert entry["replacement"]["trend_id"] == "trend-a"


@pytest.mark.asyncio
async def test_reconciliation_helper_storage_paths_cover_async_and_lookup_branches() -> None:
    event_id = uuid4()
    trend_id = uuid4()
    trend = SimpleNamespace(
        id=trend_id,
        name="Trend A",
        runtime_trend_id="trend-a",
        current_log_odds=0.1,
    )
    evidence = _evidence(trend_id=trend_id, event_id=event_id)
    session = AsyncMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=trend)
    session.scalars = AsyncMock(
        return_value=SimpleNamespace(all=AsyncMock(return_value=[evidence]))
    )
    trend_engine = SimpleNamespace(apply_log_odds_delta=AsyncMock(return_value=(0.1, 0.2)))

    loaded = await _load_active_event_evidence(session=session, event_id=event_id)
    assert loaded == [evidence]

    loaded_trend = await _trend_for_evidence(
        session=session,
        evidence=evidence,
        trend_by_uuid={},
    )
    assert loaded_trend is trend

    no_id_trend = SimpleNamespace(id=None)
    session.get = AsyncMock(return_value=no_id_trend)
    uncached = {}
    loaded_trend = await _trend_for_evidence(
        session=session,
        evidence=evidence,
        trend_by_uuid=uncached,
    )
    assert loaded_trend is no_id_trend
    assert uncached == {}
    session.get = AsyncMock(return_value=trend)

    delta = await _invalidate_existing_match(
        session=session,
        trend_engine=trend_engine,
        evidence=evidence,
        trend_by_uuid={},
        invalidated_at=datetime.now(tz=UTC),
    )
    assert delta == pytest.approx(0.01)

    with pytest.raises(ValueError, match="not found while reconciling"):
        await _invalidate_active_evidence(
            session=session,
            trend_engine=trend_engine,
            evidence=_evidence(trend_id=trend_id, event_id=event_id),
            trend=None,
            invalidated_at=datetime.now(tz=UTC),
        )

    zero_delta_evidence = _evidence(trend_id=trend_id, event_id=event_id, delta=0.0)
    trend_engine.apply_log_odds_delta.reset_mock()
    zero_delta = await _invalidate_active_evidence(
        session=session,
        trend_engine=trend_engine,
        evidence=zero_delta_evidence,
        trend=trend,
        invalidated_at=datetime.now(tz=UTC),
    )
    assert zero_delta == pytest.approx(0.0)
    assert zero_delta_evidence.is_invalidated is True
    trend_engine.apply_log_odds_delta.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliation_helper_replaces_and_removes_evidence_rows() -> None:
    event_id = uuid4()
    trend_id = uuid4()
    trend = SimpleNamespace(
        id=trend_id,
        name="Trend A",
        definition={"id": "trend-a"},
        runtime_trend_id="trend-a",
        current_log_odds=0.1,
    )
    session = AsyncMock()
    session.flush = AsyncMock()
    trend_engine = SimpleNamespace(
        apply_log_odds_delta=AsyncMock(return_value=(0.1, 0.2)),
        apply_evidence=AsyncMock(return_value=SimpleNamespace(delta_applied=0.02)),
    )

    existing = _evidence(trend_id=trend_id, event_id=event_id)
    desired = _desired(trend=trend, reasoning="updated reasoning")
    updates, lineage = await _invalidate_absent_evidence(
        session=session,
        trend_engine=trend_engine,
        active_by_key={(trend_id, "military_movement"): existing},
        trend_by_uuid={trend_id: trend},
        invalidated_at=datetime.now(tz=UTC),
    )
    assert updates == 1
    assert lineage[0]["change_type"] == "removed"

    zero_delta_existing = _evidence(trend_id=trend_id, event_id=event_id, delta=0.0)
    zero_delta_updates, zero_delta_lineage = await _invalidate_absent_evidence(
        session=session,
        trend_engine=trend_engine,
        active_by_key={(trend_id, "military_movement"): zero_delta_existing},
        trend_by_uuid={trend_id: trend},
        invalidated_at=datetime.now(tz=UTC),
    )
    assert zero_delta_updates == 0
    assert zero_delta_lineage[0]["change_type"] == "removed"

    replacing = _evidence(
        trend_id=trend_id,
        event_id=event_id,
        delta=0.02,
        reasoning="stale reasoning",
    )
    replacing.trend_definition_hash = TrendEngine._definition_hash({"id": "trend-a", "v": 0})
    trend_engine.apply_evidence.return_value = SimpleNamespace(delta_applied=0.0)
    updates, lineage = await _reconcile_desired_evidence(
        session=session,
        trend_engine=trend_engine,
        event_id=event_id,
        desired_by_key={desired.key: desired},
        active_by_key={(trend_id, "military_movement"): replacing},
        trend_by_uuid={trend_id: trend},
        invalidated_at=datetime.now(tz=UTC),
    )
    assert updates == 1
    assert lineage[0]["change_type"] == "replaced"
    assert lineage[0]["replacement"]["trend_id"] == "trend-a"

    matching = _evidence(trend_id=trend_id, event_id=event_id)
    updates, lineage = await _reconcile_desired_evidence(
        session=session,
        trend_engine=trend_engine,
        event_id=event_id,
        desired_by_key={
            desired.key: DesiredTrendEvidence(**{**desired.__dict__, "reasoning": "because"})
        },
        active_by_key={(trend_id, "military_movement"): matching},
        trend_by_uuid={trend_id: trend},
        invalidated_at=datetime.now(tz=UTC),
    )
    assert updates == 0
    assert lineage == []


@pytest.mark.asyncio
async def test_reconcile_event_trend_impacts_handles_non_list_and_history_append() -> None:
    event_id = uuid4()
    trend_id = uuid4()
    trend = SimpleNamespace(
        id=trend_id,
        name="Trend A",
        definition={"id": "trend-a"},
        runtime_trend_id="trend-a",
        current_log_odds=0.1,
    )
    evidence = _evidence(trend_id=trend_id, event_id=event_id)
    session = AsyncMock()
    session.flush = AsyncMock()
    session.scalars = AsyncMock(
        side_effect=[
            SimpleNamespace(all=lambda: [evidence]),
            SimpleNamespace(all=list),
        ]
    )
    trend_engine = SimpleNamespace(apply_log_odds_delta=AsyncMock(return_value=(0.1, 0.0)))
    callbacks = {
        "load_event_source_credibility": AsyncMock(return_value=0.8),
        "load_corroboration_score": AsyncMock(return_value=1.0),
        "load_novelty_score": AsyncMock(return_value=1.0),
        "capture_taxonomy_gap": AsyncMock(return_value=None),
    }

    event = Event(id=event_id, extracted_claims={"trend_impacts": []})
    seen, updates = await reconcile_event_trend_impacts(
        session=session,
        trend_engine=trend_engine,
        event=event,
        trends=[trend],
        **callbacks,
    )
    assert seen == 0
    assert updates == 1
    assert "_trend_impact_reconciliation" in (event.extracted_claims or {})

    non_list_event = Event(id=uuid4(), extracted_claims={"trend_impacts": "bad"})
    assert await reconcile_event_trend_impacts(
        session=session,
        trend_engine=trend_engine,
        event=non_list_event,
        trends=[trend],
        **callbacks,
    ) == (0, 0)

    _append_reconciliation_history(
        event=Event(id=uuid4(), extracted_claims={}),
        invalidated_at=datetime.now(tz=UTC),
        lineage_entries=[{"change_type": "removed"}],
    )
