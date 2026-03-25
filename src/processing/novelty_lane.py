"""Deterministic novelty-lane capture and ranking helpers."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.processing.trend_impact_mapping import iter_unresolved_mapping_gaps
from src.storage.event_summary import resolved_event_summary
from src.storage.novelty_models import NoveltyCandidate

if TYPE_CHECKING:
    from src.processing.tier1_classifier import Tier1ItemResult
    from src.storage.models import Event, RawItem

_KEY_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_SUMMARY_MAX_CHARS = 240
_MAX_LANE_CANDIDATES = 200
_NEAR_THRESHOLD_MARGIN = 1


class NoveltyLaneService:
    """Persist bounded novelty candidates from existing deterministic signals."""

    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session

    async def capture_tier1_near_miss(
        self,
        *,
        item: RawItem,
        tier1_result: Tier1ItemResult,
    ) -> None:
        """Persist a near-threshold Tier-1 miss when it looks worth reviewing."""

        if tier1_result.should_queue_tier2:
            return
        if not self._is_near_threshold(tier1_result.max_relevance):
            return

        summary = _item_summary(item)
        if not summary:
            return

        details = {
            "reason": "near_threshold_item",
            "language": _normalized_text(item.language, max_terms=1) or None,
            "top_trend_scores": _top_trend_scores(tier1_result),
            "source_id": str(item.source_id),
            "title": item.title,
            "url": item.url,
        }
        await self._upsert_candidate(
            cluster_key=_cluster_key(
                "near_threshold_item",
                _normalized_text(item.language, max_terms=1),
                _normalized_text(item.title or item.raw_content),
            ),
            candidate_kind="near_threshold_item",
            summary=summary,
            details=details,
            event_id=None,
            raw_item_id=item.id,
            distinct_source_count=1,
            actor_location_hit=0,
            near_threshold_hit=1,
            unmapped_signal_count=0,
            last_tier1_max_relevance=tier1_result.max_relevance,
        )

    async def capture_event_candidate(
        self,
        *,
        event: Event,
        item: RawItem,
        tier1_result: Tier1ItemResult,
        trend_impacts_seen: int,
        trend_updates: int,
    ) -> None:
        """Persist a novelty event candidate when no active-trend update was applied."""

        if event.id is None or trend_updates > 0:
            return

        summary = resolved_event_summary(event).strip()
        if not summary:
            return

        unresolved_mapping_count = len(iter_unresolved_mapping_gaps(event))
        actor_location_hit = 1 if _has_actor_location_signal(event) else 0
        near_threshold_hit = 1 if self._is_near_threshold(tier1_result.max_relevance) else 0
        distinct_source_count = max(
            1,
            int(event.unique_source_count or event.source_count or 1),
        )

        if (
            trend_impacts_seen <= 0
            and unresolved_mapping_count <= 0
            and actor_location_hit <= 0
            and near_threshold_hit <= 0
            and distinct_source_count < 2
        ):
            return

        details = {
            "reason": "event_gap" if unresolved_mapping_count <= 0 else "unmapped_event",
            "top_trend_scores": _top_trend_scores(tier1_result),
            "trend_impacts_seen": int(trend_impacts_seen),
            "trend_updates": int(trend_updates),
            "unresolved_mapping_count": int(unresolved_mapping_count),
            "actors": _string_list(event.extracted_who),
            "where": event.extracted_where,
            "categories": _string_list(event.categories),
            "source_count": int(event.source_count or 1),
            "raw_item_id": str(item.id),
        }
        await self._upsert_candidate(
            cluster_key=_cluster_key(
                "event_gap",
                _normalized_text(" ".join(_string_list(event.extracted_who))),
                _normalized_text(event.extracted_where),
                _normalized_text(event.extracted_what or summary),
            ),
            candidate_kind="event_gap",
            summary=_truncate(summary),
            details=details,
            event_id=event.id,
            raw_item_id=item.id,
            distinct_source_count=distinct_source_count,
            actor_location_hit=actor_location_hit,
            near_threshold_hit=near_threshold_hit,
            unmapped_signal_count=unresolved_mapping_count,
            last_tier1_max_relevance=tier1_result.max_relevance,
        )

    def _is_near_threshold(self, max_relevance: int) -> bool:
        lower_bound = max(0, int(settings.TIER1_RELEVANCE_THRESHOLD) - _NEAR_THRESHOLD_MARGIN)
        return lower_bound <= int(max_relevance) < int(settings.TIER1_RELEVANCE_THRESHOLD)

    async def _upsert_candidate(
        self,
        *,
        cluster_key: str,
        candidate_kind: str,
        summary: str,
        details: dict[str, Any],
        event_id: UUID | None,
        raw_item_id: UUID | None,
        distinct_source_count: int,
        actor_location_hit: int,
        near_threshold_hit: int,
        unmapped_signal_count: int,
        last_tier1_max_relevance: int,
    ) -> None:
        now = datetime.now(tz=UTC)
        existing = await self.session.scalar(
            select(NoveltyCandidate).where(NoveltyCandidate.cluster_key == cluster_key).limit(1)
        )
        if existing is None:
            candidate = NoveltyCandidate(
                cluster_key=cluster_key,
                candidate_kind=candidate_kind,
                event_id=event_id,
                raw_item_id=raw_item_id,
                summary=summary,
                details=details,
                recurrence_count=1,
                distinct_source_count=max(1, int(distinct_source_count)),
                actor_location_hits=max(0, int(actor_location_hit)),
                near_threshold_hits=max(0, int(near_threshold_hit)),
                unmapped_signal_count=max(0, int(unmapped_signal_count)),
                last_tier1_max_relevance=int(last_tier1_max_relevance),
                ranking_score=self._ranking_score(
                    recurrence_count=1,
                    distinct_source_count=max(1, int(distinct_source_count)),
                    actor_location_hits=max(0, int(actor_location_hit)),
                    near_threshold_hits=max(0, int(near_threshold_hit)),
                    unmapped_signal_count=max(0, int(unmapped_signal_count)),
                    last_tier1_max_relevance=int(last_tier1_max_relevance),
                ),
                first_seen_at=now,
                last_seen_at=now,
            )
            self.session.add(candidate)
        else:
            existing.event_id = event_id or existing.event_id
            existing.raw_item_id = raw_item_id or existing.raw_item_id
            existing.summary = summary or existing.summary
            existing.details = _merged_details(existing.details, details)
            existing.recurrence_count = int(existing.recurrence_count or 0) + 1
            existing.distinct_source_count = max(
                int(existing.distinct_source_count or 1),
                int(distinct_source_count),
            )
            existing.actor_location_hits = int(existing.actor_location_hits or 0) + int(
                actor_location_hit
            )
            existing.near_threshold_hits = int(existing.near_threshold_hits or 0) + int(
                near_threshold_hit
            )
            existing.unmapped_signal_count = max(
                int(existing.unmapped_signal_count or 0),
                int(unmapped_signal_count),
            )
            existing.last_tier1_max_relevance = max(
                int(existing.last_tier1_max_relevance or 0),
                int(last_tier1_max_relevance),
            )
            existing.last_seen_at = now
            existing.ranking_score = self._ranking_score(
                recurrence_count=int(existing.recurrence_count or 1),
                distinct_source_count=int(existing.distinct_source_count or 1),
                actor_location_hits=int(existing.actor_location_hits or 0),
                near_threshold_hits=int(existing.near_threshold_hits or 0),
                unmapped_signal_count=int(existing.unmapped_signal_count or 0),
                last_tier1_max_relevance=int(existing.last_tier1_max_relevance or 0),
            )

        await self.session.flush()
        await self._prune_lane()

    @staticmethod
    def _ranking_score(
        *,
        recurrence_count: int,
        distinct_source_count: int,
        actor_location_hits: int,
        near_threshold_hits: int,
        unmapped_signal_count: int,
        last_tier1_max_relevance: int,
    ) -> float:
        recurrence_signal = min(2.5, math.log1p(max(1, recurrence_count)))
        source_signal = min(1.5, 0.25 * max(0, distinct_source_count - 1))
        actor_location_signal = min(2.0, 0.75 * max(0, actor_location_hits))
        near_threshold_signal = min(2.0, 0.35 * max(0, near_threshold_hits)) + min(
            0.5,
            0.1 * max(0, last_tier1_max_relevance - int(settings.TIER1_RELEVANCE_THRESHOLD) + 1),
        )
        unmapped_signal = min(1.5, 0.4 * max(0, unmapped_signal_count))
        return round(
            1.0
            + recurrence_signal
            + source_signal
            + actor_location_signal
            + near_threshold_signal
            + unmapped_signal,
            4,
        )

    async def _prune_lane(self) -> None:
        count = await self.session.scalar(select(func.count()).select_from(NoveltyCandidate))
        total_count = int(count or 0)
        if total_count <= _MAX_LANE_CANDIDATES:
            return

        keep_ids = list(
            (
                await self.session.scalars(
                    select(NoveltyCandidate.id)
                    .order_by(
                        NoveltyCandidate.ranking_score.desc(),
                        NoveltyCandidate.last_seen_at.desc(),
                        NoveltyCandidate.created_at.desc(),
                    )
                    .limit(_MAX_LANE_CANDIDATES)
                )
            ).all()
        )
        if not keep_ids:
            return
        await self.session.execute(
            delete(NoveltyCandidate).where(NoveltyCandidate.id.not_in(tuple(keep_ids)))
        )
        await self.session.flush()


def _item_summary(item: RawItem) -> str:
    title = (item.title or "").strip()
    if title:
        return _truncate(title)
    return _truncate(" ".join((item.raw_content or "").split()))


def _top_trend_scores(tier1_result: Tier1ItemResult) -> list[dict[str, Any]]:
    top_scores = sorted(
        (
            {
                "trend_id": score.trend_id,
                "relevance_score": int(score.relevance_score),
                "rationale": score.rationale,
            }
            for score in tier1_result.trend_scores
            if int(score.relevance_score) > 0
        ),
        key=lambda row: (-cast("int", row["relevance_score"]), str(row["trend_id"])),
    )
    return top_scores[:3]


def _truncate(value: str) -> str:
    text_value = " ".join(value.split()).strip()
    if len(text_value) <= _SUMMARY_MAX_CHARS:
        return text_value
    return f"{text_value[: _SUMMARY_MAX_CHARS - 3].rstrip()}..."


def _normalized_text(value: str | None, *, max_terms: int = 12) -> str:
    if not isinstance(value, str):
        return ""
    normalized = _KEY_TOKEN_RE.sub(" ", value.lower()).strip()
    if not normalized:
        return ""
    return " ".join(normalized.split()[:max_terms])


def _cluster_key(*parts: str) -> str:
    payload = "|".join(part for part in parts if part)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry.strip() for entry in value if isinstance(entry, str) and entry.strip()]


def _has_actor_location_signal(event: Event) -> bool:
    return bool(_string_list(event.extracted_who)) and bool(
        isinstance(event.extracted_where, str) and event.extracted_where.strip()
    )


def _merged_details(existing: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if value is None:
            continue
        merged[key] = value
    return merged
