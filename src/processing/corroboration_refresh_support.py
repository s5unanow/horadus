"""Support helpers for source-triggered corroboration refreshes."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.source_credibility import (
    DEFAULT_SOURCE_CREDIBILITY,
    source_multiplier_expression,
)
from src.core.trend_engine import calculate_recency_novelty
from src.storage.models import EventItem, RawItem, Source, TrendEvidence


async def _load_novelty_snapshot_for_refresh(
    *,
    session: AsyncSession,
) -> dict[tuple[UUID, str], tuple[tuple[UUID, datetime], ...]]:
    query = (
        select(
            TrendEvidence.trend_id,
            TrendEvidence.signal_type,
            TrendEvidence.event_id,
            TrendEvidence.created_at,
        )
        .where(TrendEvidence.is_invalidated.is_(False))
        .order_by(TrendEvidence.created_at.desc())
    )
    rows = (await session.execute(query)).all()
    grouped: dict[tuple[UUID, str], dict[UUID, datetime]] = {}
    for trend_id, signal_type, event_id, created_at in rows:
        if created_at is None:
            continue
        entries = grouped.setdefault((trend_id, signal_type), {})
        previous = entries.get(event_id)
        if previous is None or created_at > previous:
            entries[event_id] = created_at
    return {
        key: tuple(sorted(entries.items(), key=lambda item: item[1], reverse=True))
        for key, entries in grouped.items()
    }


async def _sync_novelty_snapshot_for_refresh(
    *,
    session: AsyncSession,
    event_id: UUID,
    snapshot: Mapping[tuple[UUID, str], tuple[tuple[UUID, datetime], ...]],
) -> dict[tuple[UUID, str], tuple[tuple[UUID, datetime], ...]]:
    existing_timestamps = {
        key: created_at
        for key, entries in snapshot.items()
        for seen_event_id, created_at in entries
        if seen_event_id == event_id
    }
    next_snapshot: dict[tuple[UUID, str], list[tuple[UUID, datetime]]] = {
        key: [
            (seen_event_id, created_at)
            for seen_event_id, created_at in entries
            if seen_event_id != event_id
        ]
        for key, entries in snapshot.items()
    }
    query = (
        select(
            TrendEvidence.trend_id,
            TrendEvidence.signal_type,
            func.max(TrendEvidence.created_at),
        )
        .where(TrendEvidence.event_id == event_id)
        .where(TrendEvidence.is_invalidated.is_(False))
        .group_by(TrendEvidence.trend_id, TrendEvidence.signal_type)
    )
    rows = (await session.execute(query)).all()
    for trend_id, signal_type, created_at in rows:
        if created_at is None:
            continue
        key = (trend_id, signal_type)
        next_snapshot.setdefault(key, []).append(
            (event_id, existing_timestamps.get(key, created_at))
        )
    return {
        key: tuple(sorted(entries, key=lambda item: item[1], reverse=True))
        for key, entries in next_snapshot.items()
        if entries
    }


async def _load_item_for_refresh(
    *,
    session: AsyncSession,
    item_id: UUID | None,
) -> RawItem | None:
    if item_id is None:
        return None
    query = select(RawItem).where(RawItem.id == item_id).limit(1)
    return cast("RawItem | None", await session.scalar(query))


async def _load_most_credible_event_item_for_refresh(
    *,
    session: AsyncSession,
    event_id: UUID,
) -> RawItem | None:
    effective_credibility = func.coalesce(
        Source.credibility_score, DEFAULT_SOURCE_CREDIBILITY
    ) * source_multiplier_expression(
        source_tier_col=Source.source_tier,
        reporting_type_col=Source.reporting_type,
    )
    freshness = func.coalesce(RawItem.published_at, RawItem.fetched_at)
    query = (
        select(RawItem)
        .join(EventItem, EventItem.item_id == RawItem.id)
        .join(Source, Source.id == RawItem.source_id)
        .where(EventItem.event_id == event_id)
        .order_by(
            effective_credibility.desc(),
            freshness.desc(),
            RawItem.id.asc(),
        )
        .limit(1)
    )
    return cast("RawItem | None", await session.scalar(query))


async def _load_item_effective_credibility_for_refresh(
    *,
    session: AsyncSession,
    item_id: UUID,
) -> float | None:
    query = (
        select(
            (
                func.coalesce(Source.credibility_score, DEFAULT_SOURCE_CREDIBILITY)
                * source_multiplier_expression(
                    source_tier_col=Source.source_tier,
                    reporting_type_col=Source.reporting_type,
                )
            ).label("effective_credibility")
        )
        .join(RawItem, RawItem.source_id == Source.id)
        .where(RawItem.id == item_id)
        .limit(1)
    )
    credibility = await session.scalar(query)
    try:
        return float(credibility) if credibility is not None else None
    except (TypeError, ValueError):
        return None


async def _load_novelty_score_for_refresh(
    *,
    session: AsyncSession,
    trend_id: UUID,
    signal_type: str,
    event_id: UUID,
    snapshot: Mapping[tuple[UUID, str], tuple[tuple[UUID, datetime], ...]] | None = None,
) -> float:
    if snapshot is not None:
        entries = snapshot.get((trend_id, signal_type), ())
        snapshot_last_seen_at = next(
            (
                created_at
                for seen_event_id, created_at in entries
                if seen_event_id != event_id and created_at is not None
            ),
            None,
        )
        return calculate_recency_novelty(last_seen_at=snapshot_last_seen_at)
    query = (
        select(func.max(TrendEvidence.created_at))
        .where(TrendEvidence.trend_id == trend_id)
        .where(TrendEvidence.signal_type == signal_type)
        .where(TrendEvidence.event_id != event_id)
        .where(TrendEvidence.is_invalidated.is_(False))
    )
    last_seen_at: datetime | None = await session.scalar(query)
    return calculate_recency_novelty(last_seen_at=last_seen_at)


def _build_canonical_summary(item: RawItem) -> str:
    if item.title and item.title.strip():
        return item.title.strip()
    content = item.raw_content.strip()
    return content[:400] if len(content) > 400 else content
