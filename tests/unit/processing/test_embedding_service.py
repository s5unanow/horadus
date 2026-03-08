from __future__ import annotations

import sys
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.processing.embedding_service import EmbeddingInputAudit, EmbeddingService
from src.storage.models import Event, RawItem

embedding_service_module = sys.modules[EmbeddingService.__module__]

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
    *,
    mock_db_session,
    dimensions: int = 3,
    batch_size: int = 2,
    cache_max_size: int = 128,
    max_input_tokens: int = 8191,
    input_policy: str = "truncate",
    token_estimate_chars_per_token: int = 4,
) -> tuple[
    EmbeddingService,
    FakeEmbeddingsAPI,
    SimpleNamespace,
]:
    embeddings_api = FakeEmbeddingsAPI(dimensions=dimensions, calls=[])
    client = SimpleNamespace(embeddings=embeddings_api)
    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )
    service = EmbeddingService(
        session=mock_db_session,
        client=client,
        model="test-embedding-model",
        dimensions=dimensions,
        batch_size=batch_size,
        cache_max_size=cache_max_size,
        max_input_tokens=max_input_tokens,
        input_policy=input_policy,
        token_estimate_chars_per_token=token_estimate_chars_per_token,
        cost_tracker=cost_tracker,
    )
    return service, embeddings_api, cost_tracker


@pytest.mark.asyncio
async def test_embed_texts_batches_requests_and_counts_cache_hits(mock_db_session) -> None:
    service, embeddings_api, cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        batch_size=2,
    )

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
    assert cost_tracker.ensure_within_budget.await_count == 2
    assert cost_tracker.record_usage.await_count == 2


@pytest.mark.asyncio
async def test_embed_texts_reuses_cache_across_calls(mock_db_session) -> None:
    service, embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        batch_size=8,
    )

    first = await service.embed_text("cached")
    vectors, cache_hits, api_calls = await service.embed_texts(["cached", "new"])

    assert vectors[0] == first
    assert cache_hits == 1
    assert api_calls == 1
    assert len(embeddings_api.calls) == 2


@pytest.mark.asyncio
async def test_embed_texts_evicts_least_recent_cache_entry(mock_db_session) -> None:
    service, embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        batch_size=4,
        cache_max_size=2,
    )

    await service.embed_texts(["alpha", "beta"])
    await service.embed_text("alpha")
    await service.embed_text("gamma")
    _vector, cache_hits, api_calls = await service.embed_texts(["beta"])

    assert cache_hits == 0
    assert api_calls == 1
    assert embeddings_api.calls[-1] == ("test-embedding-model", ["beta"])


@pytest.mark.asyncio
async def test_embed_text_rejects_blank_input(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)

    with pytest.raises(ValueError, match="must not be empty"):
        await service.embed_text("   ")


def test_create_client_requires_api_key(mock_db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedding_service_module.settings, "OPENAI_API_KEY", "")

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        EmbeddingService(session=mock_db_session, client=None)


def test_create_client_uses_configured_api_key(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_factory = MagicMock(return_value="client")

    monkeypatch.setattr(embedding_service_module.settings, "OPENAI_API_KEY", "stub-value")
    monkeypatch.setattr(embedding_service_module, "AsyncOpenAI", client_factory)

    service = EmbeddingService(
        session=mock_db_session,
        client=None,
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
    )

    assert service.client == "client"
    client_factory.assert_called_once_with(api_key="stub-value")  # pragma: allowlist secret


def test_last_input_audits_returns_tuple_snapshot(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)
    service._last_input_audits = [
        EmbeddingInputAudit(
            original_tokens=3,
            retained_tokens=3,
            strategy="none",
            was_truncated=False,
            dropped_tail_tokens=0,
            chunk_count=1,
        )
    ]

    assert service.last_input_audits == (
        EmbeddingInputAudit(
            original_tokens=3,
            retained_tokens=3,
            strategy="none",
            was_truncated=False,
            dropped_tail_tokens=0,
            chunk_count=1,
        ),
    )


@pytest.mark.asyncio
async def test_embed_texts_with_contexts_tracks_under_and_exact_limit_paths(
    mock_db_session,
) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        max_input_tokens=10,
        token_estimate_chars_per_token=1,
    )

    _vectors, audits, _cache_hits, _api_calls = await service.embed_texts_with_contexts(
        ["under", "1234567890"],
        entity_type="raw_item",
        entity_ids=[uuid4(), uuid4()],
    )

    assert [audit.strategy for audit in audits] == ["none", "none"]
    assert [audit.original_tokens for audit in audits] == [5, 10]
    assert [audit.retained_tokens for audit in audits] == [5, 10]
    assert all(audit.was_truncated is False for audit in audits)


@pytest.mark.asyncio
async def test_embed_texts_with_contexts_rejects_mismatched_entity_ids(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)

    with pytest.raises(ValueError, match="entity_ids must match texts length"):
        await service.embed_texts_with_contexts(
            ["one", "two"],
            entity_type="event",
            entity_ids=[uuid4()],
        )


@pytest.mark.asyncio
async def test_embed_texts_with_contexts_truncates_over_limit_input(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        max_input_tokens=30,
        token_estimate_chars_per_token=1,
        input_policy="truncate",
    )

    _vectors, audits, _cache_hits, _api_calls = await service.embed_texts_with_contexts(
        ["x" * 40],
        entity_type="raw_item",
        entity_ids=[uuid4()],
    )

    assert audits[0].strategy == "truncate"
    assert audits[0].was_truncated is True
    assert audits[0].original_tokens == 40
    assert audits[0].retained_tokens == 30
    assert audits[0].dropped_tail_tokens == 10
    assert audits[0].chunk_count == 1


@pytest.mark.asyncio
async def test_embed_texts_with_contexts_chunks_over_limit_input(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        max_input_tokens=10,
        token_estimate_chars_per_token=1,
        input_policy="chunk",
    )

    _vectors, audits, _cache_hits, _api_calls = await service.embed_texts_with_contexts(
        ["aaaaa bbbbb ccccc ddddd"],
        entity_type="event",
        entity_ids=[uuid4()],
    )

    assert audits[0].strategy == "chunk"
    assert audits[0].was_truncated is False
    assert audits[0].original_tokens == audits[0].retained_tokens
    assert audits[0].chunk_count > 1
    assert audits[0].dropped_tail_tokens == 0


@pytest.mark.asyncio
async def test_embed_texts_with_contexts_logs_cut_inputs_with_entity_id(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        max_input_tokens=10,
        token_estimate_chars_per_token=1,
        input_policy="truncate",
    )
    captured_logs: list[dict[str, object]] = []

    def _capture_warning(_message: str, **kwargs: object) -> None:
        captured_logs.append(kwargs)

    monkeypatch.setattr(embedding_service_module.logger, "warning", _capture_warning)

    entity_id = uuid4()
    await service.embed_texts_with_contexts(
        ["y" * 40],
        entity_type="raw_item",
        entity_ids=[entity_id],
    )

    assert len(captured_logs) == 1
    assert captured_logs[0]["entity_type"] == "raw_item"
    assert captured_logs[0]["entity_id"] == str(entity_id)
    assert captured_logs[0]["strategy"] == "truncate"


@pytest.mark.asyncio
async def test_embed_texts_with_contexts_handles_empty_input_list(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)

    assert await service.embed_texts_with_contexts([], entity_type="generic", entity_ids=None) == (
        [],
        [],
        0,
        0,
    )


@pytest.mark.asyncio
async def test_embed_texts_with_contexts_raises_when_results_or_audits_missing(
    mock_db_session,
) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)
    service._cache_get = lambda _key: None  # type: ignore[method-assign]
    service._request_embeddings = AsyncMock(return_value=[])

    with pytest.raises(ValueError, match="zip\\(\\) argument 2 is shorter"):
        await service.embed_texts_with_contexts(["alpha"], entity_type="generic", entity_ids=None)

    service._request_embeddings = AsyncMock(return_value=[[1.0, 2.0, 3.0]])
    original_prepare = service._prepare_input

    def prepare_without_audit(text: str):
        prepared = original_prepare(text)
        return embedding_service_module._PreparedEmbeddingInput(
            text_chunks=prepared.text_chunks, audit=None
        )  # type: ignore[arg-type]

    service._prepare_input = prepare_without_audit  # type: ignore[method-assign]
    service._record_input_audit = lambda **_: None  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="audits missing"):
        await service.embed_texts_with_contexts(["alpha"], entity_type="generic", entity_ids=None)

    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)
    original_prepare = service._prepare_input

    def prepare_without_chunks(text: str):
        prepared = original_prepare(text)
        return embedding_service_module._PreparedEmbeddingInput(
            text_chunks=[],
            audit=prepared.audit,
        )

    service._prepare_input = prepare_without_chunks  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="failed to produce vectors"):
        await service.embed_texts_with_contexts(["alpha"], entity_type="generic", entity_ids=None)


@pytest.mark.asyncio
async def test_request_embeddings_rejects_dimension_mismatch(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        dimensions=3,
    )

    class WrongEmbeddingsAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[1.0, 2.0])])

    service.client = SimpleNamespace(embeddings=WrongEmbeddingsAPI())

    with pytest.raises(ValueError, match="dimension mismatch"):
        await service.embed_text("one")


@pytest.mark.asyncio
async def test_request_embeddings_validates_response_shapes_and_values(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session, dimensions=3
    )

    class MissingDataAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(data=None)

    service.client = SimpleNamespace(embeddings=MissingDataAPI())
    with pytest.raises(ValueError, match="missing data list"):
        await service._request_embeddings(["one"])

    class WrongCountAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(data=[])

    service.client = SimpleNamespace(embeddings=WrongCountAPI())
    with pytest.raises(ValueError, match="size does not match"):
        await service._request_embeddings(["one"])

    class BadIndexAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(data=[SimpleNamespace(index="bad", embedding=[1.0, 2.0, 3.0])])

    service.client = SimpleNamespace(embeddings=BadIndexAPI())
    with pytest.raises(ValueError, match="index is not an integer"):
        await service._request_embeddings(["one"])

    class BadEmbeddingAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding="bad")])

    service.client = SimpleNamespace(embeddings=BadEmbeddingAPI())
    with pytest.raises(ValueError, match="embedding is not a list"):
        await service._request_embeddings(["one"])

    class NonNumericAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[1.0, "bad", 3.0])])

    service.client = SimpleNamespace(embeddings=NonNumericAPI())
    with pytest.raises(ValueError, match="non-numeric"):
        await service._request_embeddings(["one"])

    class NonFiniteAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(
                data=[SimpleNamespace(index=0, embedding=[1.0, float("inf"), 3.0])]
            )

    service.client = SimpleNamespace(embeddings=NonFiniteAPI())
    with pytest.raises(ValueError, match="non-finite"):
        await service._request_embeddings(["one"])

    class InvalidIndexOrderAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=2, embedding=[1.0, 2.0, 3.0]),
                    SimpleNamespace(index=0, embedding=[4.0, 5.0, 6.0]),
                ]
            )

    service.client = SimpleNamespace(embeddings=InvalidIndexOrderAPI())
    with pytest.raises(ValueError, match="indices are invalid"):
        await service._request_embeddings(["one", "two"])


@pytest.mark.asyncio
async def test_request_embeddings_uses_total_tokens_when_prompt_tokens_missing(
    mock_db_session,
) -> None:
    service, _embeddings_api, cost_tracker = _build_service(
        mock_db_session=mock_db_session, dimensions=3
    )

    class TotalTokensAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(
                data=[SimpleNamespace(index=0, embedding=[1.0, 2.0, 3.0])],
                usage=SimpleNamespace(prompt_tokens=0, total_tokens=12),
            )

    service.client = SimpleNamespace(embeddings=TotalTokensAPI())
    vectors = await service._request_embeddings(["one"])

    assert vectors == [[1.0, 2.0, 3.0]]
    cost_tracker.record_usage.assert_awaited_once()
    assert cost_tracker.record_usage.await_args.kwargs["input_tokens"] == 12


@pytest.mark.asyncio
async def test_request_embeddings_prefers_prompt_tokens_and_handles_empty_inputs(
    mock_db_session,
) -> None:
    service, _embeddings_api, cost_tracker = _build_service(
        mock_db_session=mock_db_session, dimensions=3
    )

    assert await service._request_embeddings([]) == []

    class PromptTokensAPI:
        async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
            _ = model, input
            return SimpleNamespace(
                data=[SimpleNamespace(index=0, embedding=[1.0, 2.0, 3.0])],
                usage=SimpleNamespace(prompt_tokens=7, total_tokens=12),
            )

    service.client = SimpleNamespace(embeddings=PromptTokensAPI())
    vectors = await service._request_embeddings(["one"])

    assert vectors == [[1.0, 2.0, 3.0]]
    cost_tracker.record_usage.assert_awaited_once()
    assert cost_tracker.record_usage.await_args.kwargs["input_tokens"] == 7


@pytest.mark.asyncio
async def test_embed_raw_items_without_embedding_persists_vectors(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)
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

    async def fake_embed_texts_with_contexts(
        _texts: list[str],
        *,
        entity_type: str,
        entity_ids: list[str | object | None] | None,
    ) -> tuple[list[list[float]], list[EmbeddingInputAudit], int, int]:
        assert entity_type == "raw_item"
        assert entity_ids == [first_item.id, second_item.id]
        return (
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            [
                EmbeddingInputAudit(
                    original_tokens=120,
                    retained_tokens=100,
                    strategy="truncate",
                    was_truncated=True,
                    dropped_tail_tokens=20,
                    chunk_count=1,
                ),
                EmbeddingInputAudit(
                    original_tokens=80,
                    retained_tokens=80,
                    strategy="none",
                    was_truncated=False,
                    dropped_tail_tokens=0,
                    chunk_count=1,
                ),
            ],
            1,
            1,
        )

    service.embed_texts_with_contexts = fake_embed_texts_with_contexts

    result = await service.embed_raw_items_without_embedding(limit=10)

    assert first_item.embedding == [1.0, 2.0, 3.0]
    assert second_item.embedding == [4.0, 5.0, 6.0]
    assert first_item.embedding_model == "test-embedding-model"
    assert second_item.embedding_model == "test-embedding-model"
    assert first_item.embedding_generated_at is not None
    assert second_item.embedding_generated_at is not None
    assert first_item.embedding_input_tokens == 120
    assert first_item.embedding_retained_tokens == 100
    assert first_item.embedding_was_truncated is True
    assert first_item.embedding_truncation_strategy == "truncate"
    assert second_item.embedding_input_tokens == 80
    assert second_item.embedding_retained_tokens == 80
    assert second_item.embedding_was_truncated is False
    assert second_item.embedding_truncation_strategy is None
    assert result.entity_type == "raw_items"
    assert result.scanned == 2
    assert result.embedded == 2
    assert result.cache_hits == 1
    assert result.api_calls == 1
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_embed_raw_items_without_embedding_returns_empty_summary(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    result = await service.embed_raw_items_without_embedding(limit=10)

    assert result.entity_type == "raw_items"
    assert result.embedded == 0


@pytest.mark.asyncio
async def test_embed_events_without_embedding_persists_vectors(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)
    first_event = Event(canonical_summary="first summary")
    second_event = Event(canonical_summary="second summary")
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [first_event, second_event])

    async def fake_embed_texts_with_contexts(
        _texts: list[str],
        *,
        entity_type: str,
        entity_ids: list[str | object | None] | None,
    ) -> tuple[list[list[float]], list[EmbeddingInputAudit], int, int]:
        assert entity_type == "event"
        assert entity_ids == [first_event.id, second_event.id]
        return (
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            [
                EmbeddingInputAudit(
                    original_tokens=60,
                    retained_tokens=60,
                    strategy="none",
                    was_truncated=False,
                    dropped_tail_tokens=0,
                    chunk_count=1,
                ),
                EmbeddingInputAudit(
                    original_tokens=140,
                    retained_tokens=140,
                    strategy="chunk",
                    was_truncated=False,
                    dropped_tail_tokens=0,
                    chunk_count=2,
                ),
            ],
            0,
            1,
        )

    service.embed_texts_with_contexts = fake_embed_texts_with_contexts

    result = await service.embed_events_without_embedding(limit=10)

    assert first_event.embedding == [0.1, 0.2, 0.3]
    assert second_event.embedding == [0.4, 0.5, 0.6]
    assert first_event.embedding_model == "test-embedding-model"
    assert second_event.embedding_model == "test-embedding-model"
    assert first_event.embedding_generated_at is not None
    assert second_event.embedding_generated_at is not None
    assert first_event.embedding_input_tokens == 60
    assert first_event.embedding_retained_tokens == 60
    assert first_event.embedding_was_truncated is False
    assert first_event.embedding_truncation_strategy is None
    assert second_event.embedding_input_tokens == 140
    assert second_event.embedding_retained_tokens == 140
    assert second_event.embedding_was_truncated is False
    assert second_event.embedding_truncation_strategy == "chunk"
    assert result.entity_type == "events"
    assert result.scanned == 2
    assert result.embedded == 2
    assert result.cache_hits == 0
    assert result.api_calls == 1
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_embed_events_without_embedding_returns_empty_summary(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(mock_db_session=mock_db_session)
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    result = await service.embed_events_without_embedding(limit=10)

    assert result.entity_type == "events"
    assert result.embedded == 0


def test_cache_helpers_chunking_and_average_vector_behaviors(mock_db_session) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        dimensions=3,
        cache_max_size=2,
        max_input_tokens=4,
        token_estimate_chars_per_token=1,
        input_policy="chunk",
    )

    key = service._cache_key("alpha")
    assert service._cache_get(key) is None
    service._cache_set("a", [1.0, 2.0, 3.0])
    service._cache_set("b", [4.0, 5.0, 6.0])
    service._cache_set("c", [7.0, 8.0, 9.0])
    assert "a" not in service._cache
    assert service._cache_get("b") == [4.0, 5.0, 6.0]

    assert service._chunk_text("tiny") == ["tiny"]
    assert service._chunk_text("aaaaa bbbbb ccccc") == ["aaaa", "a", "bbbb", "b", "cccc", "c"]
    assert service._chunk_text("one two three four five") == [
        "one",
        "two",
        "thre",
        "e",
        "four",
        "five",
    ]

    with pytest.raises(ValueError, match="at least one chunk vector"):
        service._average_vectors([])
    with pytest.raises(ValueError, match="dimension mismatch"):
        service._average_vectors([[1.0, 2.0]])
    assert service._average_vectors([[1.0, 2.0, 3.0], [3.0, 4.0, 5.0]]) == [2.0, 3.0, 4.0]


def test_prepare_input_record_audit_and_normalize_helpers(
    mock_db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _embeddings_api, _cost_tracker = _build_service(
        mock_db_session=mock_db_session,
        max_input_tokens=4,
        token_estimate_chars_per_token=1,
    )
    captured_metrics: list[dict[str, object]] = []
    warning_logger = MagicMock()
    monkeypatch.setattr(
        embedding_service_module,
        "record_embedding_input_guardrail",
        lambda **kwargs: captured_metrics.append(kwargs),
    )
    monkeypatch.setattr(embedding_service_module.logger, "warning", warning_logger)

    prepared = service._prepare_input("abcdef")
    assert prepared.audit.strategy == "truncate"
    assert prepared.audit.was_cut is True

    no_cut_audit = EmbeddingInputAudit(
        original_tokens=2,
        retained_tokens=2,
        strategy="none",
        was_truncated=False,
        dropped_tail_tokens=0,
        chunk_count=1,
    )
    service._record_input_audit(entity_type="event", entity_id=None, audit=no_cut_audit)
    warning_logger.assert_not_called()
    assert captured_metrics[-1]["was_cut"] is False

    cut_audit = EmbeddingInputAudit(
        original_tokens=6,
        retained_tokens=4,
        strategy="truncate",
        was_truncated=True,
        dropped_tail_tokens=2,
        chunk_count=1,
    )
    service._record_input_audit(entity_type="event", entity_id="123", audit=cut_audit)
    warning_logger.assert_called_once()
    assert EmbeddingService._normalize_text("  alpha   beta  ") == "alpha beta"
    with pytest.raises(ValueError, match="must not be empty"):
        EmbeddingService._normalize_text("   ")
