from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

import src.processing.event_clusterer as event_clusterer_module
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
    item.embedding_model = "text-embedding-3-small"

    async def no_existing(_item_id) -> None:
        return None

    async def no_match(_embedding, _embedding_model, _reference_time) -> None:
        return None

    add_link = AsyncMock(return_value=True)
    clusterer._find_existing_event_id_for_item = no_existing
    clusterer._find_matching_event = no_match
    clusterer._add_event_link = add_link
    clusterer._refresh_event_provenance = AsyncMock()

    result = await clusterer.cluster_item(item)

    added_event = mock_db_session.add.call_args.args[0]
    assert isinstance(added_event, Event)
    assert added_event.canonical_summary == "New event title"
    assert added_event.embedding_model == "text-embedding-3-small"
    assert added_event.embedding_generated_at is None
    assert added_event.source_count == 1
    assert added_event.primary_item_id == item.id
    assert added_event.provenance_summary["cluster_health"][
        "cluster_cohesion_score"
    ] == pytest.approx(1.0)
    assert added_event.provenance_summary["cluster_health"]["split_risk_score"] == pytest.approx(
        0.0
    )
    assert result.created is True
    assert result.merged is False
    assert result.event_id == added_event.id
    assert add_link.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("title", "raw_content"),
    [
        ("Border update", "Troops moved near the border overnight."),
        ("Оновлення кордону", "Підрозділи були перекинуті до прикордонного району."),
        ("Обновление границы", "Подразделения были переброшены в приграничный район."),
    ],
)
async def test_cluster_item_handles_launch_languages(
    mock_db_session,
    title: str,
    raw_content: str,
) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title=title, raw_content=raw_content)
    item.embedding_model = "text-embedding-3-small"

    clusterer._find_existing_event_id_for_item = AsyncMock(return_value=None)
    clusterer._find_matching_event = AsyncMock(return_value=None)
    clusterer._add_event_link = AsyncMock()
    clusterer._refresh_event_provenance = AsyncMock()

    result = await clusterer.cluster_item(item)

    assert result.created is True
    assert result.merged is False


@pytest.mark.asyncio
async def test_cluster_item_merges_into_existing_event(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title="Updated summary")
    item.embedding_model = "text-embedding-3-small"
    event = Event(
        canonical_summary="Old summary",
        source_count=2,
        unique_source_count=1,
        lifecycle_status=EventLifecycle.EMERGING.value,
        primary_item_id=uuid4(),
    )

    async def no_existing(_item_id) -> None:
        return None

    async def match_event(_embedding, _embedding_model, _reference_time) -> tuple[Event, float]:
        return (event, 0.95)

    add_link = AsyncMock()
    update_primary = AsyncMock(return_value=True)

    async def count_unique(_event_id, _fallback_source_id) -> int:
        return 3

    clusterer._find_existing_event_id_for_item = no_existing
    clusterer._find_matching_event = match_event
    clusterer._add_event_link = add_link
    clusterer._update_primary_item = update_primary
    clusterer._count_unique_sources = count_unique

    async def refresh_provenance(target_event: Event) -> None:
        target_event.independent_evidence_count = target_event.unique_source_count
        target_event.corroboration_score = Decimal(target_event.unique_source_count)
        target_event.corroboration_mode = "provenance_aware"
        target_event.provenance_summary = {"method": "provenance_aware"}

    clusterer._refresh_event_provenance = AsyncMock(side_effect=refresh_provenance)

    result = await clusterer.cluster_item(item)

    assert event.source_count == 3
    assert event.unique_source_count == 3
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value
    assert event.confirmed_at is not None
    assert event.canonical_summary == "Updated summary"
    assert event.embedding_model == "text-embedding-3-small"
    assert result.created is False
    assert result.merged is True
    assert result.similarity == pytest.approx(0.95)
    assert event.provenance_summary["cluster_health"]["cluster_cohesion_score"] == pytest.approx(
        0.983333,
        rel=1e-5,
    )
    assert event.provenance_summary["cluster_health"]["split_risk_score"] == pytest.approx(0.05)
    assert add_link.await_count == 1
    assert update_primary.await_count == 1


@pytest.mark.asyncio
async def test_cluster_item_links_before_unique_source_recount(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title="Threshold mention")
    item.embedding_model = "text-embedding-3-small"
    event = Event(
        canonical_summary="Emerging event",
        source_count=2,
        unique_source_count=2,
        lifecycle_status=EventLifecycle.EMERGING.value,
        primary_item_id=uuid4(),
    )
    link_state = {"added": False}

    async def no_existing(_item_id):
        return None

    async def match_event(_embedding, _embedding_model, _reference_time):
        return (event, 0.9)

    async def add_link(_event_id, _item_id):
        link_state["added"] = True
        return True

    async def count_unique(_event_id, _fallback_source_id):
        assert link_state["added"] is True
        return 3

    clusterer._find_existing_event_id_for_item = no_existing
    clusterer._find_matching_event = match_event
    clusterer._add_event_link = add_link
    clusterer._count_unique_sources = count_unique
    clusterer._update_primary_item = AsyncMock(return_value=True)

    async def refresh_provenance(target_event: Event) -> None:
        target_event.independent_evidence_count = target_event.unique_source_count

    clusterer._refresh_event_provenance = AsyncMock(side_effect=refresh_provenance)

    result = await clusterer.cluster_item(item)

    assert result.merged is True
    assert event.unique_source_count == 3
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value
    assert event.confirmed_at is not None


@pytest.mark.asyncio
async def test_cluster_item_skips_merge_when_link_already_exists(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title="Duplicate merge")
    item.embedding_model = "text-embedding-3-small"
    event = Event(
        canonical_summary="Existing event",
        source_count=2,
        unique_source_count=2,
        lifecycle_status=EventLifecycle.EMERGING.value,
        primary_item_id=uuid4(),
    )
    merge_into_event = AsyncMock()

    clusterer._find_existing_event_id_for_item = AsyncMock(return_value=None)
    clusterer._find_matching_event = AsyncMock(return_value=(event, 0.93))
    clusterer._add_event_link = AsyncMock(return_value=False)
    clusterer._merge_into_event = merge_into_event
    clusterer._refresh_event_provenance = AsyncMock()

    result = await clusterer.cluster_item(item)

    assert result.merged is True
    assert event.source_count == 2
    assert event.unique_source_count == 2
    merge_into_event.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_item_keeps_canonical_summary_when_primary_does_not_change(
    mock_db_session,
) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title="Newest mention")
    item.embedding_model = "text-embedding-3-small"
    event = Event(
        canonical_summary="Primary summary",
        source_count=2,
        unique_source_count=2,
        lifecycle_status=EventLifecycle.CONFIRMED.value,
        primary_item_id=uuid4(),
    )

    clusterer._find_existing_event_id_for_item = AsyncMock(return_value=None)
    clusterer._find_matching_event = AsyncMock(return_value=(event, 0.89))
    clusterer._add_event_link = AsyncMock(return_value=True)
    clusterer._count_unique_sources = AsyncMock(return_value=3)
    clusterer._update_primary_item = AsyncMock(return_value=False)

    result = await clusterer.cluster_item(item)

    assert result.merged is True
    assert event.canonical_summary == "Primary summary"


@pytest.mark.asyncio
async def test_cluster_item_returns_existing_event_id_when_link_conflicts(
    mock_db_session,
) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title="Concurrent link conflict")
    item.embedding_model = "text-embedding-3-small"
    matched_event = Event(
        canonical_summary="Candidate event",
        source_count=2,
        unique_source_count=2,
        lifecycle_status=EventLifecycle.EMERGING.value,
        primary_item_id=uuid4(),
    )
    existing_event_id = uuid4()
    merge_into_event = AsyncMock()

    clusterer._find_existing_event_id_for_item = AsyncMock(side_effect=[None, existing_event_id])
    clusterer._find_matching_event = AsyncMock(return_value=(matched_event, 0.88))
    clusterer._add_event_link = AsyncMock(return_value=False)
    clusterer._merge_into_event = merge_into_event

    result = await clusterer.cluster_item(item)

    assert result.created is False
    assert result.merged is True
    assert result.event_id == existing_event_id
    merge_into_event.assert_not_called()


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
async def test_cluster_item_without_embedding_model_skips_similarity_matching(
    mock_db_session,
) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3])
    item.embedding_model = None

    async def no_existing(_item_id):
        return None

    find_matching = AsyncMock()
    add_link = AsyncMock(return_value=True)
    clusterer._find_existing_event_id_for_item = no_existing
    clusterer._find_matching_event = find_matching
    clusterer._add_event_link = add_link

    result = await clusterer.cluster_item(item)

    assert result.created is True
    assert result.merged is False
    assert find_matching.await_count == 0
    assert add_link.await_count == 1


@pytest.mark.asyncio
async def test_update_primary_item_prefers_higher_credibility(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    current_primary = uuid4()
    candidate = uuid4()
    event = Event(canonical_summary="x", primary_item_id=current_primary)

    async def credibility(item_id):
        return 0.9 if item_id == candidate else 0.4

    clusterer._source_credibility_for_item = credibility

    changed = await clusterer._update_primary_item(event, candidate)

    assert changed is True
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

    changed = await clusterer._update_primary_item(event, candidate)

    assert changed is False
    assert event.primary_item_id == current_primary


@pytest.mark.asyncio
async def test_find_matching_event_filters_by_embedding_model(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: None)

    result = await clusterer._find_matching_event(
        item_embedding=[0.1, 0.2, 0.3],
        embedding_model="text-embedding-3-small",
        reference_time=datetime.now(tz=UTC),
    )

    assert result is None
    query = mock_db_session.execute.await_args.args[0]
    assert "events.embedding_model =" in str(query)


@pytest.mark.asyncio
async def test_cluster_item_skips_merge_for_suppressed_event(mock_db_session, monkeypatch) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3], title="Suppressed merge attempt")
    item.embedding_model = "text-embedding-3-small"
    event = Event(
        canonical_summary="Suppressed event",
        source_count=5,
        unique_source_count=3,
        lifecycle_status=EventLifecycle.ARCHIVED.value,
        primary_item_id=uuid4(),
    )
    merge_into_event = AsyncMock()
    add_event_link = AsyncMock()
    suppression_metric_calls: list[tuple[str, str]] = []

    def _record_suppression(*, action: str, stage: str) -> None:
        suppression_metric_calls.append((action, stage))

    clusterer._find_existing_event_id_for_item = AsyncMock(return_value=None)
    clusterer._find_matching_event = AsyncMock(return_value=(event, 0.91))
    clusterer._merge_into_event = merge_into_event
    clusterer._add_event_link = add_event_link
    clusterer._event_suppression_action = AsyncMock(return_value="invalidate")
    monkeypatch.setattr(
        event_clusterer_module,
        "record_processing_event_suppression",
        _record_suppression,
    )

    result = await clusterer.cluster_item(item)

    assert result.created is False
    assert result.merged is False
    assert result.event_id == event.id
    assert result.similarity == pytest.approx(0.91)
    assert event.lifecycle_status == EventLifecycle.ARCHIVED.value
    merge_into_event.assert_not_called()
    add_event_link.assert_not_called()
    assert suppression_metric_calls == [("invalidate", "clusterer_pre_merge")]


@pytest.mark.asyncio
async def test_cluster_item_requires_item_id(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(item_id=uuid4())
    item.id = None

    with pytest.raises(ValueError, match="RawItem must have an id"):
        await clusterer.cluster_item(item)


@pytest.mark.asyncio
async def test_cluster_item_creates_event_when_embedding_is_missing(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=None)
    clusterer._find_existing_event_id_for_item = AsyncMock(return_value=None)
    clusterer._add_event_link = AsyncMock(return_value=True)

    result = await clusterer.cluster_item(item)

    assert result.created is True
    assert result.merged is False
    clusterer._add_event_link.assert_awaited_once()


@pytest.mark.asyncio
async def test_cluster_item_treats_blank_embedding_model_as_missing(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.1, 0.2, 0.3])
    item.embedding_model = "   "
    clusterer._find_existing_event_id_for_item = AsyncMock(return_value=None)
    clusterer._find_matching_event = AsyncMock()
    clusterer._add_event_link = AsyncMock(return_value=True)

    result = await clusterer.cluster_item(item)

    assert result.created is True
    assert result.merged is False
    clusterer._find_matching_event.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_unlinked_items_clusters_each_result_and_flushes(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    items = [_build_item(), _build_item()]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: items)
    clusterer.cluster_item = AsyncMock(
        side_effect=[
            SimpleNamespace(item_id=items[0].id),
            SimpleNamespace(item_id=items[1].id),
        ]
    )

    results = await clusterer.cluster_unlinked_items(limit=2)

    assert [result.item_id for result in results] == [items[0].id, items[1].id]
    assert mock_db_session.flush.await_count >= 1


@pytest.mark.asyncio
async def test_create_event_assigns_id_and_uses_item_timestamp(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    published_at = datetime(2026, 3, 1, tzinfo=UTC)
    item = _build_item(title=None, raw_content="  body  ", embedding=[0.1])
    item.published_at = published_at

    event = await clusterer._create_event(item)

    assert event.id is not None
    assert event.first_seen_at == published_at
    assert event.last_mention_at == published_at
    assert event.canonical_summary == "body"


@pytest.mark.asyncio
async def test_create_event_preserves_preexisting_event_id(
    mock_db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing_id = uuid4()

    class FakeEvent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.id = existing_id

    monkeypatch.setattr(event_clusterer_module, "Event", FakeEvent)
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item()

    event = await clusterer._create_event(item)

    assert event.id == existing_id


@pytest.mark.asyncio
async def test_merge_into_event_populates_embedding_and_preserves_summary_when_primary_unchanged(
    mock_db_session,
) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.5, 0.6], title="new summary")
    item.embedding_model = "text-embedding-3-small"
    item.embedding_generated_at = datetime(2026, 3, 1, tzinfo=UTC)
    item.fetched_at = datetime(2026, 3, 2, tzinfo=UTC)
    event = Event(
        canonical_summary="old summary",
        source_count=1,
        unique_source_count=1,
        primary_item_id=uuid4(),
        embedding=None,
    )
    clusterer._update_primary_item = AsyncMock(return_value=False)
    clusterer._count_unique_sources = AsyncMock(return_value=2)
    clusterer.lifecycle_manager.on_event_mention = MagicMock()

    await clusterer._merge_into_event(event, item, similarity=0.91)

    assert event.embedding == [0.5, 0.6]
    assert event.embedding_model == "text-embedding-3-small"
    assert event.embedding_generated_at == item.embedding_generated_at
    assert event.canonical_summary == "old summary"
    clusterer.lifecycle_manager.on_event_mention.assert_called_once()


@pytest.mark.asyncio
async def test_merge_into_event_preserves_existing_embedding(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=None, title="irrelevant")
    item.fetched_at = datetime(2026, 3, 2, tzinfo=UTC)
    event = Event(
        canonical_summary="summary",
        source_count=1,
        unique_source_count=1,
        primary_item_id=uuid4(),
        embedding=[0.1, 0.2],
        embedding_model="old-model",
    )
    clusterer._update_primary_item = AsyncMock(return_value=False)
    clusterer._count_unique_sources = AsyncMock(return_value=1)
    clusterer.lifecycle_manager.on_event_mention = MagicMock()

    await clusterer._merge_into_event(event, item, similarity=0.88)

    assert event.embedding == [0.1, 0.2]
    assert event.embedding_model == "old-model"


@pytest.mark.asyncio
async def test_merge_into_event_preserves_prior_cluster_health_after_provenance_refresh(
    mock_db_session,
) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    item = _build_item(embedding=[0.4, 0.5], title="follow-up")
    item.embedding_model = "text-embedding-3-small"
    item.fetched_at = datetime(2026, 3, 2, tzinfo=UTC)
    event = Event(
        canonical_summary="summary",
        source_count=2,
        unique_source_count=2,
        primary_item_id=uuid4(),
        embedding=[0.1, 0.2],
        embedding_model="old-model",
    )
    event.provenance_summary = {
        "method": "provenance_aware",
        "cluster_health": {
            "cluster_cohesion_score": 0.6,
            "split_risk_score": 0.4,
        },
    }
    clusterer._update_primary_item = AsyncMock(return_value=False)
    clusterer._count_unique_sources = AsyncMock(return_value=3)
    clusterer.lifecycle_manager.on_event_mention = MagicMock()

    async def refresh_provenance(target_event: Event) -> None:
        target_event.provenance_summary = {"method": "provenance_aware"}

    clusterer._refresh_event_provenance = AsyncMock(side_effect=refresh_provenance)

    await clusterer._merge_into_event(event, item, similarity=0.95)

    assert event.provenance_summary["cluster_health"]["cluster_cohesion_score"] == pytest.approx(
        0.716667,
        rel=1e-5,
    )
    assert event.provenance_summary["cluster_health"]["split_risk_score"] == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_find_matching_event_returns_similarity(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    event = Event(canonical_summary="match")
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: (event, 0.2))

    matched = await clusterer._find_matching_event(
        item_embedding=[0.1, 0.2],
        embedding_model="text-embedding-3-small",
        reference_time=datetime(2026, 3, 2, tzinfo=UTC),
    )

    assert matched is not None
    matched_event, similarity = matched
    assert matched_event is event
    assert similarity == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_find_existing_event_id_for_item_returns_scalar_value(mock_db_session) -> None:
    event_id = uuid4()
    mock_db_session.scalar.return_value = event_id
    clusterer = EventClusterer(session=mock_db_session)

    assert await clusterer._find_existing_event_id_for_item(uuid4()) == event_id


@pytest.mark.asyncio
async def test_event_suppression_action_normalizes_and_filters_values(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    mock_db_session.scalar.side_effect = [None, " archive ", " mark_noise "]

    assert await clusterer._event_suppression_action(event_id=uuid4()) is None
    assert await clusterer._event_suppression_action(event_id=uuid4()) is None
    assert await clusterer._event_suppression_action(event_id=uuid4()) == "mark_noise"


@pytest.mark.asyncio
async def test_add_event_link_returns_true_on_insert_and_false_on_conflict(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    event_id = uuid4()
    item_id = uuid4()

    @asynccontextmanager
    async def ok_nested():
        yield

    @asynccontextmanager
    async def fail_nested():
        raise IntegrityError("stmt", "params", "orig")
        yield

    mock_db_session.begin_nested.side_effect = [ok_nested(), fail_nested()]

    assert await clusterer._add_event_link(event_id, item_id) is True
    assert await clusterer._add_event_link(event_id, item_id) is False


@pytest.mark.asyncio
async def test_count_unique_sources_uses_fallback_when_query_returns_empty(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    fallback_source_id = uuid4()
    mock_db_session.scalar.side_effect = [None, 0, 3]

    assert await clusterer._count_unique_sources(uuid4(), fallback_source_id) == 1
    assert await clusterer._count_unique_sources(uuid4(), None) == 0
    assert await clusterer._count_unique_sources(uuid4(), fallback_source_id) == 3


@pytest.mark.asyncio
async def test_update_primary_item_uses_candidate_when_event_has_no_primary(
    mock_db_session,
) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    candidate = uuid4()
    event = Event(canonical_summary="x", primary_item_id=None)

    changed = await clusterer._update_primary_item(event, candidate)

    assert changed is True
    assert event.primary_item_id == candidate


@pytest.mark.asyncio
async def test_source_credibility_for_item_handles_none_and_bad_values(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    mock_db_session.scalar.side_effect = [None, "bad-value", Decimal("0.8")]

    assert await clusterer._source_credibility_for_item(uuid4()) == 0.0
    assert await clusterer._source_credibility_for_item(uuid4()) == 0.0
    assert await clusterer._source_credibility_for_item(uuid4()) == pytest.approx(0.8)


def test_build_canonical_summary_prefers_title_and_truncates_content() -> None:
    title_item = _build_item(title="  canonical title  ", raw_content="ignored")
    long_content_item = _build_item(title=None, raw_content="x" * 500)

    assert EventClusterer._build_canonical_summary(title_item) == "canonical title"
    assert len(EventClusterer._build_canonical_summary(long_content_item)) == 400


def test_item_timestamp_prefers_published_then_fetched_then_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_at = datetime(2026, 3, 1, tzinfo=UTC)
    fetched_at = datetime(2026, 3, 2, tzinfo=UTC)
    fallback_now = datetime(2026, 3, 3, tzinfo=UTC)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            _ = tz
            return fallback_now

    published_item = _build_item()
    published_item.published_at = published_at
    published_item.fetched_at = fetched_at

    fetched_item = _build_item()
    fetched_item.published_at = None
    fetched_item.fetched_at = fetched_at

    missing_item = _build_item()
    missing_item.published_at = None
    missing_item.fetched_at = None

    monkeypatch.setattr(event_clusterer_module, "datetime", FixedDatetime)

    assert EventClusterer._item_timestamp(published_item) == published_at
    assert EventClusterer._item_timestamp(fetched_item) == fetched_at
    assert EventClusterer._item_timestamp(missing_item) == fallback_now


@pytest.mark.asyncio
async def test_refresh_event_provenance_handles_async_row_collection(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    event = Event(
        id=uuid4(),
        canonical_summary="Async provenance rows",
        source_count=1,
        unique_source_count=1,
    )

    async def async_all():
        return [
            (
                uuid4(),
                "Reuters",
                "https://www.reuters.com",
                "wire",
                "secondary",
                "https://example.test/story",
                "Story title",
                "Reuters staff",
                "a" * 64,
            )
        ]

    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(all=async_all))

    await clusterer._refresh_event_provenance(event)

    assert event.independent_evidence_count == 1
    assert event.corroboration_mode == "provenance_aware"


@pytest.mark.asyncio
async def test_refresh_event_provenance_handles_sync_row_collection(mock_db_session) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    event = Event(
        id=uuid4(),
        canonical_summary="Sync provenance rows",
        source_count=1,
        unique_source_count=1,
    )
    rows = [
        (
            uuid4(),
            "Reuters",
            "https://www.reuters.com",
            "wire",
            "secondary",
            "https://example.test/story",
            "Story title",
            "Reuters staff",
            "a" * 64,
        )
    ]
    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))

    await clusterer._refresh_event_provenance(event)

    assert event.independent_evidence_count == 1
    assert event.corroboration_mode == "provenance_aware"
