"""
Sources API endpoints.

CRUD operations for managing data sources (RSS feeds, Telegram channels, etc.)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.source_freshness import build_source_freshness_report
from src.storage.database import get_session
from src.storage.models import ReportingType, Source, SourceTier, SourceType

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class SourceCreate(BaseModel):
    """Request body for creating a source."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "rss",
                "name": "Reuters World",
                "url": "https://feeds.reuters.com/Reuters/worldNews",
                "credibility_score": 0.95,
                "source_tier": "wire",
                "reporting_type": "secondary",
                "config": {"check_interval_minutes": 30},
                "is_active": True,
            }
        }
    )

    type: SourceType = Field(..., description="Source type: rss, telegram, gdelt, api")
    name: str = Field(..., description="Human-readable name")
    url: str | None = Field(None, description="Source URL")
    credibility_score: float = Field(0.5, ge=0, le=1, description="Reliability score")
    source_tier: SourceTier = Field(
        default=SourceTier.REGIONAL,
        description="Source tier (primary/wire/major/regional/aggregator)",
    )
    reporting_type: ReportingType = Field(
        default=ReportingType.SECONDARY,
        description="Reporting type (firsthand/secondary/aggregator)",
    )
    config: dict[str, Any] = Field(default_factory=dict, description="Source-specific config")
    is_active: bool = True


class SourceUpdate(BaseModel):
    """Request body for updating a source."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "credibility_score": 0.92,
                "source_tier": "major",
                "is_active": True,
            }
        }
    )

    name: str | None = None
    url: str | None = None
    credibility_score: float | None = Field(None, ge=0, le=1)
    source_tier: SourceTier | None = None
    reporting_type: ReportingType | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class SourceResponse(BaseModel):
    """Response body for a source."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "type": "rss",
                "name": "Reuters World",
                "url": "https://feeds.reuters.com/Reuters/worldNews",
                "credibility_score": 0.95,
                "source_tier": "wire",
                "reporting_type": "secondary",
                "config": {"check_interval_minutes": 30},
                "is_active": True,
                "last_fetched_at": "2026-02-07T18:30:00Z",
                "error_count": 0,
            }
        },
    )

    id: UUID
    type: SourceType
    name: str
    url: str | None
    credibility_score: float
    source_tier: str
    reporting_type: str
    config: dict[str, Any]
    is_active: bool
    last_fetched_at: datetime | None
    error_count: int


class SourceFreshnessRowResponse(BaseModel):
    """Freshness status for one source."""

    source_id: UUID
    source_name: str
    collector: str
    last_fetched_at: datetime | None
    age_seconds: int | None
    stale_after_seconds: int
    is_stale: bool


class SourceFreshnessResponse(BaseModel):
    """Freshness summary across active RSS/GDELT sources."""

    checked_at: datetime
    stale_multiplier: float
    stale_count: int
    stale_collectors: list[str]
    catchup_dispatch_budget: int
    catchup_candidates: list[str]
    rows: list[SourceFreshnessRowResponse]


# =============================================================================
# Helpers
# =============================================================================


def _to_response(source: Source) -> SourceResponse:
    return SourceResponse.model_validate(source)


async def _get_source_or_404(session: AsyncSession, source_id: UUID) -> Source:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found",
        )
    return source


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    source_type: SourceType | None = Query(default=None, alias="type"),
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
) -> list[SourceResponse]:
    """
    List all data sources.

    Args:
        source_type: Filter by source type (rss, telegram, gdelt, api)
        active_only: Only return active sources

    Returns:
        List of sources
    """
    query = select(Source).order_by(Source.created_at.desc())
    if source_type is not None:
        query = query.where(Source.type == source_type)
    if active_only:
        query = query.where(Source.is_active.is_(True))

    sources = (await session.scalars(query)).all()
    return [_to_response(source) for source in sources]


@router.get("/freshness", response_model=SourceFreshnessResponse)
async def get_source_freshness(
    session: AsyncSession = Depends(get_session),
) -> SourceFreshnessResponse:
    """Get freshness SLO status for active RSS/GDELT sources."""
    report = await build_source_freshness_report(session=session)
    enabled_collectors: list[str] = []
    if settings.ENABLE_RSS_INGESTION:
        enabled_collectors.append("rss")
    if settings.ENABLE_GDELT_INGESTION:
        enabled_collectors.append("gdelt")

    catchup_dispatch_budget = max(0, settings.SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES)
    catchup_candidates = [
        collector for collector in report.stale_collectors if collector in enabled_collectors
    ][:catchup_dispatch_budget]

    return SourceFreshnessResponse(
        checked_at=report.checked_at,
        stale_multiplier=report.stale_multiplier,
        stale_count=report.stale_count,
        stale_collectors=list(report.stale_collectors),
        catchup_dispatch_budget=catchup_dispatch_budget,
        catchup_candidates=catchup_candidates,
        rows=[
            SourceFreshnessRowResponse(
                source_id=row.source_id,
                source_name=row.source_name,
                collector=row.collector,
                last_fetched_at=row.last_fetched_at,
                age_seconds=row.age_seconds,
                stale_after_seconds=row.stale_after_seconds,
                is_stale=row.is_stale,
            )
            for row in report.rows
        ],
    )


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    source: SourceCreate,
    session: AsyncSession = Depends(get_session),
) -> SourceResponse:
    """
    Create a new data source.

    Args:
        source: Source configuration

    Returns:
        Created source
    """
    source_record = Source(
        type=source.type,
        name=source.name,
        url=source.url,
        credibility_score=source.credibility_score,
        source_tier=source.source_tier.value,
        reporting_type=source.reporting_type.value,
        config=source.config,
        is_active=source.is_active,
        error_count=0,
    )

    session.add(source_record)
    await session.flush()

    return _to_response(source_record)


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> SourceResponse:
    """
    Get a source by ID.

    Args:
        source_id: Source UUID

    Returns:
        Source details
    """
    source = await _get_source_or_404(session, source_id)
    return _to_response(source)


@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: UUID,
    source: SourceUpdate,
    session: AsyncSession = Depends(get_session),
) -> SourceResponse:
    """
    Update a source.

    Args:
        source_id: Source UUID
        source: Fields to update

    Returns:
        Updated source
    """
    source_record = await _get_source_or_404(session, source_id)

    updates = source.model_dump(exclude_unset=True)
    if "source_tier" in updates and updates["source_tier"] is not None:
        updates["source_tier"] = updates["source_tier"].value
    if "reporting_type" in updates and updates["reporting_type"] is not None:
        updates["reporting_type"] = updates["reporting_type"].value

    for field_name, field_value in updates.items():
        setattr(source_record, field_name, field_value)

    await session.flush()
    return _to_response(source_record)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Delete (deactivate) a source.

    Args:
        source_id: Source UUID
    """
    source = await _get_source_or_404(session, source_id)
    source.is_active = False
    await session.flush()
