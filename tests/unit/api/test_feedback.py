from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

import src.api.routes.feedback as feedback_module
from src.api.routes.feedback import (
    EventFeedbackRequest,
    EventRestatementTarget,
    TaxonomyGapUpdateRequest,
    TrendOverrideRequest,
    _claim_graph_contradiction_links,
    _contradiction_risk,
    _uncertainty_score,
    create_event_feedback,
    create_trend_override,
    list_feedback,
    list_review_queue,
    list_taxonomy_gaps,
    update_taxonomy_gap,
)
from src.storage.models import (
    Event,
    HumanFeedback,
    TaxonomyGap,
    TaxonomyGapReason,
    TaxonomyGapStatus,
    Trend,
    TrendEvidence,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_list_feedback_returns_records(mock_db_session) -> None:
    record = HumanFeedback(
        id=uuid4(),
        target_type="event",
        target_id=uuid4(),
        action="pin",
        notes="Pinned for analyst watch",
        created_by="analyst@horadus",
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [record])

    result = await list_feedback(limit=20, session=mock_db_session)

    assert len(result) == 1
    assert result[0].target_type == "event"
    assert result[0].action == "pin"


@pytest.mark.asyncio
async def test_list_feedback_applies_optional_filters(mock_db_session) -> None:
    record = HumanFeedback(
        id=uuid4(),
        target_type="trend",
        target_id=uuid4(),
        action="override_delta",
        notes="Manual adjustment",
        created_by="analyst@horadus",
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [record])

    result = await list_feedback(
        target_type="trend",
        action="override_delta",
        limit=5,
        session=mock_db_session,
    )

    assert len(result) == 1
    assert result[0].target_type == "trend"
    assert result[0].action == "override_delta"

    result = await list_feedback(
        target_type="trend",
        action=None,
        limit=5,
        session=mock_db_session,
    )
    assert len(result) == 1

    result = await list_feedback(
        target_type=None,
        action="override_delta",
        limit=5,
        session=mock_db_session,
    )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_create_event_feedback_marks_noise_and_archives_event(mock_db_session) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Routine duplicate chatter",
        lifecycle_status="confirmed",
    )
    mock_db_session.get.return_value = event

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(
            action="mark_noise",
            notes="Analyst marked as noise.",
            created_by="analyst@horadus",
        ),
        session=mock_db_session,
    )

    assert event.lifecycle_status == "archived"
    assert result.action == "mark_noise"
    assert result.corrected_value is not None
    assert result.corrected_value["lifecycle_status"] == "archived"


@pytest.mark.asyncio
async def test_create_event_feedback_pin_records_feedback_without_mutation(mock_db_session) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Analyst pin candidate",
        lifecycle_status="confirmed",
    )
    mock_db_session.get.return_value = event

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(
            action="pin",
            notes="Pin for watchlist.",
            created_by="analyst@horadus",
        ),
        session=mock_db_session,
    )

    assert event.lifecycle_status == "confirmed"
    assert result.action == "pin"
    assert result.original_value is None
    assert result.corrected_value is None


@pytest.mark.asyncio
async def test_create_event_feedback_invalidates_evidence_and_reverts_trends(
    mock_db_session,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Contradictory claims surfaced")
    trend = Trend(
        id=uuid4(),
        name="EU-Russia",
        runtime_trend_id="eu-russia",
        definition={"id": "eu-russia"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    evidence_one = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.2,
    )
    evidence_two = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="diplomatic_breakdown",
        delta_log_odds=0.1,
    )

    mock_db_session.get.return_value = event
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence_one, evidence_two]),
        SimpleNamespace(all=lambda: [trend]),
    ]

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(action="invalidate", created_by="analyst@horadus"),
        session=mock_db_session,
    )

    assert float(trend.current_log_odds) == pytest.approx(-1.3)
    assert evidence_one.is_invalidated is True
    assert evidence_two.is_invalidated is True
    assert evidence_one.invalidated_at is not None
    assert evidence_two.invalidated_at is not None
    assert mock_db_session.delete.await_count == 0
    assert result.action == "invalidate"
    assert result.original_value is not None
    assert result.original_value["evidence_count"] == 2
    assert result.corrected_value is not None
    assert result.corrected_value["invalidated_evidence_count"] == 2


@pytest.mark.asyncio
async def test_create_event_feedback_invalidate_handles_missing_trend_rows(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Missing trend row")
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=uuid4(),
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.4,
    )

    class FakeTrendEngine:
        def __init__(self, *, session) -> None:
            assert session is mock_db_session

        async def apply_log_odds_delta(
            self,
            *,
            trend_id,
            trend_name,
            delta,
            reason,
            fallback_current_log_odds,
        ) -> tuple[float, float]:
            assert trend_id == evidence.trend_id
            assert trend_name is None
            assert delta == pytest.approx(-0.4)
            assert reason == "event_invalidation"
            assert fallback_current_log_odds is None
            return (0.2, -0.2)

    monkeypatch.setattr(feedback_module, "TrendEngine", FakeTrendEngine)
    mock_db_session.get.return_value = event
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=list),
    ]

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(action="invalidate", created_by="analyst@horadus"),
        session=mock_db_session,
    )

    assert evidence.is_invalidated is True
    assert result.corrected_value is not None
    adjustment = result.corrected_value["trend_adjustments"][str(evidence.trend_id)]
    assert adjustment["previous_log_odds"] == pytest.approx(0.2)
    assert adjustment["new_log_odds"] == pytest.approx(-0.2)


@pytest.mark.asyncio
async def test_create_event_feedback_invalidate_reverses_only_net_remaining_delta(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Restated evidence later invalidated")
    trend = Trend(
        id=uuid4(),
        name="EU-Russia",
        runtime_trend_id="eu-russia",
        definition={"id": "eu-russia"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.4,
    )
    applied: list[dict[str, object]] = []

    async def _fake_apply(**kwargs):
        applied.append(kwargs)
        trend.current_log_odds = -1.2
        trend.updated_at = datetime.now(tz=UTC)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(feedback_module, "apply_compensating_restatement", _fake_apply)
    monkeypatch.setattr(
        feedback_module,
        "load_prior_compensation_by_evidence_id",
        AsyncMock(return_value={evidence.id: -0.2}),
    )
    mock_db_session.get.return_value = event
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=lambda: [trend]),
    ]

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(action="invalidate", created_by="analyst@horadus"),
        session=mock_db_session,
    )

    assert len(applied) == 1
    assert applied[0]["compensation_delta_log_odds"] == pytest.approx(-0.2)
    assert result.corrected_value is not None
    assert result.corrected_value["total_compensation_delta_log_odds"] == pytest.approx(-0.2)


@pytest.mark.asyncio
async def test_create_event_feedback_invalidate_without_active_evidence(
    mock_db_session,
) -> None:
    event = Event(id=uuid4(), canonical_summary="No active evidence")
    mock_db_session.get.return_value = event
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(action="invalidate", created_by="analyst@horadus"),
        session=mock_db_session,
    )

    assert result.corrected_value is not None
    assert result.corrected_value["affected_trend_count"] == 0
    assert result.corrected_value["invalidated_evidence_count"] == 0
    assert result.corrected_value["trend_adjustments"] == {}


@pytest.mark.asyncio
async def test_create_event_feedback_invalidate_skips_missing_trend_adjustment_on_value_error(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Missing trend row")
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=uuid4(),
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.4,
    )

    class FakeTrendEngine:
        def __init__(self, *, session) -> None:
            assert session is mock_db_session

        async def apply_log_odds_delta(self, **kwargs) -> tuple[float, float]:
            raise ValueError("missing trend")

    monkeypatch.setattr(feedback_module, "TrendEngine", FakeTrendEngine)
    mock_db_session.get.return_value = event
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=list),
    ]

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(action="invalidate"),
        session=mock_db_session,
    )

    assert evidence.is_invalidated is True
    assert result.corrected_value is not None
    assert result.corrected_value["trend_adjustments"] == {}
    assert result.corrected_value["total_compensation_delta_log_odds"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_create_event_feedback_restate_preserves_evidence_and_records_compensation(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Partial correction")
    trend = Trend(
        id=uuid4(),
        name="EU-Russia",
        runtime_trend_id="eu-russia",
        definition={"id": "eu-russia"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.4,
    )
    applied: list[dict[str, object]] = []

    async def _fake_apply(**kwargs):
        applied.append(kwargs)
        trend.current_log_odds = -1.2
        trend.updated_at = datetime.now(tz=UTC)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(feedback_module, "apply_compensating_restatement", _fake_apply)
    mock_db_session.get.return_value = event
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=lambda: [trend]),
    ]

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(
            action="restate",
            notes="Analyst reduced confidence impact.",
            restatement_targets=[
                EventRestatementTarget(
                    evidence_id=evidence.id,
                    compensation_delta_log_odds=-0.2,
                    notes="Only half the original impact remains.",
                )
            ],
        ),
        session=mock_db_session,
    )

    assert evidence.is_invalidated is not True
    assert len(applied) == 1
    assert applied[0]["restatement_kind"] == "partial_restatement"
    assert applied[0]["compensation_delta_log_odds"] == pytest.approx(-0.2)
    assert result.corrected_value is not None
    assert result.corrected_value["total_compensation_delta_log_odds"] == pytest.approx(-0.2)
    assert result.corrected_value["historical_artifact_policy"] == "belief_at_time"


@pytest.mark.asyncio
async def test_create_event_feedback_restate_requires_targets(mock_db_session) -> None:
    event = Event(id=uuid4(), canonical_summary="Partial correction")
    mock_db_session.get.return_value = event
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    with pytest.raises(HTTPException, match="restate requires at least one") as exc:
        await create_event_feedback(
            event_id=event.id,
            payload=EventFeedbackRequest(action="restate"),
            session=mock_db_session,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_event_feedback_restate_rejects_unknown_targets(mock_db_session) -> None:
    event = Event(id=uuid4(), canonical_summary="Partial correction")
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=uuid4(),
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.2,
    )
    mock_db_session.get.return_value = event
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [evidence])

    with pytest.raises(HTTPException, match="must reference active evidence") as exc:
        await create_event_feedback(
            event_id=event.id,
            payload=EventFeedbackRequest(
                action="restate",
                restatement_targets=[
                    EventRestatementTarget(
                        evidence_id=uuid4(),
                        compensation_delta_log_odds=-0.1,
                    )
                ],
            ),
            session=mock_db_session,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_event_feedback_restate_rejects_duplicate_targets(mock_db_session) -> None:
    event = Event(id=uuid4(), canonical_summary="Partial correction")
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=uuid4(),
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.2,
    )
    mock_db_session.get.return_value = event
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [evidence])

    with pytest.raises(HTTPException, match="must not contain duplicate evidence_id") as exc:
        await create_event_feedback(
            event_id=event.id,
            payload=EventFeedbackRequest(
                action="restate",
                restatement_targets=[
                    EventRestatementTarget(
                        evidence_id=evidence.id,
                        compensation_delta_log_odds=-0.1,
                    ),
                    EventRestatementTarget(
                        evidence_id=evidence.id,
                        compensation_delta_log_odds=-0.05,
                    ),
                ],
            ),
            session=mock_db_session,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_event_feedback_returns_404_for_unknown_event(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc:
        await create_event_feedback(
            event_id=uuid4(),
            payload=EventFeedbackRequest(action="pin"),
            session=mock_db_session,
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_trend_override_updates_log_odds(mock_db_session) -> None:
    trend = Trend(
        id=uuid4(),
        name="EU-Russia",
        runtime_trend_id="eu-russia",
        definition={"id": "eu-russia"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    mock_db_session.get.return_value = trend

    result = await create_trend_override(
        trend_id=trend.id,
        payload=TrendOverrideRequest(
            delta_log_odds=-0.25,
            notes="Manual correction",
            created_by="analyst@horadus",
        ),
        session=mock_db_session,
    )

    assert float(trend.current_log_odds) == pytest.approx(-1.25)
    assert trend.updated_at is not None
    assert result.action == "override_delta"
    assert result.corrected_value is not None
    assert result.corrected_value["new_log_odds"] == pytest.approx(-1.25)


@pytest.mark.asyncio
async def test_create_trend_override_records_manual_compensation_restatement(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend = Trend(
        id=uuid4(),
        name="Override Trend",
        runtime_trend_id="override-trend",
        definition={"id": "override-trend"},
        baseline_log_odds=-2.0,
        current_log_odds=-0.8,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    recorded: list[dict[str, object]] = []

    async def _fake_apply(**kwargs):
        recorded.append(kwargs)
        trend.current_log_odds = -0.9
        trend.updated_at = datetime.now(tz=UTC)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(feedback_module, "apply_compensating_restatement", _fake_apply)
    mock_db_session.get.return_value = trend

    result = await create_trend_override(
        trend_id=trend.id,
        payload=TrendOverrideRequest(delta_log_odds=-0.1, notes="Manual correction"),
        session=mock_db_session,
    )

    assert len(recorded) == 1
    assert recorded[0]["restatement_kind"] == "manual_compensation"
    assert recorded[0]["source"] == "trend_override"
    assert result.corrected_value is not None
    assert result.corrected_value["historical_artifact_policy"] == "belief_at_time"
    assert result.corrected_value["new_log_odds"] == pytest.approx(-0.9)


@pytest.mark.asyncio
async def test_create_trend_override_returns_404_for_unknown_trend(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc:
        await create_trend_override(
            trend_id=uuid4(),
            payload=TrendOverrideRequest(delta_log_odds=0.1),
            session=mock_db_session,
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_trend_map_returns_empty_for_no_ids(mock_db_session) -> None:
    result = await feedback_module._trend_map(session=mock_db_session, trend_ids=set())

    assert result == {}


@pytest.mark.asyncio
async def test_list_review_queue_orders_by_ranking_score(mock_db_session) -> None:
    trend = Trend(
        id=uuid4(),
        name="EU-Russia",
        runtime_trend_id="eu-russia",
        definition={"id": "eu-russia"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    low_event = Event(
        id=uuid4(),
        canonical_summary="Low-priority event",
        lifecycle_status="confirmed",
        source_count=4,
        unique_source_count=4,
        has_contradictions=False,
    )
    high_event = Event(
        id=uuid4(),
        canonical_summary="High-priority contradictory event",
        lifecycle_status="confirmed",
        source_count=3,
        unique_source_count=2,
        has_contradictions=True,
        extracted_claims={
            "claim_graph": {
                "links": [
                    {"relation": "contradict"},
                    {"relation": "contradict"},
                ]
            }
        },
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [low_event, high_event])
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                (
                    low_event.id,
                    trend.id,
                    trend.name,
                    "military_movement",
                    0.20,
                    0.95,
                    0.90,
                ),
                (
                    high_event.id,
                    trend.id,
                    trend.name,
                    "military_movement",
                    0.30,
                    0.40,
                    0.30,
                ),
            ]
        ),
        SimpleNamespace(all=list),
    ]

    result = await list_review_queue(days=7, limit=10, session=mock_db_session)

    assert len(result) == 2
    assert result[0].event_id == high_event.id
    assert result[0].ranking_score > result[1].ranking_score


@pytest.mark.asyncio
async def test_list_review_queue_filters_unreviewed_and_trend(mock_db_session) -> None:
    trend_a = Trend(
        id=uuid4(),
        name="Trend A",
        runtime_trend_id="trend-a",
        definition={"id": "trend-a"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    trend_b = Trend(
        id=uuid4(),
        name="Trend B",
        runtime_trend_id="trend-b",
        definition={"id": "trend-b"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    reviewed_event = Event(
        id=uuid4(),
        canonical_summary="Reviewed",
        lifecycle_status="confirmed",
        source_count=2,
        unique_source_count=2,
    )
    candidate_event = Event(
        id=uuid4(),
        canonical_summary="Needs review",
        lifecycle_status="confirmed",
        source_count=2,
        unique_source_count=2,
    )
    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [reviewed_event, candidate_event]
    )
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                (
                    reviewed_event.id,
                    trend_a.id,
                    trend_a.name,
                    "military_movement",
                    0.15,
                    0.70,
                    0.60,
                ),
                (
                    candidate_event.id,
                    trend_b.id,
                    trend_b.name,
                    "sanctions",
                    0.25,
                    0.55,
                    0.50,
                ),
            ]
        ),
        SimpleNamespace(all=lambda: [(reviewed_event.id, "pin")]),
    ]

    unreviewed = await list_review_queue(
        limit=10,
        trend_id=trend_b.id,
        unreviewed_only=True,
        session=mock_db_session,
    )

    assert len(unreviewed) == 1
    assert unreviewed[0].event_id == candidate_event.id
    assert unreviewed[0].feedback_count == 0

    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                (
                    candidate_event.id,
                    trend_b.id,
                    trend_b.name,
                    "sanctions",
                    0.25,
                    0.55,
                    0.50,
                ),
            ]
        ),
        SimpleNamespace(all=list),
    ]

    filtered = await list_review_queue(
        limit=10,
        trend_id=trend_b.id,
        unreviewed_only=False,
        session=mock_db_session,
    )

    assert len(filtered) == 1
    assert filtered[0].event_id == candidate_event.id


@pytest.mark.asyncio
async def test_list_review_queue_handles_empty_and_skipped_candidates(mock_db_session) -> None:
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)
    assert await list_review_queue(session=mock_db_session) == []

    event_without_id = Event(
        id=None,
        canonical_summary="Missing id",
        lifecycle_status="confirmed",
        source_count=1,
        unique_source_count=1,
    )
    event_without_evidence = Event(
        id=uuid4(),
        canonical_summary="No evidence",
        lifecycle_status="confirmed",
        source_count=1,
        unique_source_count=1,
    )
    zero_delta_event = Event(
        id=uuid4(),
        canonical_summary="Zero delta evidence",
        lifecycle_status="confirmed",
        source_count=1,
        unique_source_count=1,
    )
    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [event_without_id, event_without_evidence, zero_delta_event]
    )
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                ("not-a-uuid", uuid4(), "Trend", "signal", 1.0, 0.9, 0.8),
                (zero_delta_event.id, uuid4(), "Trend", "signal", 0.0, 0.9, 0.8),
            ]
        ),
        SimpleNamespace(all=lambda: [("not-a-uuid", 1)]),
    ]

    assert await list_review_queue(session=mock_db_session) == []

    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [Event(id=None, canonical_summary="None", lifecycle_status="confirmed")]
    )
    mock_db_session.execute.side_effect = []
    assert await list_review_queue(session=mock_db_session) == []


@pytest.mark.asyncio
async def test_list_review_queue_without_trend_filter_keeps_base_evidence_query(
    mock_db_session,
) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Candidate",
        lifecycle_status="confirmed",
        source_count=1,
        unique_source_count=1,
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [event])
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                (event.id, uuid4(), "Trend", "signal", 0.2, 0.8, 0.9),
            ]
        ),
        SimpleNamespace(all=list),
    ]

    result = await list_review_queue(
        trend_id=None,
        unreviewed_only=False,
        session=mock_db_session,
    )

    evidence_query = str(mock_db_session.execute.await_args_list[0].args[0]).lower()
    assert "trend_evidence.trend_id =" not in evidence_query
    assert len(result) == 1


@pytest.mark.asyncio
async def test_list_taxonomy_gaps_returns_summary_and_top_unknown_signals(
    mock_db_session,
) -> None:
    first_gap = TaxonomyGap(
        id=uuid4(),
        event_id=uuid4(),
        trend_id="eu-russia",
        signal_type="unknown_signal",
        reason=TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE,
        status=TaxonomyGapStatus.OPEN,
        details={"direction": "escalatory"},
    )
    second_gap = TaxonomyGap(
        id=uuid4(),
        event_id=uuid4(),
        trend_id="unknown-trend",
        signal_type="military_movement",
        reason=TaxonomyGapReason.UNKNOWN_TREND_ID,
        status=TaxonomyGapStatus.RESOLVED,
        details={"direction": "escalatory"},
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [first_gap, second_gap])
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                (TaxonomyGapStatus.OPEN, TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE, 3),
                (TaxonomyGapStatus.RESOLVED, TaxonomyGapReason.UNKNOWN_TREND_ID, 2),
            ]
        ),
        SimpleNamespace(all=lambda: [("eu-russia", "unknown_signal", 3)]),
    ]

    result = await list_taxonomy_gaps(days=7, limit=20, session=mock_db_session)

    assert result.total_count == 5
    assert result.open_count == 3
    assert result.resolved_count == 2
    assert result.rejected_count == 0
    assert result.unknown_signal_count == 3
    assert result.unknown_trend_count == 2
    assert result.top_unknown_signal_keys_by_trend[0].trend_id == "eu-russia"
    assert result.top_unknown_signal_keys_by_trend[0].signal_type == "unknown_signal"
    assert len(result.items) == 2


@pytest.mark.asyncio
async def test_list_taxonomy_gaps_applies_status_filter_and_ignores_unknown_buckets(
    mock_db_session,
) -> None:
    gap = TaxonomyGap(
        id=uuid4(),
        event_id=uuid4(),
        trend_id="eu-russia",
        signal_type="unknown_signal",
        reason=TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE,
        status=TaxonomyGapStatus.OPEN,
        details={},
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [gap])
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                (TaxonomyGapStatus.OPEN, TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE, 2),
                ("unknown", "other", 7),
            ]
        ),
        SimpleNamespace(all=list),
    ]

    result = await list_taxonomy_gaps(
        days=7,
        limit=20,
        status_filter="open",
        session=mock_db_session,
    )

    assert result.total_count == 9
    assert result.open_count == 2
    assert result.resolved_count == 0
    assert result.rejected_count == 0
    assert result.unknown_signal_count == 2
    assert result.unknown_trend_count == 0


@pytest.mark.asyncio
async def test_update_taxonomy_gap_sets_resolution_fields(mock_db_session) -> None:
    gap = TaxonomyGap(
        id=uuid4(),
        event_id=uuid4(),
        trend_id="eu-russia",
        signal_type="unknown_signal",
        reason=TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE,
        status=TaxonomyGapStatus.OPEN,
        details={},
    )
    mock_db_session.get.return_value = gap

    result = await update_taxonomy_gap(
        gap_id=gap.id,
        payload=TaxonomyGapUpdateRequest(
            status="resolved",
            resolution_notes="Added indicator mapping in trend config.",
            resolved_by="analyst@horadus",
        ),
        session=mock_db_session,
    )

    assert gap.status == TaxonomyGapStatus.RESOLVED
    assert gap.resolution_notes == "Added indicator mapping in trend config."
    assert gap.resolved_by == "analyst@horadus"
    assert gap.resolved_at is not None
    assert result.status == "resolved"


@pytest.mark.asyncio
async def test_update_taxonomy_gap_reopening_clears_resolution_fields(mock_db_session) -> None:
    gap = TaxonomyGap(
        id=uuid4(),
        event_id=uuid4(),
        trend_id="eu-russia",
        signal_type="unknown_signal",
        reason=TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE,
        status=TaxonomyGapStatus.RESOLVED,
        details={},
        resolution_notes="done",
        resolved_by="analyst@horadus",
    )
    gap.resolved_at = feedback_module.datetime.now(tz=feedback_module.UTC)
    mock_db_session.get.return_value = gap

    result = await update_taxonomy_gap(
        gap_id=gap.id,
        payload=TaxonomyGapUpdateRequest(status="open"),
        session=mock_db_session,
    )

    assert gap.status == TaxonomyGapStatus.OPEN
    assert gap.resolution_notes is None
    assert gap.resolved_by is None
    assert gap.resolved_at is None
    assert result.status == "open"


@pytest.mark.asyncio
async def test_update_taxonomy_gap_returns_404_when_missing(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc:
        await update_taxonomy_gap(
            gap_id=uuid4(),
            payload=TaxonomyGapUpdateRequest(status="resolved"),
            session=mock_db_session,
        )

    assert exc.value.status_code == 404


def test_feedback_helper_metrics_cover_guard_clauses() -> None:
    event = Event(canonical_summary="Test event", source_count=1, unique_source_count=1)
    assert _claim_graph_contradiction_links(event) == 0

    event.extracted_claims = {"claim_graph": []}
    assert _claim_graph_contradiction_links(event) == 0

    event.extracted_claims = {"claim_graph": {"links": "bad"}}
    assert _claim_graph_contradiction_links(event) == 0

    event.extracted_claims = {"claim_graph": {"links": [{"relation": "contradict"}]}}
    event.has_contradictions = True
    assert _claim_graph_contradiction_links(event) == 1
    assert _contradiction_risk(event) == pytest.approx(1.75)

    assert _uncertainty_score([]) == pytest.approx(0.551)
