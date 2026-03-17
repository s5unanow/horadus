"""Helpers for stable event-claim identity under mutable event clusters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from inspect import isawaitable
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import Event, EventClaim, EventClaimType

FALLBACK_EVENT_CLAIM_KEY = "__event__"
MAX_EVENT_CLAIM_KEY_LENGTH = 255
_DEFAULT_FALLBACK_CLAIM_TEXT = "Cluster event"


@dataclass(frozen=True)
class EventClaimSpec:
    """Desired claim identity for one event."""

    claim_key: str
    normalized_text: str
    claim_text: str
    claim_type: str
    claim_order: int


def normalize_claim_key(value: str) -> str:
    """Return a deterministic key for stable claim matching."""
    collapsed = normalize_claim_text(value)
    if len(collapsed) <= MAX_EVENT_CLAIM_KEY_LENGTH:
        return collapsed

    digest = sha256(collapsed.encode("utf-8")).hexdigest()[:16]
    prefix_length = MAX_EVENT_CLAIM_KEY_LENGTH - len(digest) - 1
    prefix = collapsed[:prefix_length].rstrip()
    return f"{prefix}-{digest}"


def normalize_claim_text(value: str) -> str:
    """Return normalized claim text without storage-specific length bounds."""
    normalized = value.lower().strip()
    chars = [ch if ch.isalnum() or ch.isspace() else " " for ch in normalized]
    return " ".join("".join(chars).split())


def fallback_claim_text(event: Event) -> str:
    """Return the deterministic fallback claim text for an event."""
    for candidate in (event.extracted_what, event.canonical_summary):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return _DEFAULT_FALLBACK_CLAIM_TEXT


def build_event_claim_specs(event: Event) -> list[EventClaimSpec]:
    """Build desired stable claim identities from event extraction payload."""
    specs = [
        EventClaimSpec(
            claim_key=FALLBACK_EVENT_CLAIM_KEY,
            normalized_text=normalize_claim_text(fallback_claim_text(event)),
            claim_text=fallback_claim_text(event),
            claim_type=EventClaimType.FALLBACK.value,
            claim_order=0,
        )
    ]
    seen_keys = {FALLBACK_EVENT_CLAIM_KEY}

    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    claim_graph = claims.get("claim_graph", {})
    nodes = claim_graph.get("nodes", []) if isinstance(claim_graph, dict) else []

    statement_texts: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        text = node.get("text")
        if isinstance(text, str) and text.strip():
            statement_texts.append(text.strip())

    if not statement_texts:
        raw_claims = claims.get("claims", [])
        if isinstance(raw_claims, list):
            for value in raw_claims:
                if isinstance(value, str) and value.strip():
                    statement_texts.append(value.strip())

    for index, text in enumerate(statement_texts, start=1):
        claim_key = normalize_claim_key(text)
        if not claim_key or claim_key in seen_keys:
            continue
        seen_keys.add(claim_key)
        specs.append(
            EventClaimSpec(
                claim_key=claim_key,
                normalized_text=normalize_claim_text(text),
                claim_text=text,
                claim_type=EventClaimType.STATEMENT.value,
                claim_order=index,
            )
        )
    return specs


def assign_claim_keys_to_impacts(
    *,
    event: Event,
    impacts: list[Any],
) -> list[Any]:
    """Attach deterministic claim keys to Tier-2 impact payloads."""
    specs = build_event_claim_specs(event)
    by_key = {spec.claim_key: spec for spec in specs}
    statements = [spec for spec in specs if spec.claim_type == EventClaimType.STATEMENT.value]

    assigned: list[Any] = []
    for payload in impacts:
        if not isinstance(payload, dict):
            assigned.append(payload)
            continue

        existing_key = payload.get("event_claim_key")
        if isinstance(existing_key, str) and existing_key in by_key:
            spec = by_key[existing_key]
        else:
            spec = _select_claim_for_impact(
                payload=payload, statements=statements, fallback=specs[0]
            )

        enriched = dict(payload)
        enriched["event_claim_key"] = spec.claim_key
        enriched["event_claim_text"] = spec.claim_text
        assigned.append(enriched)
    return assigned


def _select_claim_for_impact(
    *,
    payload: dict[str, Any],
    statements: list[EventClaimSpec],
    fallback: EventClaimSpec,
) -> EventClaimSpec:
    if not statements:
        return fallback
    if len(statements) == 1:
        return statements[0]

    scoring_text = " ".join(
        [
            str(payload.get("rationale", "") or ""),
            str(payload.get("signal_type", "") or "").replace("_", " "),
            str(payload.get("direction", "") or "").replace("_", " "),
        ]
    ).strip()
    scoring_tokens = set(normalize_claim_text(scoring_text).split())
    if not scoring_tokens:
        return fallback

    best: EventClaimSpec | None = None
    best_score = 0
    for spec in statements:
        overlap = len(scoring_tokens.intersection(spec.normalized_text.split()))
        if overlap > best_score:
            best = spec
            best_score = overlap
    if best is None or best_score <= 0:
        return fallback
    return best


async def sync_event_claims(
    *,
    session: AsyncSession,
    event: Event,
) -> dict[str, EventClaim]:
    """Upsert stable claim rows for an event and decorate impact payloads with ids."""
    if event.id is None:
        raise ValueError("Event must have an id before syncing event claims")

    desired_specs = build_event_claim_specs(event)
    result = await session.scalars(
        select(EventClaim)
        .where(EventClaim.event_id == event.id)
        .order_by(EventClaim.claim_order.asc(), EventClaim.created_at.asc())
    )
    existing_rows = list(await _await_if_needed(result.all()))
    existing_by_key = {row.claim_key: row for row in existing_rows}
    now = datetime.now(tz=UTC)
    desired_keys = {spec.claim_key for spec in desired_specs}

    resolved: dict[str, EventClaim] = {}
    for spec in desired_specs:
        row = await _resolve_event_claim_row(
            session=session,
            event_id=event.id,
            spec=spec,
            existing_by_key=existing_by_key,
            now=now,
        )
        resolved[spec.claim_key] = row

    for row in existing_rows:
        if row.claim_key not in desired_keys:
            row.is_active = False

    await session.flush()
    _decorate_event_claim_payload(event=event, claim_by_key=resolved)
    return resolved


async def _resolve_event_claim_row(
    *,
    session: AsyncSession,
    event_id: Any,
    spec: EventClaimSpec,
    existing_by_key: dict[str, EventClaim],
    now: datetime,
) -> EventClaim:
    row = existing_by_key.get(spec.claim_key)
    if row is None:
        row = await _insert_or_reload_event_claim(
            session=session,
            event_id=event_id,
            spec=spec,
            now=now,
        )
        existing_by_key[spec.claim_key] = row
    row.claim_text = spec.claim_text
    row.claim_type = spec.claim_type
    row.claim_order = spec.claim_order
    row.is_active = True
    row.last_seen_at = now
    return row


async def _insert_or_reload_event_claim(
    *,
    session: AsyncSession,
    event_id: Any,
    spec: EventClaimSpec,
    now: datetime,
) -> EventClaim:
    row = EventClaim(
        id=uuid4(),
        event_id=event_id,
        claim_key=spec.claim_key,
        claim_text=spec.claim_text,
        claim_type=spec.claim_type,
        claim_order=spec.claim_order,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    try:
        async with _begin_nested_if_available(session):
            session.add(row)
            await session.flush([row])
    except IntegrityError:
        result = await session.scalars(
            select(EventClaim).where(
                EventClaim.event_id == event_id,
                EventClaim.claim_key == spec.claim_key,
            )
        )
        row = await _await_if_needed(result.one())
    return row


async def _await_if_needed(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


@asynccontextmanager
async def _begin_nested_if_available(session: AsyncSession) -> AsyncIterator[None]:
    if not isinstance(session, AsyncSession):
        yield
        return

    async with session.begin_nested():
        yield


def _decorate_event_claim_payload(
    *,
    event: Event,
    claim_by_key: dict[str, EventClaim],
) -> None:
    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    claim_graph = claims.get("claim_graph", {})
    if isinstance(claim_graph, dict):
        nodes = claim_graph.get("nodes", [])
        if isinstance(nodes, list):
            decorated_nodes: list[Any] = []
            for node in nodes:
                if not isinstance(node, dict):
                    decorated_nodes.append(node)
                    continue
                text = node.get("text")
                claim_key = normalize_claim_key(text) if isinstance(text, str) else ""
                event_claim = claim_by_key.get(claim_key)
                decorated = dict(node)
                if event_claim is not None and event_claim.id is not None:
                    decorated["event_claim_key"] = event_claim.claim_key
                    decorated["event_claim_id"] = str(event_claim.id)
                decorated_nodes.append(decorated)
            claim_graph["nodes"] = decorated_nodes

    impacts_raw = claims.get("trend_impacts", [])
    if isinstance(impacts_raw, list):
        claims["trend_impacts"] = [
            _decorate_impact_payload(payload=payload, claim_by_key=claim_by_key)
            for payload in assign_claim_keys_to_impacts(event=event, impacts=impacts_raw)
        ]

    claims["event_claims"] = [
        {
            "event_claim_id": str(row.id),
            "event_claim_key": row.claim_key,
            "claim_text": row.claim_text,
            "claim_type": row.claim_type,
            "is_active": bool(row.is_active),
        }
        for row in sorted(
            claim_by_key.values(),
            key=lambda row: (int(row.claim_order), str(row.claim_key)),
        )
        if row.id is not None
    ]
    event.extracted_claims = claims


def _decorate_impact_payload(
    *,
    payload: Any,
    claim_by_key: dict[str, EventClaim],
) -> Any:
    if not isinstance(payload, dict):
        return payload

    claim_key = payload.get("event_claim_key")
    if not isinstance(claim_key, str) or claim_key not in claim_by_key:
        claim_key = FALLBACK_EVENT_CLAIM_KEY
    event_claim = claim_by_key[claim_key]

    enriched = dict(payload)
    enriched["event_claim_key"] = event_claim.claim_key
    enriched["event_claim_text"] = event_claim.claim_text
    if event_claim.id is not None:
        enriched["event_claim_id"] = str(event_claim.id)
    return enriched


def fallback_event_claim_id(*, claims_payload: dict[str, Any]) -> str | None:
    """Return the fallback claim id from an extracted-claims payload."""
    event_claims = claims_payload.get("event_claims", [])
    if not isinstance(event_claims, list):
        return None
    for row in event_claims:
        if not isinstance(row, dict):
            continue
        if row.get("event_claim_key") == FALLBACK_EVENT_CLAIM_KEY:
            event_claim_id = row.get("event_claim_id")
            if isinstance(event_claim_id, str) and event_claim_id.strip():
                return event_claim_id
    return None
