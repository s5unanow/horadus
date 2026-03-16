"""Persistence helpers for trend write routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import Trend


def raise_payload_validation_error(exc: Exception) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc),
    ) from exc


def is_unique_integrity_error(exc: IntegrityError, *, marker: str) -> bool:
    return marker in str(getattr(exc, "orig", exc))


async def get_existing_trend_by_runtime_id(
    session: AsyncSession,
    *,
    runtime_trend_id: str,
) -> Trend | None:
    query = select(Trend).where(Trend.runtime_trend_id == runtime_trend_id).limit(1)
    return cast("Trend | None", await session.scalar(query))


async def enforce_trend_uniqueness(
    session: AsyncSession,
    *,
    trend_name: str,
    runtime_trend_id: str,
    current_trend_id: UUID | None = None,
) -> None:
    existing_name_id = cast(
        "UUID | None",
        await session.scalar(select(Trend.id).where(Trend.name == trend_name).limit(1)),
    )
    if existing_name_id is not None and existing_name_id != current_trend_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trend '{trend_name}' already exists",
        )

    existing_runtime = cast(
        "UUID | None",
        await session.scalar(
            select(Trend.id).where(Trend.runtime_trend_id == runtime_trend_id).limit(1)
        ),
    )
    if existing_runtime is not None and existing_runtime != current_trend_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trend runtime id '{runtime_trend_id}' already exists",
        )
