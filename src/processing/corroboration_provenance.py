"""Deterministic provenance-aware corroboration grouping for event evidence."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from inspect import isawaitable
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.source_credibility import (
    DEFAULT_SOURCE_CREDIBILITY,
    source_multiplier_expression,
)
from src.core.trend_engine import TrendEngine, calculate_recency_novelty
from src.processing.event_lifecycle import EventLifecycleManager
from src.processing.trend_impact_reconciliation import reconcile_event_trend_impacts
from src.storage.event_state import resolved_corroboration_score
from src.storage.models import Event, EventItem, RawItem, Source, Trend, TrendEvidence

PROVENANCE_AWARE_MODE = "provenance_aware"
FALLBACK_MODE = "fallback"
_GROUPS_PAYLOAD_LIMIT = 20
_WORD_RE = re.compile(r"[a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")
_SYNDICATION_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "reuters",
        (
            re.compile(r"\breuters\b", re.IGNORECASE),
            re.compile(r"\bthomson reuters\b", re.IGNORECASE),
        ),
    ),
    (
        "associated-press",
        (
            re.compile(r"\bassociated press\b", re.IGNORECASE),
            re.compile(r"\bap news\b", re.IGNORECASE),
        ),
    ),
    (
        "afp",
        (
            re.compile(r"\bafp\b", re.IGNORECASE),
            re.compile(r"\bagence france-presse\b", re.IGNORECASE),
        ),
    ),
    (
        "interfax",
        (re.compile(r"\binterfax\b", re.IGNORECASE),),
    ),
    (
        "tass",
        (re.compile(r"\btass\b", re.IGNORECASE),),
    ),
)


@dataclass(frozen=True, slots=True)
class EventSourceProvenance:
    """Normalized source/item metadata used to infer independence groups."""

    source_id: UUID | str
    source_name: str | None
    source_url: str | None
    source_tier: str | None
    reporting_type: str | None
    item_url: str | None
    title: str | None
    author: str | None
    content_hash: str | None


@dataclass(slots=True)
class _GroupAccumulator:
    key: str
    kind: str
    weight: float
    source_ids: set[str] = field(default_factory=set)
    source_families: set[str] = field(default_factory=set)
    reporting_types: set[str] = field(default_factory=set)
    member_count: int = 0

    def add(self, observation: EventSourceProvenance, *, source_family: str | None) -> None:
        self.member_count += 1
        self.source_ids.add(str(observation.source_id))
        if source_family:
            self.source_families.add(source_family)
        reporting_type = _normalized_value(observation.reporting_type)
        if reporting_type:
            self.reporting_types.add(reporting_type)
        self.weight = max(self.weight, reporting_type_weight(observation.reporting_type))

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "weight": round(self.weight, 4),
            "member_count": self.member_count,
            "source_count": len(self.source_ids),
            "source_families": sorted(self.source_families),
            "reporting_types": sorted(self.reporting_types),
        }


@dataclass(frozen=True, slots=True)
class EventProvenanceSummary:
    """Persistable provenance-aware corroboration summary for one event."""

    method: str
    reason: str
    raw_source_count: int
    unique_source_count: int
    independent_evidence_count: int
    weighted_corroboration_score: float
    source_family_count: int
    syndication_group_count: int
    near_duplicate_group_count: int
    groups: tuple[dict[str, Any], ...]
    groups_truncated: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "method": self.method,
            "reason": self.reason,
            "raw_source_count": self.raw_source_count,
            "unique_source_count": self.unique_source_count,
            "independent_evidence_count": self.independent_evidence_count,
            "weighted_corroboration_score": round(self.weighted_corroboration_score, 4),
            "source_family_count": self.source_family_count,
            "syndication_group_count": self.syndication_group_count,
            "near_duplicate_group_count": self.near_duplicate_group_count,
            "groups": list(self.groups),
        }
        if self.groups_truncated > 0:
            payload["groups_truncated"] = self.groups_truncated
        return payload


def fallback_event_provenance_summary(
    *,
    raw_source_count: int,
    unique_source_count: int,
    reason: str,
) -> EventProvenanceSummary:
    """Build a conservative fallback summary when provenance cannot be inferred."""

    fallback_count = max(1, unique_source_count or raw_source_count or 1)
    return EventProvenanceSummary(
        method=FALLBACK_MODE,
        reason=reason,
        raw_source_count=max(0, int(raw_source_count or 0)),
        unique_source_count=max(0, int(unique_source_count or 0)),
        independent_evidence_count=fallback_count,
        weighted_corroboration_score=float(fallback_count),
        source_family_count=0,
        syndication_group_count=0,
        near_duplicate_group_count=0,
        groups=(),
    )


def summarize_event_provenance(
    *,
    observations: list[EventSourceProvenance],
    raw_source_count: int,
    unique_source_count: int,
) -> EventProvenanceSummary:
    """Collapse event item/source metadata into independent evidence groups."""

    if not observations:
        return fallback_event_provenance_summary(
            raw_source_count=raw_source_count,
            unique_source_count=unique_source_count,
            reason="no_event_item_provenance",
        )

    story_fingerprints = Counter(
        fingerprint
        for fingerprint in (_story_fingerprint(observation) for observation in observations)
        if fingerprint is not None
    )
    groups: dict[str, _GroupAccumulator] = {}
    source_families: set[str] = set()

    for observation in observations:
        source_family = infer_source_family(observation)
        if source_family:
            source_families.add(source_family)
        group_key, group_kind = _group_identity(
            observation=observation,
            source_family=source_family,
            fingerprint_counts=story_fingerprints,
        )
        accumulator = groups.setdefault(
            group_key,
            _GroupAccumulator(
                key=group_key,
                kind=group_kind,
                weight=reporting_type_weight(observation.reporting_type),
            ),
        )
        accumulator.add(observation, source_family=source_family)

    ordered_groups = sorted(
        (group.as_dict() for group in groups.values()),
        key=lambda group: (-int(group["member_count"]), str(group["key"])),
    )
    groups_payload = tuple(ordered_groups[:_GROUPS_PAYLOAD_LIMIT])
    groups_truncated = max(0, len(ordered_groups) - len(groups_payload))
    independent_evidence_count = max(1, len(groups))
    corroboration_score = sum(float(group["weight"]) for group in ordered_groups)

    return EventProvenanceSummary(
        method=PROVENANCE_AWARE_MODE,
        reason="derived_from_event_items",
        raw_source_count=max(0, int(raw_source_count or 0)),
        unique_source_count=max(0, int(unique_source_count or 0)),
        independent_evidence_count=independent_evidence_count,
        weighted_corroboration_score=max(0.1, corroboration_score),
        source_family_count=len(source_families),
        syndication_group_count=sum(
            1 for group in ordered_groups if group["kind"] == "syndication"
        ),
        near_duplicate_group_count=sum(
            1 for group in ordered_groups if group["kind"] == "near_duplicate"
        ),
        groups=groups_payload,
        groups_truncated=groups_truncated,
    )


def parse_event_provenance_row(row: Any) -> EventSourceProvenance | None:
    """Parse a SQLAlchemy row/tuple into a normalized provenance observation."""

    if isinstance(row, tuple) and len(row) >= 9:
        source_id = row[0]
        if source_id is None:
            return None
        return EventSourceProvenance(
            source_id=source_id,
            source_name=_maybe_str(row[1]),
            source_url=_maybe_str(row[2]),
            source_tier=_maybe_str(row[3]),
            reporting_type=_maybe_str(row[4]),
            item_url=_maybe_str(row[5]),
            title=_maybe_str(row[6]),
            author=_maybe_str(row[7]),
            content_hash=_maybe_str(row[8]),
        )

    mapping = getattr(row, "_mapping", None)
    if not isinstance(mapping, Mapping):
        return None
    source_id = mapping.get("source_id")
    if source_id is None:
        return None
    return EventSourceProvenance(
        source_id=source_id,
        source_name=_maybe_str(mapping.get("source_name")),
        source_url=_maybe_str(mapping.get("source_url")),
        source_tier=_maybe_str(mapping.get("source_tier")),
        reporting_type=_maybe_str(mapping.get("reporting_type")),
        item_url=_maybe_str(mapping.get("item_url")),
        title=_maybe_str(mapping.get("title")),
        author=_maybe_str(mapping.get("author")),
        content_hash=_maybe_str(mapping.get("content_hash")),
    )


async def load_event_provenance_observations(
    *,
    session: AsyncSession,
    event_id: UUID,
) -> list[EventSourceProvenance]:
    """Load normalized provenance observations for one event."""

    query = (
        select(
            Source.id.label("source_id"),
            Source.name.label("source_name"),
            Source.url.label("source_url"),
            Source.source_tier.label("source_tier"),
            Source.reporting_type.label("reporting_type"),
            RawItem.url.label("item_url"),
            RawItem.title.label("title"),
            RawItem.author.label("author"),
            RawItem.content_hash.label("content_hash"),
        )
        .join(RawItem, RawItem.source_id == Source.id)
        .join(EventItem, EventItem.item_id == RawItem.id)
        .where(EventItem.event_id == event_id)
        .order_by(EventItem.added_at.asc())
    )
    rows = (await session.execute(query)).all()
    if isawaitable(rows):
        rows = await rows
    return [
        observation
        for observation in (parse_event_provenance_row(row) for row in rows)
        if observation is not None
    ]


async def refresh_event_provenance(
    *,
    session: AsyncSession,
    event: Event,
) -> EventProvenanceSummary:
    """Recompute and persist one event's provenance-aware corroboration summary."""

    if event.id is None:
        summary = fallback_event_provenance_summary(
            raw_source_count=event.source_count,
            unique_source_count=event.unique_source_count,
            reason="missing_event_id",
        )
    else:
        observations = await load_event_provenance_observations(session=session, event_id=event.id)
        summary = summarize_event_provenance(
            observations=observations,
            raw_source_count=event.source_count,
            unique_source_count=event.unique_source_count,
        )
    event.independent_evidence_count = summary.independent_evidence_count
    event.corroboration_score = summary.weighted_corroboration_score
    event.corroboration_mode = summary.method
    event.provenance_summary = summary.as_dict()
    return summary


async def refresh_events_for_source(
    *,
    session: AsyncSession,
    source_id: UUID | None,
) -> int:
    """Refresh provenance summaries for all events linked to one source."""

    if source_id is None:
        return 0
    query = (
        select(Event)
        .join(EventItem, EventItem.event_id == Event.id)
        .join(RawItem, RawItem.id == EventItem.item_id)
        .where(RawItem.source_id == source_id)
        .distinct()
    )
    events = list((await session.scalars(query)).all())
    lifecycle_manager = EventLifecycleManager(session)
    for event in events:
        await refresh_event_provenance(session=session, event=event)
        lifecycle_manager.sync_event_state(event)
        await _refresh_event_trend_impacts(session=session, event=event)
    return len(events)


async def _refresh_event_trend_impacts(
    *,
    session: AsyncSession,
    event: Event,
) -> tuple[int, int]:
    trends = await _load_active_trends_for_refresh(session=session)
    if not trends:
        return (0, 0)
    trend_engine = TrendEngine(session=session)

    async def load_event_source_credibility(target_event: Event) -> float:
        return await _load_event_source_credibility_for_refresh(
            session=session,
            event=target_event,
        )

    async def load_corroboration_score(target_event: Event) -> float:
        return await _load_corroboration_score_for_refresh(target_event)

    async def load_novelty_score(*, trend_id: UUID, signal_type: str, event_id: UUID) -> float:
        return await _load_novelty_score_for_refresh(
            session=session,
            trend_id=trend_id,
            signal_type=signal_type,
            event_id=event_id,
        )

    return await reconcile_event_trend_impacts(
        session=session,
        trend_engine=trend_engine,
        event=event,
        trends=trends,
        load_event_source_credibility=load_event_source_credibility,
        load_corroboration_score=load_corroboration_score,
        load_novelty_score=load_novelty_score,
        capture_taxonomy_gap=_capture_taxonomy_gap_for_refresh,
    )


async def _load_active_trends_for_refresh(*, session: AsyncSession) -> list[Trend]:
    query = select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
    return list((await session.scalars(query)).all())


async def _load_event_source_credibility_for_refresh(
    *,
    session: AsyncSession,
    event: Event,
) -> float:
    if event.primary_item_id is None:
        return DEFAULT_SOURCE_CREDIBILITY
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
        .where(RawItem.id == event.primary_item_id)
        .limit(1)
    )
    credibility = await session.scalar(query)
    try:
        return float(credibility) if credibility is not None else DEFAULT_SOURCE_CREDIBILITY
    except (TypeError, ValueError):
        return DEFAULT_SOURCE_CREDIBILITY


async def _load_corroboration_score_for_refresh(event: Event) -> float:
    return max(0.1, resolved_corroboration_score(event) * _contradiction_penalty(event))


async def _load_novelty_score_for_refresh(
    *,
    session: AsyncSession,
    trend_id: UUID,
    signal_type: str,
    event_id: UUID,
) -> float:
    query = (
        select(func.max(TrendEvidence.created_at))
        .where(TrendEvidence.trend_id == trend_id)
        .where(TrendEvidence.signal_type == signal_type)
        .where(TrendEvidence.event_id != event_id)
        .where(TrendEvidence.is_invalidated.is_(False))
    )
    last_seen_at: datetime | None = await session.scalar(query)
    return calculate_recency_novelty(last_seen_at=last_seen_at)


async def _capture_taxonomy_gap_for_refresh(**_: Any) -> None:
    return None


def _contradiction_penalty(event: Event) -> float:
    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    claim_graph = claims.get("claim_graph", {})
    links = claim_graph.get("links", []) if isinstance(claim_graph, dict) else []
    contradiction_links = 0
    if isinstance(links, list):
        contradiction_links = sum(
            1 for link in links if isinstance(link, dict) and link.get("relation") == "contradict"
        )
    if contradiction_links > 0:
        return max(0.4, 1.0 - 0.15 * contradiction_links)
    if event.has_contradictions:
        return 0.7
    return 1.0


def infer_source_family(observation: EventSourceProvenance) -> str | None:
    """Infer a bounded source-family key from URLs or the configured source name."""

    for candidate in (observation.item_url, observation.source_url):
        family_key = _source_family_key_from_url(candidate)
        if family_key is not None:
            return family_key
    return _slug_text(observation.source_name)


def reporting_type_weight(reporting_type: str | None) -> float:
    """Weight corroboration groups conservatively by reporting type."""

    reporting = _normalized_value(reporting_type)
    if reporting == "firsthand":
        return 1.0
    if reporting == "secondary":
        return 0.6
    if reporting == "aggregator":
        return 0.35
    return 0.5


def _group_identity(
    *,
    observation: EventSourceProvenance,
    source_family: str | None,
    fingerprint_counts: Counter[str],
) -> tuple[str, str]:
    reporting_type = _normalized_value(observation.reporting_type)
    if reporting_type == "firsthand":
        return (f"source:{observation.source_id}", "source")

    story_fingerprint = _story_fingerprint(observation)
    syndicator = _syndication_provider(observation)
    if syndicator is not None and story_fingerprint is not None:
        return (f"syndication:{syndicator}:{story_fingerprint}", "syndication")
    if story_fingerprint is not None and fingerprint_counts.get(story_fingerprint, 0) > 1:
        return (f"near-duplicate:{story_fingerprint}", "near_duplicate")
    if source_family is not None:
        return (f"family:{source_family}", "source_family")
    return (f"source:{observation.source_id}", "source")


def _story_fingerprint(observation: EventSourceProvenance) -> str | None:
    content_hash = _normalized_value(observation.content_hash)
    if content_hash:
        return f"content:{content_hash[:16]}"
    title = _normalized_text(observation.title)
    if len(title) < 24:
        return None
    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]
    return f"title:{digest}"


def _syndication_provider(observation: EventSourceProvenance) -> str | None:
    haystack = " | ".join(
        value
        for value in (observation.author, observation.title, observation.source_name)
        if isinstance(value, str) and value.strip()
    )
    if not haystack:
        return None
    for provider, patterns in _SYNDICATION_PATTERNS:
        if any(pattern.search(haystack) for pattern in patterns):
            return provider
    return None


def _maybe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _normalized_hostname(value: str | None) -> str | None:
    normalized = _maybe_str(value)
    if normalized is None:
        return None
    parsed = urlparse(normalized if "://" in normalized else f"https://{normalized}")
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or None


def _source_family_key_from_url(value: str | None) -> str | None:
    normalized = _maybe_str(value)
    if normalized is None:
        return None
    parsed = urlparse(normalized if "://" in normalized else f"https://{normalized}")
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if hostname in {"t.me", "telegram.me"}:
        segments = [
            segment.strip().lower() for segment in parsed.path.split("/") if segment.strip()
        ]
        if segments:
            return f"{hostname}/{segments[0]}"
    return hostname or None


def _slug_text(value: str | None) -> str | None:
    normalized = _normalized_text(value)
    if not normalized:
        return None
    words = _WORD_RE.findall(normalized)
    if not words:
        return None
    return "-".join(words[:6])


def _normalized_text(value: str | None) -> str:
    normalized = _maybe_str(value)
    if normalized is None:
        return ""
    lowered = normalized.lower()
    return _SPACE_RE.sub(" ", lowered).strip()


def _normalized_value(value: str | None) -> str | None:
    normalized = _maybe_str(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    return lowered or None
