from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.processing.embedding_service import EmbeddingService
from src.storage.models import Event, RawItem

pytestmark = pytest.mark.unit


@dataclass(slots=True)
class FakeEmbeddingsAPI:
    dimensions: int
    calls: list[tuple[str, list[str]]]

    async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
        self.calls.append((model, input))
        data = []
        for index, text in enumerate(input):
            base = float(sum(ord(char) for char in text) % 1000)
            vector = [base + float(offset) for offset in range(self.dimensions)]
            data.append(SimpleNamespace(index=index, embedding=vector))
        return SimpleNamespace(data=data)


def _build_service(
    *, mock_db_session, dimensions: int = 3, batch_size: int = 2
) -> tuple[
    EmbeddingService,
    FakeEmbeddingsAPI,
]:
    embeddings_api = FakeEmbeddingsAPI(dimensions=dimensions, calls=[])
    client = SimpleNamespace(embeddings=embeddings_api)
    service = EmbeddingService(
        session=mock_db_session,
        client=client,
        model="test-embedding-model",
        dimensions=dimensions,
        batch_size=batch_size,
    )
    return service, embeddings_api


@pytest.mark.asyncio
async def test_embed_texts_batches_requests_and_counts_cache_hits(mock_db_session) -> None:
    service, embeddings_api = _build_service(mock_db_session=mock_db_session, batch_size=2)

    vectors, cache_hits, api_calls = await service.embed_texts(
        ["alpha", "beta", "alpha", "  gamma  "]
    )

    assert len(vectors) == 4
    assert vectors[0] == vectors[2]
    assert cache_hits == 0
    assert api_calls == 2
    assert embeddings_api.calls == [
        ("test-embedding-model", ["alpha", "beta"]),
        ("test-embedding-model", ["gamma"]),
    ]


@pytest.mark.asyncio
async def test_embed_texts_reuses_cache_across_calls(mock_db_session) -> None:
    service, embeddings_api = _build_service(mock_db_session=mock_db_session, batch_size=8)

    first = await service.embed_text("cached")
    vectors, cache_hits, api_calls = await service.embed_texts(["cached", "new"])

    assert vectors[0] == first
    assert cache_hits == 1
    assert api_calls == 1
    assert len(embeddings_api.calls) == 2


@pytest.mark.asyncio
async def test_embed_text_rejects_blank_input(mock_db_session) -> None:
    service, _ = _build_service(mock_db_session=mock_db_session)

    with pytest.raises(ValueError, match="must not be empty"):
        await service.embed_text("   ")


@pytest.mark.asyncio
async def test_request_embeddings_rejects_dimension_mismatch(mock_db_session) -> None:
    service, _ = _build_service(mock_db_session=mock_db_session, dimensions=3)

    class WrongEmbeddingsAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[1.0, 2.0])])

    service.client = SimpleNamespace(embeddings=WrongEmbeddingsAPI())

    with pytest.raises(ValueError, match="dimension mismatch"):
        await service.embed_text("one")


@pytest.mark.asyncio
async def test_embed_raw_items_without_embedding_persists_vectors(mock_db_session) -> None:
    service, _ = _build_service(mock_db_session=mock_db_session)
    first_item = RawItem(
        source_id=uuid4(),
        external_id="raw-1",
        raw_content="first text",
        content_hash="a" * 64,
    )
    second_item = RawItem(
        source_id=uuid4(),
        external_id="raw-2",
        raw_content="second text",
        content_hash="b" * 64,
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [first_item, second_item])

    async def fake_embed_texts(_texts: list[str]) -> tuple[list[list[float]], int, int]:
        return ([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], 1, 1)

    service.embed_texts = fake_embed_texts

    result = await service.embed_raw_items_without_embedding(limit=10)

    assert first_item.embedding == [1.0, 2.0, 3.0]
    assert second_item.embedding == [4.0, 5.0, 6.0]
    assert result.entity_type == "raw_items"
    assert result.scanned == 2
    assert result.embedded == 2
    assert result.cache_hits == 1
    assert result.api_calls == 1
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_embed_events_without_embedding_persists_vectors(mock_db_session) -> None:
    service, _ = _build_service(mock_db_session=mock_db_session)
    first_event = Event(canonical_summary="first summary")
    second_event = Event(canonical_summary="second summary")
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [first_event, second_event])

    async def fake_embed_texts(_texts: list[str]) -> tuple[list[list[float]], int, int]:
        return ([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], 0, 1)

    service.embed_texts = fake_embed_texts

    result = await service.embed_events_without_embedding(limit=10)

    assert first_event.embedding == [0.1, 0.2, 0.3]
    assert second_event.embedding == [0.4, 0.5, 0.6]
    assert result.entity_type == "events"
    assert result.scanned == 2
    assert result.embedded == 2
    assert result.cache_hits == 0
    assert result.api_calls == 1
    assert mock_db_session.flush.await_count == 1
