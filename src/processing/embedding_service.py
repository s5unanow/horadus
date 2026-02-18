"""
Embedding service with batching, caching, and pgvector persistence.
"""

from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import record_embedding_input_guardrail
from src.processing.cost_tracker import EMBEDDING, CostTracker
from src.processing.llm_input_safety import estimate_tokens, truncate_to_token_limit
from src.storage.models import Event, RawItem

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class EmbeddingRunResult:
    """Summary metrics for one persistence run."""

    entity_type: str
    scanned: int = 0
    embedded: int = 0
    cache_hits: int = 0
    api_calls: int = 0


@dataclass(frozen=True, slots=True)
class EmbeddingInputAudit:
    """Per-input guardrail audit details for embedding preprocessing."""

    original_tokens: int
    retained_tokens: int
    strategy: str
    was_truncated: bool
    dropped_tail_tokens: int
    chunk_count: int

    @property
    def was_cut(self) -> bool:
        """Whether the input exceeded token budget and required handling."""
        return self.strategy in {"truncate", "chunk"}


@dataclass(frozen=True, slots=True)
class _PreparedEmbeddingInput:
    text_chunks: list[str]
    audit: EmbeddingInputAudit


class EmbeddingService:
    """
    Generate embeddings and persist them into pgvector columns.
    """

    def __init__(
        self,
        session: AsyncSession,
        client: AsyncOpenAI | Any | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
        cache_max_size: int | None = None,
        max_input_tokens: int | None = None,
        input_policy: str | None = None,
        token_estimate_chars_per_token: int | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.session = session
        self.model = model or settings.EMBEDDING_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.cache_max_size = cache_max_size or settings.EMBEDDING_CACHE_MAX_SIZE
        self.max_input_tokens = max_input_tokens or settings.EMBEDDING_MAX_INPUT_TOKENS
        self.input_policy = (input_policy or settings.EMBEDDING_INPUT_POLICY).strip().lower()
        self.token_estimate_chars_per_token = (
            token_estimate_chars_per_token or settings.EMBEDDING_TOKEN_ESTIMATE_CHARS_PER_TOKEN
        )

        self.client = client or self._create_client()
        self.cost_tracker = cost_tracker or CostTracker(session=session)
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._last_input_audits: list[EmbeddingInputAudit] = []

    def _create_client(self) -> AsyncOpenAI:
        if not settings.OPENAI_API_KEY.strip():
            msg = "OPENAI_API_KEY is required for EmbeddingService"
            raise ValueError(msg)
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def embed_text(self, text: str) -> list[float]:
        """Generate a single embedding."""
        embeddings, _hits, _calls = await self.embed_texts([text])
        return embeddings[0]

    async def embed_texts(self, texts: list[str]) -> tuple[list[list[float]], int, int]:
        """
        Generate embeddings for multiple texts with cache reuse.

        Returns:
            Tuple of (embeddings, cache_hits, api_calls)
        """
        embeddings, audits, cache_hits, api_calls = await self.embed_texts_with_contexts(
            texts,
            entity_type="generic",
            entity_ids=None,
        )
        self._last_input_audits = audits
        return (embeddings, cache_hits, api_calls)

    @property
    def last_input_audits(self) -> tuple[EmbeddingInputAudit, ...]:
        """Return guardrail audits from the most recent embed_texts call."""
        return tuple(self._last_input_audits)

    async def embed_texts_with_contexts(
        self,
        texts: list[str],
        *,
        entity_type: str,
        entity_ids: list[str | Any | None] | None,
    ) -> tuple[list[list[float]], list[EmbeddingInputAudit], int, int]:
        """Embed texts while attaching entity context for audit logs/metrics."""
        if not texts:
            return ([], [], 0, 0)
        if entity_ids is not None and len(entity_ids) != len(texts):
            msg = "entity_ids must match texts length"
            raise ValueError(msg)

        normalized_texts = [self._normalize_text(text) for text in texts]
        cache_hits = 0
        api_calls = 0

        results: list[list[float] | None] = [None] * len(normalized_texts)
        audits: list[EmbeddingInputAudit | None] = [None] * len(normalized_texts)
        misses_by_key: dict[str, list[int]] = {}
        prepared_by_key: dict[str, _PreparedEmbeddingInput] = {}

        for index, normalized_text in enumerate(normalized_texts):
            cache_key = self._cache_key(normalized_text)
            prepared = prepared_by_key.get(cache_key)
            if prepared is None:
                prepared = self._prepare_input(normalized_text)
                prepared_by_key[cache_key] = prepared

            audit = prepared.audit
            audits[index] = audit
            entity_id = (
                str(entity_ids[index])
                if entity_ids is not None and entity_ids[index] is not None
                else None
            )
            self._record_input_audit(
                entity_type=entity_type,
                entity_id=entity_id,
                audit=audit,
            )

            cached_vector = self._cache_get(cache_key)
            if cached_vector is not None:
                results[index] = cached_vector
                cache_hits += 1
                continue

            misses_by_key.setdefault(cache_key, []).append(index)

        miss_keys = list(misses_by_key.keys())
        single_chunk_keys = [key for key in miss_keys if len(prepared_by_key[key].text_chunks) == 1]
        multi_chunk_keys = [key for key in miss_keys if len(prepared_by_key[key].text_chunks) > 1]

        for chunk_start in range(0, len(single_chunk_keys), self.batch_size):
            chunk_keys = single_chunk_keys[chunk_start : chunk_start + self.batch_size]
            chunk_texts = [prepared_by_key[key].text_chunks[0] for key in chunk_keys]
            vectors = await self._request_embeddings(chunk_texts)
            api_calls += 1

            for key, vector in zip(chunk_keys, vectors, strict=True):
                self._cache_set(key, vector)
                for result_index in misses_by_key[key]:
                    results[result_index] = vector

        for key in multi_chunk_keys:
            prepared = prepared_by_key[key]
            chunk_vectors: list[list[float]] = []
            for chunk_start in range(0, len(prepared.text_chunks), self.batch_size):
                chunk_inputs = prepared.text_chunks[chunk_start : chunk_start + self.batch_size]
                chunk_vectors.extend(await self._request_embeddings(chunk_inputs))
                api_calls += 1

            merged_vector = self._average_vectors(chunk_vectors)
            self._cache_set(key, merged_vector)
            for result_index in misses_by_key[key]:
                results[result_index] = merged_vector

        finalized = [vector for vector in results if vector is not None]
        finalized_audits = [audit for audit in audits if audit is not None]
        if len(finalized) != len(texts):
            msg = "Embedding generation failed to produce vectors for all inputs"
            raise RuntimeError(msg)
        if len(finalized_audits) != len(texts):
            msg = "Embedding preprocessing audits missing for one or more inputs"
            raise RuntimeError(msg)

        self._last_input_audits = finalized_audits
        return (finalized, finalized_audits, cache_hits, api_calls)

    async def embed_raw_items_without_embedding(self, limit: int = 100) -> EmbeddingRunResult:
        """Generate and persist embeddings for raw items missing vectors."""
        query = (
            select(RawItem)
            .where(RawItem.embedding.is_(None))
            .where(RawItem.raw_content.is_not(None))
            .order_by(RawItem.fetched_at.asc())
            .limit(limit)
        )
        items = (await self.session.scalars(query)).all()
        if not items:
            return EmbeddingRunResult(entity_type="raw_items")

        item_texts = [item.raw_content for item in items]
        vectors, audits, cache_hits, api_calls = await self.embed_texts_with_contexts(
            item_texts,
            entity_type="raw_item",
            entity_ids=[item.id for item in items],
        )
        generated_at = datetime.now(tz=UTC)

        for item, vector, audit in zip(items, vectors, audits, strict=True):
            item.embedding = vector
            item.embedding_model = self.model
            item.embedding_generated_at = generated_at
            item.embedding_input_tokens = audit.original_tokens
            item.embedding_retained_tokens = audit.retained_tokens
            item.embedding_was_truncated = audit.was_truncated
            item.embedding_truncation_strategy = audit.strategy if audit.was_cut else None

        await self.session.flush()
        logger.info(
            "Embedded raw items",
            count=len(items),
            cache_hits=cache_hits,
            api_calls=api_calls,
        )
        return EmbeddingRunResult(
            entity_type="raw_items",
            scanned=len(items),
            embedded=len(items),
            cache_hits=cache_hits,
            api_calls=api_calls,
        )

    async def embed_events_without_embedding(self, limit: int = 100) -> EmbeddingRunResult:
        """Generate and persist embeddings for events missing vectors."""
        query = (
            select(Event)
            .where(Event.embedding.is_(None))
            .where(Event.canonical_summary.is_not(None))
            .order_by(Event.first_seen_at.asc())
            .limit(limit)
        )
        events = (await self.session.scalars(query)).all()
        if not events:
            return EmbeddingRunResult(entity_type="events")

        event_texts = [event.canonical_summary for event in events]
        vectors, audits, cache_hits, api_calls = await self.embed_texts_with_contexts(
            event_texts,
            entity_type="event",
            entity_ids=[event.id for event in events],
        )
        generated_at = datetime.now(tz=UTC)

        for event, vector, audit in zip(events, vectors, audits, strict=True):
            event.embedding = vector
            event.embedding_model = self.model
            event.embedding_generated_at = generated_at
            event.embedding_input_tokens = audit.original_tokens
            event.embedding_retained_tokens = audit.retained_tokens
            event.embedding_was_truncated = audit.was_truncated
            event.embedding_truncation_strategy = audit.strategy if audit.was_cut else None

        await self.session.flush()
        logger.info(
            "Embedded events",
            count=len(events),
            cache_hits=cache_hits,
            api_calls=api_calls,
        )
        return EmbeddingRunResult(
            entity_type="events",
            scanned=len(events),
            embedded=len(events),
            cache_hits=cache_hits,
            api_calls=api_calls,
        )

    async def _request_embeddings(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []

        await self.cost_tracker.ensure_within_budget(EMBEDDING)
        response = await self.client.embeddings.create(
            model=self.model,
            input=inputs,
        )
        usage_obj = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
        if prompt_tokens == 0:
            prompt_tokens = int(getattr(usage_obj, "total_tokens", 0) or 0)
        await self.cost_tracker.record_usage(
            tier=EMBEDDING,
            input_tokens=prompt_tokens,
            output_tokens=0,
        )

        raw_data = getattr(response, "data", None)
        if not isinstance(raw_data, list):
            msg = "Embedding response missing data list"
            raise ValueError(msg)
        if len(raw_data) != len(inputs):
            msg = "Embedding response size does not match input size"
            raise ValueError(msg)

        indexed_vectors: list[tuple[int, list[float]]] = []
        for fallback_index, item in enumerate(raw_data):
            raw_index = getattr(item, "index", fallback_index)
            if not isinstance(raw_index, int):
                msg = "Embedding response index is not an integer"
                raise ValueError(msg)

            raw_embedding = getattr(item, "embedding", None)
            if not isinstance(raw_embedding, list):
                msg = "Embedding response embedding is not a list"
                raise ValueError(msg)
            if len(raw_embedding) != self.dimensions:
                msg = f"Embedding dimension mismatch: expected {self.dimensions}"
                raise ValueError(msg)

            vector: list[float] = []
            for value in raw_embedding:
                if not isinstance(value, int | float):
                    msg = "Embedding vector contains non-numeric value"
                    raise ValueError(msg)
                float_value = float(value)
                if not math.isfinite(float_value):
                    msg = "Embedding vector contains non-finite value"
                    raise ValueError(msg)
                vector.append(float_value)

            indexed_vectors.append((raw_index, vector))

        indexed_vectors.sort(key=lambda pair: pair[0])
        expected_indices = list(range(len(inputs)))
        actual_indices = [index for index, _ in indexed_vectors]
        if actual_indices != expected_indices:
            msg = "Embedding response indices are invalid"
            raise ValueError(msg)

        return [vector for _index, vector in indexed_vectors]

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_get(self, cache_key: str) -> list[float] | None:
        cached = self._cache.get(cache_key)
        if cached is None:
            return None
        self._cache.move_to_end(cache_key)
        return cached

    def _cache_set(self, cache_key: str, vector: list[float]) -> None:
        self._cache[cache_key] = vector
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self.cache_max_size:
            self._cache.popitem(last=False)

    def _prepare_input(self, normalized_text: str) -> _PreparedEmbeddingInput:
        original_tokens = estimate_tokens(
            text=normalized_text,
            chars_per_token=self.token_estimate_chars_per_token,
        )
        if original_tokens <= self.max_input_tokens:
            audit = EmbeddingInputAudit(
                original_tokens=original_tokens,
                retained_tokens=original_tokens,
                strategy="none",
                was_truncated=False,
                dropped_tail_tokens=0,
                chunk_count=1,
            )
            return _PreparedEmbeddingInput(text_chunks=[normalized_text], audit=audit)

        if self.input_policy == "chunk":
            chunks = self._chunk_text(normalized_text)
            audit = EmbeddingInputAudit(
                original_tokens=original_tokens,
                retained_tokens=original_tokens,
                strategy="chunk",
                was_truncated=False,
                dropped_tail_tokens=0,
                chunk_count=len(chunks),
            )
            return _PreparedEmbeddingInput(text_chunks=chunks, audit=audit)

        truncated = truncate_to_token_limit(
            text=normalized_text,
            max_tokens=self.max_input_tokens,
            chars_per_token=self.token_estimate_chars_per_token,
        )
        retained_tokens = min(
            self.max_input_tokens,
            estimate_tokens(
                text=truncated,
                chars_per_token=self.token_estimate_chars_per_token,
            ),
        )
        dropped_tail_tokens = max(0, original_tokens - retained_tokens)
        audit = EmbeddingInputAudit(
            original_tokens=original_tokens,
            retained_tokens=retained_tokens,
            strategy="truncate",
            was_truncated=True,
            dropped_tail_tokens=dropped_tail_tokens,
            chunk_count=1,
        )
        return _PreparedEmbeddingInput(text_chunks=[truncated], audit=audit)

    def _chunk_text(self, normalized_text: str) -> list[str]:
        max_chars = self.max_input_tokens * self.token_estimate_chars_per_token
        if len(normalized_text) <= max_chars:
            return [normalized_text]

        chunks: list[str] = []
        current_words: list[str] = []
        current_len = 0

        def flush_current() -> None:
            nonlocal current_words, current_len
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = []
                current_len = 0

        for word in normalized_text.split():
            if len(word) > max_chars:
                flush_current()
                for start in range(0, len(word), max_chars):
                    chunks.append(word[start : start + max_chars])
                continue

            next_len = current_len + len(word) + (1 if current_words else 0)
            if current_words and next_len > max_chars:
                flush_current()

            current_words.append(word)
            current_len += len(word) + (1 if len(current_words) > 1 else 0)

        flush_current()
        return chunks or [normalized_text[:max_chars]]

    def _record_input_audit(
        self,
        *,
        entity_type: str,
        entity_id: str | None,
        audit: EmbeddingInputAudit,
    ) -> None:
        record_embedding_input_guardrail(
            entity_type=entity_type,
            strategy=audit.strategy,
            was_cut=audit.was_cut,
            dropped_tail_tokens=audit.dropped_tail_tokens,
        )
        if not audit.was_cut:
            return
        logger.warning(
            "Embedding input exceeded token budget",
            entity_type=entity_type,
            entity_id=entity_id,
            original_token_count=audit.original_tokens,
            retained_token_count=audit.retained_tokens,
            dropped_tail_tokens=audit.dropped_tail_tokens,
            strategy=audit.strategy,
            chunk_count=audit.chunk_count,
            max_input_tokens=self.max_input_tokens,
        )

    def _average_vectors(self, vectors: list[list[float]]) -> list[float]:
        if not vectors:
            msg = "Expected at least one chunk vector for aggregation"
            raise ValueError(msg)

        accumulator = [0.0] * self.dimensions
        for vector in vectors:
            if len(vector) != self.dimensions:
                msg = "Chunk vector dimension mismatch during aggregation"
                raise ValueError(msg)
            for index, value in enumerate(vector):
                accumulator[index] += value

        vector_count = float(len(vectors))
        return [value / vector_count for value in accumulator]

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = " ".join(text.split())
        if not normalized:
            msg = "Embedding input text must not be empty"
            raise ValueError(msg)
        return normalized
