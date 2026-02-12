"""
Feedback API endpoints.

Human corrections and annotations for events and trends.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
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


class ReviewQueueTrendImpact(BaseModel):
    """Trend-impact summary included in review queue items."""

    trend_id: UUID
    trend_name: str
    signal_type: str
    delta_log_odds: float
    confidence_score: float | None


class ReviewQueueItem(BaseModel):
    """Ranked event candidate for analyst review."""

    event_id: UUID
    summary: str
    lifecycle_status: str
    last_mention_at: datetime
    source_count: int
    unique_source_count: int
    has_contradictions: bool
    contradiction_notes: str | None
    evidence_count: int
    projected_delta: float
    uncertainty_score: float
    contradiction_risk: float
    ranking_score: float
    feedback_count: int
    feedback_actions: list[str]
    requires_human_verification: bool
    trend_impacts: list[ReviewQueueTrendImpact]


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


def _claim_graph_contradiction_links(event: Event) -> int:
    if not isinstance(event.extracted_claims, dict):
        return 0
    claim_graph = event.extracted_claims.get("claim_graph")
    if not isinstance(claim_graph, dict):
        return 0
    links = claim_graph.get("links")
    if not isinstance(links, list):
        return 0
    return sum(
        1
        for link in links
        if isinstance(link, dict) and str(link.get("relation", "")).strip().lower() == "contradict"
    )


def _uncertainty_score(evidence_rows: list[tuple[Any, ...]]) -> float:
    confidences = [float(row[5]) for row in evidence_rows if row[5] is not None]
    corroborations = [float(row[6]) for row in evidence_rows if row[6] is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
    avg_corroboration = sum(corroborations) / len(corroborations) if corroborations else 0.33

    confidence_uncertainty = max(0.0, 1.0 - avg_confidence)
    corroboration_uncertainty = max(0.0, 1.0 - min(1.0, avg_corroboration))
    uncertainty = 0.7 * confidence_uncertainty + 0.3 * corroboration_uncertainty
    return max(0.1, min(1.0, uncertainty))


def _contradiction_risk(event: Event) -> float:
    link_count = _claim_graph_contradiction_links(event)
    risk = 1.0 + min(1.5, 0.25 * link_count)
    if event.has_contradictions:
        risk += 0.5
    return min(3.0, risk)


@router.get("/review-queue", response_model=list[ReviewQueueItem])
async def list_review_queue(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=50, ge=1, le=200),
    trend_id: UUID | None = Query(default=None),
    unreviewed_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> list[ReviewQueueItem]:
    """
    Return ranked analyst review candidates.

    Ranking formula:
    `uncertainty_score x projected_delta x contradiction_risk`
    """
    days_value = days if isinstance(days, int) else 7
    limit_value = limit if isinstance(limit, int) else 50
    unreviewed_only_value = unreviewed_only if isinstance(unreviewed_only, bool) else True

    since = datetime.now(tz=UTC) - timedelta(days=days_value)
    candidate_limit = min(1000, max(limit_value * 4, limit_value))

    events = list(
        (
            await session.scalars(
                select(Event)
                .where(Event.last_mention_at >= since)
                .order_by(Event.last_mention_at.desc())
                .limit(candidate_limit)
            )
        ).all()
    )
    if not events:
        return []

    event_ids = [event.id for event in events if event.id is not None]
    if not event_ids:
        return []

    evidence_query = (
        select(
            TrendEvidence.event_id,
            TrendEvidence.trend_id,
            Trend.name,
            TrendEvidence.signal_type,
            TrendEvidence.delta_log_odds,
            TrendEvidence.confidence_score,
            TrendEvidence.corroboration_factor,
        )
        .join(Trend, Trend.id == TrendEvidence.trend_id)
        .where(TrendEvidence.event_id.in_(tuple(event_ids)))
    )
    if trend_id is not None:
        evidence_query = evidence_query.where(TrendEvidence.trend_id == trend_id)
    evidence_rows = (await session.execute(evidence_query)).all()

    feedback_rows = (
        await session.execute(
            select(HumanFeedback.target_id, HumanFeedback.action)
            .where(HumanFeedback.target_type == "event")
            .where(HumanFeedback.target_id.in_(tuple(event_ids)))
            .order_by(HumanFeedback.created_at.desc())
        )
    ).all()

    evidence_by_event: dict[UUID, list[tuple[Any, ...]]] = defaultdict(list)
    for row in evidence_rows:
        event_id_value = row[0]
        if isinstance(event_id_value, UUID):
            evidence_by_event[event_id_value].append(tuple(row))

    feedback_by_event: dict[UUID, list[str]] = defaultdict(list)
    for target_id, action in feedback_rows:
        if isinstance(target_id, UUID) and isinstance(action, str):
            feedback_by_event[target_id].append(action)

    queue_items: list[ReviewQueueItem] = []
    for event in events:
        if event.id is None:
            continue
        event_evidence = evidence_by_event.get(event.id, [])
        if not event_evidence:
            continue

        feedback_actions = feedback_by_event.get(event.id, [])
        if unreviewed_only_value and feedback_actions:
            continue

        projected_delta = sum(abs(float(row[4])) for row in event_evidence)
        if projected_delta <= 0:
            continue

        uncertainty_score = _uncertainty_score(event_evidence)
        contradiction_risk = _contradiction_risk(event)
        ranking_score = uncertainty_score * projected_delta * contradiction_risk
        last_mention_at = event.last_mention_at or event.created_at or datetime.now(tz=UTC)

        impacts = sorted(
            (
                ReviewQueueTrendImpact(
                    trend_id=row[1],
                    trend_name=str(row[2]),
                    signal_type=str(row[3]),
                    delta_log_odds=float(row[4]),
                    confidence_score=float(row[5]) if row[5] is not None else None,
                )
                for row in event_evidence
            ),
            key=lambda impact: abs(impact.delta_log_odds),
            reverse=True,
        )

        queue_items.append(
            ReviewQueueItem(
                event_id=event.id,
                summary=event.canonical_summary,
                lifecycle_status=event.lifecycle_status,
                last_mention_at=last_mention_at,
                source_count=event.source_count,
                unique_source_count=event.unique_source_count,
                has_contradictions=bool(event.has_contradictions),
                contradiction_notes=event.contradiction_notes,
                evidence_count=len(event_evidence),
                projected_delta=projected_delta,
                uncertainty_score=uncertainty_score,
                contradiction_risk=contradiction_risk,
                ranking_score=ranking_score,
                feedback_count=len(feedback_actions),
                feedback_actions=feedback_actions,
                requires_human_verification=len(feedback_actions) == 0,
                trend_impacts=impacts[:3],
            )
        )

    queue_items.sort(
        key=lambda item: (
            -item.ranking_score,
            -item.projected_delta,
            -item.last_mention_at.timestamp(),
            str(item.event_id),
        )
    )
    return queue_items[:limit_value]


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
