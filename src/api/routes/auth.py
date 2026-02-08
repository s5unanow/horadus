"""
Authentication and API key management endpoints.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from src.core.api_key_manager import APIKeyRecord, get_api_key_manager
from src.core.config import settings

router = APIRouter()


class APIKeySummary(BaseModel):
    """Public metadata for one API key."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "name": "ingestion-service",
                "prefix": "geo_abcd",
                "is_active": True,
                "rate_limit_per_minute": 120,
                "created_at": "2026-02-07T20:00:00Z",
                "last_used_at": "2026-02-07T20:05:00Z",
                "source": "runtime",
            }
        }
    )

    id: str
    name: str
    prefix: str
    is_active: bool
    rate_limit_per_minute: int
    created_at: datetime
    last_used_at: datetime | None
    source: str


class APIKeyCreateRequest(BaseModel):
    """Request payload to create an API key."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "analytics-dashboard",
                "rate_limit_per_minute": 90,
            }
        }
    )

    name: str = Field(min_length=1, max_length=100)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=5000)


class APIKeyCreateResponse(BaseModel):
    """Response payload for a newly created API key."""

    key: APIKeySummary
    api_key: str


def _to_summary(record: APIKeyRecord) -> APIKeySummary:
    return APIKeySummary(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        is_active=record.is_active,
        rate_limit_per_minute=record.rate_limit_per_minute,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        source=record.source,
    )


def _ensure_admin_access(request: Request) -> None:
    configured_admin_key = (settings.API_ADMIN_KEY or "").strip()
    if configured_admin_key:
        header_value = request.headers.get("X-Admin-API-Key", "").strip()
        if header_value == configured_admin_key:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key required",
        )

    if getattr(request.state, "api_key_id", None) is not None:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Authenticated API key required",
    )


@router.get("/keys", response_model=list[APIKeySummary])
async def list_api_keys(request: Request) -> list[APIKeySummary]:
    """List API keys (metadata only)."""
    _ensure_admin_access(request)
    manager = get_api_key_manager()
    return [_to_summary(record) for record in manager.list_keys()]


@router.post("/keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: APIKeyCreateRequest,
    request: Request,
) -> APIKeyCreateResponse:
    """Create a new API key."""
    _ensure_admin_access(request)
    manager = get_api_key_manager()
    record, raw_key = manager.create_key(
        name=payload.name,
        rate_limit_per_minute=payload.rate_limit_per_minute,
    )
    return APIKeyCreateResponse(
        key=_to_summary(record),
        api_key=raw_key,
    )


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    request: Request,
) -> None:
    """Revoke an API key by id."""
    _ensure_admin_access(request)
    manager = get_api_key_manager()
    revoked = manager.revoke_key(key_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )


@router.post("/keys/{key_id}/rotate", response_model=APIKeyCreateResponse)
async def rotate_api_key(
    key_id: str,
    request: Request,
) -> APIKeyCreateResponse:
    """Rotate an API key by id and return a replacement credential."""
    _ensure_admin_access(request)
    manager = get_api_key_manager()
    rotated = manager.rotate_key(key_id)
    if rotated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )
    record, raw_key = rotated
    return APIKeyCreateResponse(
        key=_to_summary(record),
        api_key=raw_key,
    )
