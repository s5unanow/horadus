"""
Events API endpoints.

Endpoints for querying clustered news events.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_session

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class EventResponse(BaseModel):
    """Response body for an event."""

    id: UUID
    summary: str
    categories: list[str]
    source_count: int
    first_seen_at: datetime
    extracted_who: list[str] | None
    extracted_what: str | None
    extracted_where: str | None


class EventDetailResponse(EventResponse):
    """Detailed event response with sources."""

    sources: list[dict]
    trend_impacts: list[dict]


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[EventResponse])
async def list_events(
    category: str | None = None,
    trend_id: UUID | None = None,
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[EventResponse]:
    """
    List recent events.

    Can filter by category or by events affecting a specific trend.
    """
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(
    event_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> EventDetailResponse:
    """
    Get detailed event information.

    Includes source articles and trend impacts.
    """
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )
