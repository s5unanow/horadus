from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.processing.event_clusterer import EventClusterer
from src.storage.models import Event, EventLifecycle, RawItem

pytestmark = pytest.mark.unit


def _build_item(
    *,
    item_id: UUID | None = None,
    source_id: UUID | None = None,
    title: str | None = "Sample title",
    raw_content: str = "sample raw content",
    embedding: list[float] | None = None,
) -> RawItem:
    return RawItem(
        id=item_id or uuid4(),
        source_id=source_id or uuid4(),
        external_id=f"item-{uuid4()}",
        title=title,
        raw_content=raw_content,
        content_hash="a" * 64,
        embedding=embedding,
    )


@pytest.mark.asyncio
async def test_cluster_item_creates_event_when_no_match(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title="New event title")

    async def no_existing(_item_id) -> None:
        return None

    async def no_match(_embedding, _reference_time) -> None:
        return None

    add_link = AsyncMock()
    clusterer._find_existing_event_id_for_item = no_existing
    clusterer._find_matching_event = no_match
    clusterer._add_event_link = add_link

    result = await clusterer.cluster_item(item)

    added_event = mock_db_session.add.call_args.args[0]
    assert isinstance(added_event, Event)
    assert added_event.canonical_summary == "New event title"
    assert added_event.source_count == 1
    assert added_event.primary_item_id == item.id
    assert result.created is True
    assert result.merged is False
    assert result.event_id == added_event.id
    assert add_link.await_count == 1


@pytest.mark.asyncio
async def test_cluster_item_merges_into_existing_event(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title="Updated summary")
    event = Event(
        canonical_summary="Old summary",
        source_count=2,
        unique_source_count=1,
        lifecycle_status=EventLifecycle.EMERGING.value,
        primary_item_id=uuid4(),
    )

    async def no_existing(_item_id) -> None:
        return None

    async def match_event(_embedding, _reference_time) -> tuple[Event, float]:
        return (event, 0.95)

    add_link = AsyncMock()
    update_primary = AsyncMock()

    async def count_unique(_event_id, _fallback_source_id) -> int:
        return 3

    clusterer._find_existing_event_id_for_item = no_existing
    clusterer._find_matching_event = match_event
    clusterer._add_event_link = add_link
    clusterer._update_primary_item = update_primary
    clusterer._count_unique_sources = count_unique

    result = await clusterer.cluster_item(item)

    assert event.source_count == 3
    assert event.unique_source_count == 3
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value
    assert event.confirmed_at is not None
    assert event.canonical_summary == "Updated summary"
    assert result.created is False
    assert result.merged is True
    assert result.similarity == pytest.approx(0.95)
    assert add_link.await_count == 1
    assert update_primary.await_count == 1


@pytest.mark.asyncio
async def test_cluster_item_returns_existing_link_without_reclustering(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3])
    existing_event_id = uuid4()

    async def has_existing(_item_id):
        return existing_event_id

    clusterer._find_existing_event_id_for_item = has_existing

    result = await clusterer.cluster_item(item)

    assert result.created is False
    assert result.merged is True
    assert result.event_id == existing_event_id
    assert mock_db_session.add.call_count == 0


@pytest.mark.asyncio
async def test_update_primary_item_prefers_higher_credibility(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    current_primary = uuid4()
    candidate = uuid4()
    event = Event(canonical_summary="x", primary_item_id=current_primary)

    async def credibility(item_id):
        return 0.9 if item_id == candidate else 0.4

    clusterer._source_credibility_for_item = credibility

    await clusterer._update_primary_item(event, candidate)

    assert event.primary_item_id == candidate


@pytest.mark.asyncio
async def test_update_primary_item_keeps_existing_when_candidate_lower(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    current_primary = uuid4()
    candidate = uuid4()
    event = Event(canonical_summary="x", primary_item_id=current_primary)

    async def credibility(item_id):
        return 0.4 if item_id == candidate else 0.9

    clusterer._source_credibility_for_item = credibility

    await clusterer._update_primary_item(event, candidate)

    assert event.primary_item_id == current_primary
