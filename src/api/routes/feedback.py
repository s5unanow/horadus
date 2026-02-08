"""
Feedback API endpoints.

Human corrections and annotations for events and trends.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_session
from src.storage.models import Event, EventLifecycle, HumanFeedback, Trend, TrendEvidence

router = APIRouter()


class FeedbackResponse(BaseModel):
    """Serialized feedback record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: str
    target_id: UUID
    action: str
    original_value: dict[str, Any] | None
    corrected_value: dict[str, Any] | None
    notes: str | None
    created_by: str | None
    created_at: datetime


class EventFeedbackRequest(BaseModel):
    """Feedback actions supported for an event."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action": "invalidate",
                "notes": "Conflicting source narratives and analyst override.",
                "created_by": "analyst@horadus",
            }
        }
    )

    action: Literal["pin", "mark_noise", "invalidate"]
    notes: str | None = None
    created_by: str | None = None


class TrendOverrideRequest(BaseModel):
    """Manual trend delta override request."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "delta_log_odds": -0.12,
                "notes": "Manual correction after source invalidation.",
                "created_by": "analyst@horadus",
            }
        }
    )

    delta_log_odds: float = Field(..., description="Manual adjustment in log-odds space")
    notes: str | None = None
    created_by: str | None = None


def _to_feedback_response(feedback: HumanFeedback) -> FeedbackResponse:
    feedback_id = feedback.id if feedback.id is not None else uuid4()
    created_at = feedback.created_at if feedback.created_at is not None else datetime.now(tz=UTC)
    return FeedbackResponse(
        id=feedback_id,
        target_type=feedback.target_type,
        target_id=feedback.target_id,
        action=feedback.action,
        original_value=feedback.original_value,
        corrected_value=feedback.corrected_value,
        notes=feedback.notes,
        created_by=feedback.created_by,
        created_at=created_at,
    )


@router.get("/feedback", response_model=list[FeedbackResponse])
async def list_feedback(
    target_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[FeedbackResponse]:
    """
    List human feedback records.

    Supports optional filtering by target type and action.
    """
    query = select(HumanFeedback).order_by(HumanFeedback.created_at.desc()).limit(limit)
    if target_type is not None:
        query = query.where(HumanFeedback.target_type == target_type)
    if action is not None:
        query = query.where(HumanFeedback.action == action)

    records = list((await session.scalars(query)).all())
    return [_to_feedback_response(record) for record in records]


@router.post("/events/{event_id}/feedback", response_model=FeedbackResponse)
async def create_event_feedback(
    event_id: UUID,
    payload: EventFeedbackRequest,
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """
    Record event-level feedback (pin, mark_noise, invalidate).

    `invalidate` removes the event's trend-evidence contributions and
    adjusts affected trend log-odds accordingly.
    """
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found",
        )

    original_value: dict[str, Any] | None = None
    corrected_value: dict[str, Any] | None = None

    if payload.action == "mark_noise":
        original_value = {"lifecycle_status": event.lifecycle_status}
        event.lifecycle_status = EventLifecycle.ARCHIVED.value
        corrected_value = {"lifecycle_status": event.lifecycle_status}
    elif payload.action == "invalidate":
        evidences = list(
            (
                await session.scalars(
                    select(TrendEvidence)
                    .where(TrendEvidence.event_id == event_id)
                    .order_by(TrendEvidence.created_at.asc())
                )
            ).all()
        )
        trend_deltas: dict[UUID, float] = {}
        for evidence in evidences:
            trend_deltas[evidence.trend_id] = trend_deltas.get(evidence.trend_id, 0.0) + float(
                evidence.delta_log_odds
            )

        if trend_deltas:
            trends = list(
                (
                    await session.scalars(
                        select(Trend).where(Trend.id.in_(tuple(trend_deltas.keys())))
                    )
                ).all()
            )
            for trend in trends:
                trend_delta = trend_deltas.get(trend.id)
                if trend_delta is None:
                    continue
                trend.current_log_odds = float(trend.current_log_odds) - trend_delta

        for evidence in evidences:
            await session.delete(evidence)

        original_value = {
            "evidence_count": len(evidences),
            "trend_deltas": {str(trend_id): delta for trend_id, delta in trend_deltas.items()},
        }
        corrected_value = {
            "reverted_event_id": str(event_id),
            "affected_trend_count": len(trend_deltas),
        }

    feedback = HumanFeedback(
        target_type="event",
        target_id=event_id,
        action=payload.action,
        original_value=original_value,
        corrected_value=corrected_value,
        notes=payload.notes,
        created_by=payload.created_by,
    )
    session.add(feedback)
    await session.flush()
    return _to_feedback_response(feedback)


@router.post("/trends/{trend_id}/override", response_model=FeedbackResponse)
async def create_trend_override(
    trend_id: UUID,
    payload: TrendOverrideRequest,
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """
    Apply a manual trend delta override and record feedback audit trail.
    """
    trend = await session.get(Trend, trend_id)
    if trend is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trend '{trend_id}' not found",
        )

    previous_log_odds = float(trend.current_log_odds)
    new_log_odds = previous_log_odds + float(payload.delta_log_odds)
    trend.current_log_odds = new_log_odds
    trend.updated_at = datetime.now(tz=UTC)

    feedback = HumanFeedback(
        target_type="trend",
        target_id=trend_id,
        action="override_delta",
        original_value={"current_log_odds": previous_log_odds},
        corrected_value={
            "delta_log_odds": float(payload.delta_log_odds),
            "new_log_odds": new_log_odds,
        },
        notes=payload.notes,
        created_by=payload.created_by,
    )
    session.add(feedback)
    await session.flush()
    return _to_feedback_response(feedback)
