"""
Sources API endpoints.

CRUD operations for managing data sources (RSS feeds, Telegram channels, etc.)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_session

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class SourceCreate(BaseModel):
    """Request body for creating a source."""

    type: str = Field(..., description="Source type: rss, telegram, gdelt, api")
    name: str = Field(..., description="Human-readable name")
    url: str | None = Field(None, description="Source URL")
    credibility_score: float = Field(0.5, ge=0, le=1, description="Reliability score")
    config: dict = Field(default_factory=dict, description="Source-specific config")


class SourceUpdate(BaseModel):
    """Request body for updating a source."""

    name: str | None = None
    url: str | None = None
    credibility_score: float | None = Field(None, ge=0, le=1)
    config: dict | None = None
    is_active: bool | None = None


class SourceResponse(BaseModel):
    """Response body for a source."""

    id: UUID
    type: str
    name: str
    url: str | None
    credibility_score: float
    config: dict
    is_active: bool
    last_fetched_at: str | None
    error_count: int

    class Config:
        from_attributes = True


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    type: str | None = None,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
) -> list[SourceResponse]:
    """
    List all data sources.

    Args:
        type: Filter by source type (rss, telegram, gdelt, api)
        active_only: Only return active sources

    Returns:
        List of sources
    """
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
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
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


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
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


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
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


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
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )
