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
from src.storage.models import Event, EventItem, RawItem, Source, TrendEvidence

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
                "first_seen_at": "2026-02-07T12:10:00Z",
                "extracted_who": ["Country A", "Country B"],
                "extracted_what": "Military units repositioned near border.",
                "extracted_where": "Eastern sector",
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
    trend_impacts: list[dict[str, Any]]


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[EventResponse])
async def list_events(
    category: str | None = None,
    trend_id: UUID | None = None,
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

    source_rows = (
        await session.execute(
            select(Source.name, RawItem.url)
            .join(RawItem, RawItem.source_id == Source.id)
            .join(EventItem, EventItem.item_id == RawItem.id)
            .where(EventItem.event_id == event_id)
            .order_by(Source.name.asc())
        )
    ).all()
    sources = [
        {"source_name": source_name, "url": url}
        for source_name, url in source_rows
        if source_name is not None
    ]

    impact_rows = (
        await session.execute(
            select(
                TrendEvidence.trend_id,
                TrendEvidence.signal_type,
                TrendEvidence.delta_log_odds,
            )
            .where(TrendEvidence.event_id == event_id)
            .where(TrendEvidence.is_invalidated.is_(False))
            .order_by(TrendEvidence.created_at.desc())
        )
    ).all()
    trend_impacts = [
        {
            "trend_id": trend_id,
            "signal_type": signal_type,
            "direction": "escalatory" if float(delta_log_odds) >= 0 else "de_escalatory",
        }
        for trend_id, signal_type, delta_log_odds in impact_rows
    ]

    return EventDetailResponse(
        id=event.id,
        summary=event.canonical_summary,
        categories=list(event.categories or []),
        source_count=event.source_count,
        unique_source_count=event.unique_source_count,
        lifecycle_status=event.lifecycle_status,
        has_contradictions=event.has_contradictions,
        contradiction_notes=event.contradiction_notes,
        first_seen_at=event.first_seen_at,
        last_mention_at=event.last_mention_at,
        extracted_who=list(event.extracted_who) if event.extracted_who else None,
        extracted_what=event.extracted_what,
        extracted_where=event.extracted_where,
        sources=sources,
        trend_impacts=trend_impacts,
    )
