"""Add event-level provenance-aware corroboration fields.

Revision ID: 0027_event_provenance
Revises: 0026_split_event_state_axes
Create Date: 2026-03-20 17:10:00.000000
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0027_event_provenance"
down_revision = "0026_split_event_state_axes"
branch_labels = None
depends_on = None

_FALLBACK_MODE = "fallback"
_PROVENANCE_AWARE_MODE = "provenance_aware"
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
    ("interfax", (re.compile(r"\binterfax\b", re.IGNORECASE),)),
    ("tass", (re.compile(r"\btass\b", re.IGNORECASE),)),
)


class _EventSourceProvenance:
    def __init__(
        self,
        *,
        source_id: object,
        source_name: str | None,
        source_url: str | None,
        source_tier: str | None,
        reporting_type: str | None,
        item_url: str | None,
        title: str | None,
        author: str | None,
        content_hash: str | None,
    ) -> None:
        self.source_id = source_id
        self.source_name = source_name
        self.source_url = source_url
        self.source_tier = source_tier
        self.reporting_type = reporting_type
        self.item_url = item_url
        self.title = title
        self.author = author
        self.content_hash = content_hash


class _GroupAccumulator:
    def __init__(self, *, key: str, kind: str, weight: float) -> None:
        self.key = key
        self.kind = kind
        self.weight = weight
        self.source_ids: set[str] = set()
        self.source_families: set[str] = set()
        self.reporting_types: set[str] = set()
        self.member_count = 0

    def add(self, observation: _EventSourceProvenance, *, source_family: str | None) -> None:
        self.member_count += 1
        self.source_ids.add(str(observation.source_id))
        if source_family:
            self.source_families.add(source_family)
        reporting_type = _normalized_value(observation.reporting_type)
        if reporting_type:
            self.reporting_types.add(reporting_type)
        self.weight = max(self.weight, _reporting_type_weight(observation.reporting_type))

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


def _fallback_event_provenance_summary(
    *,
    raw_source_count: int,
    unique_source_count: int,
    reason: str,
) -> dict[str, Any]:
    fallback_count = max(1, unique_source_count or raw_source_count or 1)
    return {
        "method": _FALLBACK_MODE,
        "reason": reason,
        "raw_source_count": max(0, int(raw_source_count or 0)),
        "unique_source_count": max(0, int(unique_source_count or 0)),
        "independent_evidence_count": fallback_count,
        "weighted_corroboration_score": float(fallback_count),
        "source_family_count": 0,
        "syndication_group_count": 0,
        "near_duplicate_group_count": 0,
        "groups": [],
    }


def _summarize_event_provenance(
    *,
    observations: list[_EventSourceProvenance],
    raw_source_count: int,
    unique_source_count: int,
) -> dict[str, Any]:
    if not observations:
        return _fallback_event_provenance_summary(
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
        source_family = _infer_source_family(observation)
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
                weight=_reporting_type_weight(observation.reporting_type),
            ),
        )
        accumulator.add(observation, source_family=source_family)

    ordered_groups = sorted(
        (group.as_dict() for group in groups.values()),
        key=lambda group: (-int(group["member_count"]), str(group["key"])),
    )
    groups_payload = ordered_groups[:_GROUPS_PAYLOAD_LIMIT]
    summary = {
        "method": _PROVENANCE_AWARE_MODE,
        "reason": "derived_from_event_items",
        "raw_source_count": max(0, int(raw_source_count or 0)),
        "unique_source_count": max(0, int(unique_source_count or 0)),
        "independent_evidence_count": max(1, len(groups)),
        "weighted_corroboration_score": round(
            max(0.1, sum(float(group["weight"]) for group in ordered_groups)),
            4,
        ),
        "source_family_count": len(source_families),
        "syndication_group_count": sum(
            1 for group in ordered_groups if group["kind"] == "syndication"
        ),
        "near_duplicate_group_count": sum(
            1 for group in ordered_groups if group["kind"] == "near_duplicate"
        ),
        "groups": groups_payload,
    }
    groups_truncated = max(0, len(ordered_groups) - len(groups_payload))
    if groups_truncated > 0:
        summary["groups_truncated"] = groups_truncated
    return summary


def _infer_source_family(observation: _EventSourceProvenance) -> str | None:
    for candidate in (observation.item_url, observation.source_url):
        family_key = _source_family_key_from_url(candidate)
        if family_key is not None:
            return family_key
    return _slug_text(observation.source_name)


def _reporting_type_weight(reporting_type: str | None) -> float:
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
    observation: _EventSourceProvenance,
    source_family: str | None,
    fingerprint_counts: Counter[str],
) -> tuple[str, str]:
    if _normalized_value(observation.reporting_type) == "firsthand":
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


def _story_fingerprint(observation: _EventSourceProvenance) -> str | None:
    content_hash = _normalized_value(observation.content_hash)
    if content_hash:
        return f"content:{content_hash[:16]}"
    title = _normalized_text(observation.title)
    if len(title) < 24:
        return None
    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]
    return f"title:{digest}"


def _syndication_provider(observation: _EventSourceProvenance) -> str | None:
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


def _normalized_value(value: str | None) -> str | None:
    normalized = _maybe_str(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    return lowered or None


def _normalized_text(value: str | None) -> str:
    normalized = _maybe_str(value)
    if normalized is None:
        return ""
    return _SPACE_RE.sub(" ", normalized.lower()).strip()


def _slug_text(value: str | None) -> str | None:
    normalized = _normalized_text(value)
    if not normalized:
        return None
    words = _WORD_RE.findall(normalized)
    if not words:
        return None
    return "-".join(words[:6])


def _source_family_key_from_url(value: str | None) -> str | None:
    normalized = _maybe_str(value)
    if normalized is None:
        return None
    parsed = urlparse(normalized if "://" in normalized else f"https://{normalized}")
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if hostname in {"t.me", "telegram.me"}:
        hostname = "t.me"
        segments = [
            segment.strip().lower() for segment in parsed.path.split("/") if segment.strip()
        ]
        if len(segments) >= 2 and segments[0] == "s":
            return f"{hostname}/{segments[1]}"
        if segments:
            return f"{hostname}/{segments[0]}"
    return hostname or None


def _backfill_event_provenance(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                e.id AS event_id,
                e.source_count AS source_count,
                e.unique_source_count AS unique_source_count,
                s.id AS source_id,
                s.name AS source_name,
                s.url AS source_url,
                s.source_tier AS source_tier,
                s.reporting_type AS reporting_type,
                ri.url AS item_url,
                ri.title AS title,
                ri.author AS author,
                ri.content_hash AS content_hash
            FROM events AS e
            LEFT JOIN event_items AS ei ON ei.event_id = e.id
            LEFT JOIN raw_items AS ri ON ri.id = ei.item_id
            LEFT JOIN sources AS s ON s.id = ri.source_id
            ORDER BY e.id, ei.added_at
            """
        )
    ).mappings()
    by_event: dict[object, dict[str, object]] = defaultdict(
        lambda: {"source_count": 0, "unique_source_count": 0, "observations": []}
    )
    for row in rows:
        payload = by_event[row["event_id"]]
        payload["source_count"] = int(row["source_count"] or 0)
        payload["unique_source_count"] = int(row["unique_source_count"] or 0)
        if row["source_id"] is not None:
            observations = payload["observations"]
            assert isinstance(observations, list)
            observations.append(
                _EventSourceProvenance(
                    source_id=row["source_id"],
                    source_name=row["source_name"],
                    source_url=row["source_url"],
                    source_tier=row["source_tier"],
                    reporting_type=row["reporting_type"],
                    item_url=row["item_url"],
                    title=row["title"],
                    author=row["author"],
                    content_hash=row["content_hash"],
                )
            )

    update_stmt = sa.text(
        """
        UPDATE events
        SET independent_evidence_count = :independent_evidence_count,
            corroboration_score = :corroboration_score,
            corroboration_mode = :corroboration_mode,
            provenance_summary = CAST(:provenance_summary AS jsonb)
        WHERE id = :event_id
        """
    )
    for event_id, payload in by_event.items():
        observations = payload["observations"]
        assert isinstance(observations, list)
        source_count = int(payload["source_count"])
        unique_source_count = int(payload["unique_source_count"])
        summary = _summarize_event_provenance(
            observations=observations,
            raw_source_count=source_count,
            unique_source_count=unique_source_count,
        )
        if not observations:
            summary = _fallback_event_provenance_summary(
                raw_source_count=source_count,
                unique_source_count=unique_source_count,
                reason="migration_backfill_no_event_items",
            )
        connection.execute(
            update_stmt,
            {
                "event_id": event_id,
                "independent_evidence_count": summary["independent_evidence_count"],
                "corroboration_score": summary["weighted_corroboration_score"],
                "corroboration_mode": summary["method"],
                "provenance_summary": json.dumps(summary),
            },
        )


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "independent_evidence_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "corroboration_score",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="1.00",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "corroboration_mode",
            sa.String(length=20),
            nullable=False,
            server_default="fallback",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "provenance_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    _backfill_event_provenance(op.get_bind())
    op.alter_column("events", "independent_evidence_count", server_default=None)
    op.alter_column("events", "corroboration_score", server_default=None)
    op.alter_column("events", "corroboration_mode", server_default=None)
    op.alter_column("events", "provenance_summary", server_default=None)


def downgrade() -> None:
    op.drop_column("events", "provenance_summary")
    op.drop_column("events", "corroboration_mode")
    op.drop_column("events", "corroboration_score")
    op.drop_column("events", "independent_evidence_count")
