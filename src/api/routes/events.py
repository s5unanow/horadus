"""
Events API endpoints.

Endpoints for querying clustered news events.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_session

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
                "first_seen_at": "2026-02-07T12:10:00Z",
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
    first_seen_at: datetime
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
