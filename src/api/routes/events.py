"""
Events API endpoints.

Endpoints for querying clustered news events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_session
from src.storage.event_state import (
    resolved_corroboration_mode,
    resolved_corroboration_score,
    resolved_event_activity_state,
    resolved_event_epistemic_state,
    resolved_independent_evidence_count,
)
from src.storage.models import Event, EventClaim, EventItem, RawItem, Source, TrendEvidence

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class EventResponse(BaseModel):
    """Response body for an event."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "summary": "Border force movement observed across multiple sources.",
                "categories": ["military"],
                "source_count": 5,
                "unique_source_count": 4,
                "independent_evidence_count": 2,
                "corroboration_mode": "provenance_aware",
                "epistemic_state": "contested",
                "activity_state": "active",
                "lifecycle_status": "confirmed",
                "has_contradictions": True,
                "contradiction_notes": "Source A reports a withdrawal while Source B reports escalation.",
                "first_seen_at": "2026-02-07T12:10:00Z",
                "last_mention_at": "2026-02-07T15:25:00Z",
                "extracted_who": ["Country A", "Country B"],
                "extracted_what": "Military units repositioned near border.",
                "extracted_where": "Eastern sector",
            }
        }
    )

    id: UUID
    summary: str
    categories: list[str]
    source_count: int
    unique_source_count: int
    independent_evidence_count: int
    corroboration_mode: str
    epistemic_state: str
    activity_state: str
    lifecycle_status: str
    has_contradictions: bool
    contradiction_notes: str | None
    first_seen_at: datetime
    last_mention_at: datetime
    extracted_who: list[str] | None
    extracted_what: str | None
    extracted_where: str | None


class EventDetailResponse(EventResponse):
    """Detailed event response with sources."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "summary": "Border force movement observed across multiple sources.",
                "categories": ["military"],
                "source_count": 5,
                "unique_source_count": 4,
                "independent_evidence_count": 2,
                "corroboration_mode": "provenance_aware",
                "corroboration_score": 1.35,
                "first_seen_at": "2026-02-07T12:10:00Z",
                "extracted_who": ["Country A", "Country B"],
                "extracted_what": "Military units repositioned near border.",
                "extracted_where": "Eastern sector",
                "provenance_summary": {
                    "method": "provenance_aware",
                    "raw_source_count": 5,
                    "unique_source_count": 4,
                    "independent_evidence_count": 2,
                    "weighted_corroboration_score": 1.35,
                },
                "sources": [{"source_name": "Reuters", "url": "https://example.com/article-1"}],
                "trend_impacts": [
                    {
                        "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                    }
                ],
            }
        }
    )

    sources: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    trend_impacts: list[dict[str, Any]]
    corroboration_score: float
    provenance_summary: dict[str, Any]


# =============================================================================
# Endpoints
# =============================================================================


async def _load_event_detail_payloads(
    *,
    session: AsyncSession,
    event_id: UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    source_rows = (
        await session.execute(
            select(Source.name, RawItem.url)
            .join(RawItem, RawItem.source_id == Source.id)
            .join(EventItem, EventItem.item_id == RawItem.id)
            .where(EventItem.event_id == event_id)
            .order_by(Source.name.asc())
        )
    ).all()
    impact_rows = (
        await session.execute(
            select(
                TrendEvidence.trend_id,
                TrendEvidence.event_claim_id,
                EventClaim.claim_text,
                TrendEvidence.signal_type,
                TrendEvidence.delta_log_odds,
            )
            .join(EventClaim, EventClaim.id == TrendEvidence.event_claim_id)
            .where(TrendEvidence.event_id == event_id)
            .where(TrendEvidence.is_invalidated.is_(False))
            .order_by(TrendEvidence.created_at.desc())
        )
    ).all()
    claim_rows = (
        await session.execute(
            select(
                EventClaim.id,
                EventClaim.claim_key,
                EventClaim.claim_text,
                EventClaim.claim_type,
                EventClaim.is_active,
            )
            .where(EventClaim.event_id == event_id)
            .order_by(EventClaim.claim_order.asc(), EventClaim.created_at.asc())
        )
    ).all()
    sources = [
        {"source_name": source_name, "url": url}
        for source_name, url in source_rows
        if source_name is not None
    ]
    claims = [
        {
            "id": claim_id,
            "claim_key": claim_key,
            "claim_text": claim_text,
            "claim_type": claim_type,
            "is_active": is_active,
        }
        for claim_id, claim_key, claim_text, claim_type, is_active in claim_rows
    ]
    trend_impacts = [
        {
            "trend_id": trend_id,
            "event_claim_id": event_claim_id,
            "claim_text": claim_text,
            "signal_type": signal_type,
            "direction": "escalatory" if float(delta_log_odds) >= 0 else "de_escalatory",
        }
        for trend_id, event_claim_id, claim_text, signal_type, delta_log_odds in impact_rows
    ]
    return (sources, claims, trend_impacts)


@router.get("", response_model=list[EventResponse])
async def list_events(
    category: str | None = None,
    trend_id: UUID | None = None,
    epistemic: Literal["emerging", "confirmed", "contested", "retracted"] | None = None,
    activity: Literal["active", "dormant", "closed"] | None = None,
    lifecycle: Literal["emerging", "confirmed", "fading", "archived"] | None = None,
    contradicted: bool | None = Query(
        default=None,
        description="Filter contradicted events (true/false)",
    ),
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[EventResponse]:
    """
    List recent events.

    Can filter by category or by events affecting a specific trend.
    """
    since = datetime.now(tz=UTC) - timedelta(days=days)
    query = (
        select(Event)
        .where(Event.last_mention_at >= since)
        .order_by(Event.last_mention_at.desc())
        .limit(limit)
    )
    if epistemic is not None:
        query = query.where(Event.epistemic_state == epistemic)
    if activity is not None:
        query = query.where(Event.activity_state == activity)
    if lifecycle is not None:
        query = query.where(Event.lifecycle_status == lifecycle)
    if contradicted is not None:
        query = query.where(Event.has_contradictions.is_(contradicted))
    if category is not None:
        query = query.where(func.array_position(Event.categories, category).is_not(None))
    if trend_id is not None:
        query = query.where(
            exists(
                select(TrendEvidence.id).where(
                    TrendEvidence.event_id == Event.id,
                    TrendEvidence.trend_id == trend_id,
                    TrendEvidence.is_invalidated.is_(False),
                )
            )
        )

    events = list((await session.scalars(query)).all())
    return [
        EventResponse(
            id=event.id,
            summary=event.canonical_summary,
            categories=list(event.categories or []),
            source_count=event.source_count,
            unique_source_count=event.unique_source_count,
            independent_evidence_count=resolved_independent_evidence_count(event),
            corroboration_mode=resolved_corroboration_mode(event),
            epistemic_state=resolved_event_epistemic_state(event),
            activity_state=resolved_event_activity_state(event),
            lifecycle_status=event.lifecycle_status,
            has_contradictions=event.has_contradictions,
            contradiction_notes=event.contradiction_notes,
            first_seen_at=event.first_seen_at,
            last_mention_at=event.last_mention_at,
            extracted_who=list(event.extracted_who) if event.extracted_who else None,
            extracted_what=event.extracted_what,
            extracted_where=event.extracted_where,
        )
        for event in events
    ]


@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(
    event_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> EventDetailResponse:
    """
    Get detailed event information.

    Includes source articles and trend impacts.
    """
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found",
        )
    sources, claims, trend_impacts = await _load_event_detail_payloads(
        session=session,
        event_id=event_id,
    )
    return EventDetailResponse(
        id=event.id,
        summary=event.canonical_summary,
        categories=list(event.categories or []),
        source_count=event.source_count,
        unique_source_count=event.unique_source_count,
        independent_evidence_count=resolved_independent_evidence_count(event),
        corroboration_mode=resolved_corroboration_mode(event),
        epistemic_state=resolved_event_epistemic_state(event),
        activity_state=resolved_event_activity_state(event),
        lifecycle_status=event.lifecycle_status,
        has_contradictions=event.has_contradictions,
        contradiction_notes=event.contradiction_notes,
        first_seen_at=event.first_seen_at,
        last_mention_at=event.last_mention_at,
        extracted_who=list(event.extracted_who) if event.extracted_who else None,
        extracted_what=event.extracted_what,
        extracted_where=event.extracted_where,
        corroboration_score=resolved_corroboration_score(event),
        provenance_summary=dict(event.provenance_summary or {}),
        sources=sources,
        claims=claims,
        trend_impacts=trend_impacts,
    )
