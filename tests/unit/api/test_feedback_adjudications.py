from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

import src.api.routes._feedback_write_mutations as feedback_mutations_module
import src.api.routes.feedback as feedback_module
import src.api.routes.feedback_adjudication_helpers as adjudication_module
from src.api.routes._feedback_write_mutations import FeedbackMutationResult
from src.api.routes._privileged_write_contract import event_revision_token
from src.api.routes.event_review_metadata import EventReviewMetadata
from src.api.routes.feedback import create_event_adjudication, list_review_queue
from src.api.routes.feedback_event_helpers import (
    _claim_graph_contradiction_links,
    _contradiction_risk,
    _uncertainty_score,
)
from src.api.routes.feedback_models import EventAdjudicationRequest
from src.storage.models import Event, HumanFeedback, Trend

pytestmark = pytest.mark.unit


def _mock_request() -> object:
    return SimpleNamespace()


@pytest.mark.asyncio
async def test_create_event_adjudication_confirm_records_feedback_link(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Needs operator confirmation",
        lifecycle_status="confirmed",
    )
    feedback = HumanFeedback(
        id=uuid4(),
        target_type="event",
        target_id=event.id,
        action="pin",
        corrected_value={"kept": True},
        created_by="analyst@horadus",
    )
    mock_db_session.get.return_value = event
    monkeypatch.setattr(
        adjudication_module,
        "apply_event_feedback_mutation",
        AsyncMock(
            return_value=FeedbackMutationResult(
                feedback=feedback,
                target_revision_token="event-rev-2",
                result_links={
                    "event_id": str(event.id),
                    "feedback_id": str(feedback.id),
                },
            )
        ),
    )
    monkeypatch.setattr(
        adjudication_module,
        "load_event_review_metadata",
        AsyncMock(return_value={event.id: EventReviewMetadata(open_taxonomy_gap_count=2)}),
    )

    result = await create_event_adjudication(
        event_id=event.id,
        payload=EventAdjudicationRequest(
            outcome="confirm",
            notes="Analyst confirmed the cluster.",
            created_by="analyst@horadus",
        ),
        session=mock_db_session,
    )

    assert result.event_id == event.id
    assert result.feedback_id == feedback.id
    assert result.outcome == "confirm"
    assert result.review_status == "resolved"
    assert result.override_intent == "pin_event"
    assert result.resulting_effect["feedback_action"] == "pin"
    assert result.resulting_effect["open_taxonomy_gap_count"] == 2
    assert result.target_revision_token == "event-rev-2"


@pytest.mark.asyncio
async def test_create_event_adjudication_returns_404_when_event_missing(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    mock_db_session.get.return_value = None
    rejection = AsyncMock()
    monkeypatch.setattr(feedback_module, "record_privileged_write_rejection", rejection)

    with pytest.raises(HTTPException, match="not found") as exc:
        await create_event_adjudication(
            event_id=event_id,
            payload=EventAdjudicationRequest(
                outcome="confirm",
                created_by="analyst@horadus",
            ),
            request=_mock_request(),
            session=mock_db_session,
        )

    assert exc.value.status_code == 404
    rejection.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_event_adjudication_mutation_escalation_skips_feedback(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Needs taxonomy review")
    apply_feedback = AsyncMock()
    monkeypatch.setattr(adjudication_module, "apply_event_feedback_mutation", apply_feedback)
    monkeypatch.setattr(
        adjudication_module,
        "load_event_review_metadata",
        AsyncMock(return_value={}),
    )

    result = await adjudication_module.apply_event_adjudication_mutation(
        session=mock_db_session,
        event_id=event.id,
        event=event,
        payload=EventAdjudicationRequest(
            outcome="escalate_taxonomy_review",
            created_by="analyst@horadus",
        ),
    )

    apply_feedback.assert_not_awaited()
    assert result.adjudication.review_status == "needs_taxonomy_review"
    assert result.adjudication.feedback_id is None
    assert result.target_revision_token == event_revision_token(event)
    assert "feedback_id" not in result.result_links


@pytest.mark.asyncio
async def test_apply_event_adjudication_mutation_preserves_linked_restatement_ids(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Needs restatement")
    feedback = HumanFeedback(
        id=uuid4(),
        target_type="event",
        target_id=event.id,
        action="restate",
        corrected_value=None,
    )
    monkeypatch.setattr(
        adjudication_module,
        "apply_event_feedback_mutation",
        AsyncMock(
            return_value=FeedbackMutationResult(
                feedback=feedback,
                target_revision_token="event-rev-3",
                result_links={"restatement_ids": ["restatement-1"]},
            )
        ),
    )
    monkeypatch.setattr(
        adjudication_module,
        "load_event_review_metadata",
        AsyncMock(return_value={event.id: EventReviewMetadata()}),
    )

    result = await adjudication_module.apply_event_adjudication_mutation(
        session=mock_db_session,
        event_id=event.id,
        event=event,
        payload=EventAdjudicationRequest(
            outcome="restate",
            created_by="analyst@horadus",
        ),
    )

    assert "feedback_effect" not in result.adjudication.resulting_effect
    assert result.adjudication.resulting_effect["restatement_ids"] == ["restatement-1"]
    assert result.result_links["restatement_ids"] == ["restatement-1"]


@pytest.mark.asyncio
async def test_list_review_queue_filters_by_review_status_and_reason(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(tz=UTC)
    trend = Trend(
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
    resolved_event = Event(
        id=uuid4(),
        canonical_summary="Already resolved",
        lifecycle_status="confirmed",
        source_count=2,
        unique_source_count=2,
    )
    escalated_event = Event(
        id=uuid4(),
        canonical_summary="Needs taxonomy follow-up",
        lifecycle_status="confirmed",
        source_count=3,
        unique_source_count=2,
    )
    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [resolved_event, escalated_event]
    )
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                (
                    resolved_event.id,
                    trend.id,
                    trend.name,
                    "military_movement",
                    0.2,
                    0.7,
                    0.6,
                ),
                (
                    escalated_event.id,
                    trend.id,
                    trend.name,
                    "sanctions",
                    0.3,
                    0.45,
                    0.4,
                ),
            ]
        ),
        SimpleNamespace(all=list),
    ]
    monkeypatch.setattr(
        feedback_module,
        "load_event_review_metadata",
        AsyncMock(
            return_value={
                resolved_event.id: EventReviewMetadata(
                    review_status="resolved",
                    adjudication_count=1,
                ),
                escalated_event.id: EventReviewMetadata(
                    review_status="needs_taxonomy_review",
                    open_taxonomy_gap_count=2,
                    latest_adjudication_outcome="escalate_taxonomy_review",
                    latest_adjudication_at=now,
                    adjudication_count=1,
                ),
            }
        ),
    )

    result = await list_review_queue(
        limit=10,
        review_status="needs_taxonomy_review",
        queue_reason="taxonomy_gap",
        unreviewed_only=False,
        session=mock_db_session,
    )

    assert len(result) == 1
    assert result[0].event_id == escalated_event.id
    assert result[0].review_status == "needs_taxonomy_review"
    assert result[0].open_taxonomy_gap_count == 2
    assert result[0].latest_adjudication_outcome == "escalate_taxonomy_review"
    assert "taxonomy_gap" in result[0].queue_reason_codes


@pytest.mark.asyncio
async def test_trend_map_returns_empty_for_no_ids(mock_db_session) -> None:
    result = await feedback_mutations_module._trend_map(
        session=mock_db_session,
        trend_ids=set(),
    )

    assert result == {}


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
