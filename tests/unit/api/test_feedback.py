from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.feedback import (
    EventFeedbackRequest,
    TrendOverrideRequest,
    create_event_feedback,
    create_trend_override,
    list_feedback,
)
from src.storage.models import Event, HumanFeedback, Trend, TrendEvidence

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
async def test_create_event_feedback_invalidates_evidence_and_reverts_trends(
    mock_db_session,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Contradictory claims surfaced")
    trend = Trend(
        id=uuid4(),
        name="EU-Russia",
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
        signal_type="military_movement",
        delta_log_odds=0.2,
    )
    evidence_two = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=event.id,
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
    assert mock_db_session.delete.await_count == 2
    assert result.action == "invalidate"
    assert result.original_value is not None
    assert result.original_value["evidence_count"] == 2


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
async def test_create_trend_override_returns_404_for_unknown_trend(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc:
        await create_trend_override(
            trend_id=uuid4(),
            payload=TrendOverrideRequest(delta_log_odds=0.1),
            session=mock_db_session,
        )

    assert exc.value.status_code == 404
