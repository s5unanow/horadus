"""
Source freshness SLO evaluation utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.storage.models import Source, SourceType


@dataclass(frozen=True, slots=True)
class SourceFreshnessRow:
    source_id: UUID
    source_name: str
    collector: str
    last_fetched_at: datetime | None
    age_seconds: int | None
    stale_after_seconds: int
    is_stale: bool


@dataclass(frozen=True, slots=True)
class SourceFreshnessReport:
    checked_at: datetime
    stale_multiplier: float
    rows: tuple[SourceFreshnessRow, ...]

    @property
    def stale_count(self) -> int:
        return sum(1 for row in self.rows if row.is_stale)

    @property
    def stale_collectors(self) -> tuple[str, ...]:
        collectors = sorted({row.collector for row in self.rows if row.is_stale})
        return tuple(collectors)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _collector_interval_minutes(source_type: SourceType) -> int | None:
    if source_type == SourceType.RSS:
        return max(1, settings.RSS_COLLECTION_INTERVAL)
    if source_type == SourceType.GDELT:
        return max(1, settings.GDELT_COLLECTION_INTERVAL)
    return None


async def build_source_freshness_report(
    session: AsyncSession,
    *,
    stale_multiplier: float | None = None,
    checked_at: datetime | None = None,
) -> SourceFreshnessReport:
    effective_multiplier = stale_multiplier or settings.SOURCE_FRESHNESS_ALERT_MULTIPLIER
    normalized_multiplier = max(1.0, float(effective_multiplier))
    now_utc = _as_utc(checked_at or datetime.now(tz=UTC))

    query = (
        select(Source)
        .where(Source.is_active.is_(True))
        .where(Source.type.in_((SourceType.RSS, SourceType.GDELT)))
        .order_by(Source.type.asc(), Source.name.asc())
    )
    sources = list((await session.scalars(query)).all())

    rows: list[SourceFreshnessRow] = []
    for source in sources:
        interval_minutes = _collector_interval_minutes(source.type)
        if interval_minutes is None:
            continue
        stale_after_seconds = max(60, int(interval_minutes * 60 * normalized_multiplier))
        last_fetched_at = _as_utc(source.last_fetched_at) if source.last_fetched_at else None

        if last_fetched_at is None:
            age_seconds: int | None = None
            is_stale = True
        else:
            age_seconds = max(0, int((now_utc - last_fetched_at).total_seconds()))
            is_stale = age_seconds > stale_after_seconds

        source_id = source.id
        if source_id is None:
            continue

        rows.append(
            SourceFreshnessRow(
                source_id=source_id,
                source_name=source.name,
                collector=source.type.value,
                last_fetched_at=last_fetched_at,
                age_seconds=age_seconds,
                stale_after_seconds=stale_after_seconds,
                is_stale=is_stale,
            )
        )

    rows.sort(
        key=lambda row: (
            not row.is_stale,
            -(row.age_seconds or row.stale_after_seconds),
            row.source_name.lower(),
        )
    )
    return SourceFreshnessReport(
        checked_at=now_utc,
        stale_multiplier=normalized_multiplier,
        rows=tuple(rows),
    )
