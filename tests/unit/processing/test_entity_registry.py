from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.processing.entity_registry import normalize_entity_name, sync_event_entities
from src.processing.tier2_runtime import Tier2Output
from src.storage.entity_models import CanonicalEntity, CanonicalEntityAlias, EventEntity

pytestmark = pytest.mark.unit


class _FakeSession:
    def __init__(self, execute_results: list[object]) -> None:
        self._execute_results = iter(execute_results)
        self.execute = AsyncMock(side_effect=self._execute)
        self.flush = AsyncMock(side_effect=self._flush)
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def _execute(self, _query: object) -> object:
        return next(self._execute_results)

    async def _flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()


def _tier2_output(*, entities: list[dict[str, str]] | None = None) -> Tier2Output:
    payload = {
        "summary": "Summary",
        "extracted_who": ["Actor"],
        "extracted_what": "What happened",
        "extracted_where": "Where",
        "claims": ["Claim"],
        "categories": ["security"],
    }
    if entities is not None:
        payload["entities"] = entities
    return Tier2Output.model_validate(payload)


def test_normalize_entity_name_casefolds_and_collapses_spacing() -> None:
    assert normalize_entity_name("  NATO\tAlliance  ") == "nato alliance"
    assert normalize_entity_name("  \u041d\u0410\u0422\u041e  ") == "\u043d\u0430\u0442\u043e"


@pytest.mark.asyncio
async def test_sync_event_entities_is_noop_when_entities_field_missing() -> None:
    session = _FakeSession(execute_results=[])

    await sync_event_entities(
        session=session,
        event=SimpleNamespace(id=uuid4()),
        output=_tier2_output(),
    )

    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()
    assert session.added == []


@pytest.mark.asyncio
async def test_sync_event_entities_rejects_events_without_ids() -> None:
    session = _FakeSession(execute_results=[])

    with pytest.raises(ValueError, match="must have an id"):
        await sync_event_entities(
            session=session,
            event=SimpleNamespace(id=None),
            output=_tier2_output(entities=[]),
        )


@pytest.mark.asyncio
async def test_sync_event_entities_ignores_non_list_entity_payloads_after_delete() -> None:
    session = _FakeSession(execute_results=[SimpleNamespace()])

    await sync_event_entities(
        session=session,
        event=SimpleNamespace(id=uuid4()),
        output=SimpleNamespace(model_fields_set={"entities"}, entities="bad"),
    )

    session.execute.assert_awaited_once()
    session.flush.assert_not_awaited()
    assert session.added == []


@pytest.mark.asyncio
async def test_sync_event_entities_deletes_existing_rows_when_entities_explicitly_empty() -> None:
    session = _FakeSession(execute_results=[SimpleNamespace()])

    await sync_event_entities(
        session=session,
        event=SimpleNamespace(id=uuid4()),
        output=_tier2_output(entities=[]),
    )

    session.execute.assert_awaited_once()
    session.flush.assert_not_awaited()
    assert session.added == []


@pytest.mark.asyncio
async def test_sync_event_entities_resolves_mixed_language_alias() -> None:
    canonical_entity_id = uuid4()
    session = _FakeSession(
        execute_results=[
            SimpleNamespace(),
            SimpleNamespace(all=lambda: [("нато", canonical_entity_id, "organization", "NATO")]),
        ]
    )

    await sync_event_entities(
        session=session,
        event=SimpleNamespace(id=uuid4()),
        output=_tier2_output(
            entities=[
                {
                    "name": "\u041d\u0410\u0422\u041e",
                    "entity_type": "organization",
                    "role": "actor",
                },
            ]
        ),
    )

    persisted = [obj for obj in session.added if isinstance(obj, EventEntity)]
    assert len(persisted) == 1
    assert persisted[0].mention_normalized == "нато"
    assert persisted[0].canonical_entity_id == canonical_entity_id
    assert persisted[0].resolution_status == "resolved"
    assert persisted[0].resolution_reason == "exact_alias"


@pytest.mark.asyncio
async def test_sync_event_entities_deduplicates_mentions_and_skips_blank_names() -> None:
    canonical_entity_id = uuid4()
    session = _FakeSession(
        execute_results=[
            SimpleNamespace(),
            SimpleNamespace(all=lambda: [("nato", canonical_entity_id, "organization", "NATO")]),
        ]
    )

    await sync_event_entities(
        session=session,
        event=SimpleNamespace(id=uuid4()),
        output=SimpleNamespace(
            model_fields_set={"entities"},
            entities=[
                SimpleNamespace(name="  ", entity_type="organization", role="actor"),
                SimpleNamespace(name="NATO", entity_type="organization", role="actor"),
                SimpleNamespace(name=" NATO ", entity_type="organization", role="actor"),
            ],
        ),
    )

    persisted = [obj for obj in session.added if isinstance(obj, EventEntity)]
    assert len(persisted) == 1
    assert persisted[0].mention_text == "NATO"


@pytest.mark.asyncio
async def test_sync_event_entities_marks_ambiguous_aliases_unresolved() -> None:
    session = _FakeSession(
        execute_results=[
            SimpleNamespace(),
            SimpleNamespace(
                all=lambda: [
                    ("border guard", uuid4(), "organization", "Border Guard Alpha"),
                    ("border guard", uuid4(), "organization", "Border Guard Beta"),
                ]
            ),
        ]
    )

    await sync_event_entities(
        session=session,
        event=SimpleNamespace(id=uuid4()),
        output=_tier2_output(
            entities=[
                {
                    "name": "Border Guard",
                    "entity_type": "organization",
                    "role": "actor",
                }
            ]
        ),
    )

    persisted = [obj for obj in session.added if isinstance(obj, EventEntity)]
    assert len(persisted) == 1
    assert persisted[0].canonical_entity_id is None
    assert persisted[0].resolution_status == "ambiguous"
    assert persisted[0].resolution_reason == "ambiguous_alias"


@pytest.mark.asyncio
async def test_sync_event_entities_seeds_new_canonical_rows_when_no_match_exists() -> None:
    session = _FakeSession(
        execute_results=[
            SimpleNamespace(),
            SimpleNamespace(all=list),
        ]
    )

    await sync_event_entities(
        session=session,
        event=SimpleNamespace(id=uuid4()),
        output=_tier2_output(
            entities=[
                {"name": "Kyiv", "entity_type": "location", "role": "location"},
            ]
        ),
    )

    canonical_entities = [obj for obj in session.added if isinstance(obj, CanonicalEntity)]
    aliases = [obj for obj in session.added if isinstance(obj, CanonicalEntityAlias)]
    event_entities = [obj for obj in session.added if isinstance(obj, EventEntity)]

    assert len(canonical_entities) == 1
    assert canonical_entities[0].canonical_name == "Kyiv"
    assert canonical_entities[0].is_auto_seeded is True
    assert len(aliases) == 1
    assert aliases[0].normalized_alias == "kyiv"
    assert len(event_entities) == 1
    assert event_entities[0].canonical_entity_id == canonical_entities[0].id
    assert event_entities[0].resolution_reason == "seeded_new_canonical"


def test_tier2_output_rejects_location_role_with_non_location_type() -> None:
    with pytest.raises(ValueError, match="Location-role entities"):
        _tier2_output(
            entities=[
                {"name": "Kyiv", "entity_type": "organization", "role": "location"},
            ]
        )


def test_tier2_output_rejects_actor_role_with_location_type() -> None:
    with pytest.raises(ValueError, match="Actor-role entities"):
        _tier2_output(
            entities=[
                {"name": "Kyiv", "entity_type": "location", "role": "actor"},
            ]
        )
