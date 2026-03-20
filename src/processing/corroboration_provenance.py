"""Deterministic provenance-aware corroboration grouping for event evidence."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

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


def infer_source_family(observation: EventSourceProvenance) -> str | None:
    """Infer a bounded source-family key from URLs or the configured source name."""

    for candidate in (observation.item_url, observation.source_url):
        hostname = _normalized_hostname(candidate)
        if hostname is not None:
            return hostname
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
