"""Deterministic canonical-entity normalization and event-link persistence."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.entity_models import CanonicalEntity, CanonicalEntityAlias, EventEntity

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class _EntityMention:
    name: str
    normalized_name: str
    entity_role: str
    entity_type: str


def normalize_entity_name(value: str) -> str:
    """Normalize entity names for exact bounded alias matching."""

    normalized = unicodedata.normalize("NFKC", value)
    collapsed = _WHITESPACE_RE.sub(" ", normalized).strip()
    return collapsed.casefold()


def _mentions_from_output(output: Any) -> list[_EntityMention] | None:
    model_fields_set: set[str] = getattr(output, "model_fields_set", set())
    if "entities" not in model_fields_set:
        return None
    raw_entities = getattr(output, "entities", None)
    if not isinstance(raw_entities, list):
        return []

    mentions: list[_EntityMention] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_entity in raw_entities:
        name = getattr(raw_entity, "name", "")
        normalized_name = normalize_entity_name(name)
        entity_role = getattr(raw_entity, "role", "")
        entity_type = getattr(raw_entity, "entity_type", "")
        if not normalized_name:
            continue
        dedupe_key = (entity_role, entity_type, normalized_name)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        mentions.append(
            _EntityMention(
                name=" ".join(unicodedata.normalize("NFKC", name).split()),
                normalized_name=normalized_name,
                entity_role=entity_role,
                entity_type=entity_type,
            )
        )
    return mentions


async def _load_alias_matches(
    *,
    session: AsyncSession,
    mentions: list[_EntityMention],
) -> dict[tuple[str, str], list[tuple[Any, ...]]]:
    alias_rows = (
        await session.execute(
            select(
                CanonicalEntityAlias.normalized_alias,
                CanonicalEntity.id,
                CanonicalEntity.entity_type,
                CanonicalEntity.canonical_name,
            )
            .join(
                CanonicalEntity,
                CanonicalEntity.id == CanonicalEntityAlias.canonical_entity_id,
            )
            .where(
                CanonicalEntityAlias.normalized_alias.in_(
                    sorted({mention.normalized_name for mention in mentions})
                )
            )
        )
    ).all()
    matches_by_key: dict[tuple[str, str], list[tuple[Any, ...]]] = {}
    for normalized_alias, entity_id, entity_type, canonical_name in alias_rows:
        matches_by_key.setdefault((normalized_alias, entity_type), []).append(
            (entity_id, entity_type, canonical_name)
        )
    return matches_by_key


def _add_event_entity(
    *,
    session: AsyncSession,
    event_id: Any,
    mention: _EntityMention,
    canonical_entity_id: Any | None,
    resolution_status: str,
    resolution_reason: str,
    resolution_details: dict[str, Any] | None = None,
) -> None:
    session.add(
        EventEntity(
            event_id=event_id,
            entity_role=mention.entity_role,
            entity_type=mention.entity_type,
            mention_text=mention.name,
            mention_normalized=mention.normalized_name,
            canonical_entity_id=canonical_entity_id,
            resolution_status=resolution_status,
            resolution_reason=resolution_reason,
            resolution_details=resolution_details or {},
        )
    )


async def sync_event_entities(*, session: AsyncSession, event: Any, output: Any) -> None:
    """Replace persisted event-entity rows when Tier-2 emitted an entity payload."""

    event_id = getattr(event, "id", None)
    if event_id is None:
        msg = "Event must have an id before syncing canonical entities"
        raise ValueError(msg)

    mentions = _mentions_from_output(output)
    if mentions is None:
        return

    await session.execute(delete(EventEntity).where(EventEntity.event_id == event_id))
    if not mentions:
        return

    matches_by_key = await _load_alias_matches(session=session, mentions=mentions)

    for mention in mentions:
        matches = matches_by_key.get((mention.normalized_name, mention.entity_type), [])
        if len(matches) == 1:
            entity_id, _entity_type, _canonical_name = matches[0]
            _add_event_entity(
                session=session,
                event_id=event_id,
                mention=mention,
                canonical_entity_id=entity_id,
                resolution_status="resolved",
                resolution_reason="exact_alias",
            )
            continue
        if len(matches) > 1:
            _add_event_entity(
                session=session,
                event_id=event_id,
                mention=mention,
                canonical_entity_id=None,
                resolution_status="ambiguous",
                resolution_reason="ambiguous_alias",
                resolution_details={
                    "candidate_entity_ids": [str(entity_id) for entity_id, _, _ in matches],
                    "candidate_names": [canonical_name for _, _, canonical_name in matches],
                },
            )
            continue

        canonical_entity = CanonicalEntity(
            entity_type=mention.entity_type,
            canonical_name=mention.name,
            normalized_name=mention.normalized_name,
            entity_metadata={"seed_source": "tier2"},
            is_auto_seeded=True,
        )
        session.add(canonical_entity)
        await session.flush()
        session.add(
            CanonicalEntityAlias(
                canonical_entity_id=canonical_entity.id,
                alias=mention.name,
                normalized_alias=mention.normalized_name,
            )
        )
        _add_event_entity(
            session=session,
            event_id=event_id,
            mention=mention,
            canonical_entity_id=canonical_entity.id,
            resolution_status="resolved",
            resolution_reason="seeded_new_canonical",
        )
