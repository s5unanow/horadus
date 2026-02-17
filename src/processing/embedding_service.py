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
from src.processing.cost_tracker import EMBEDDING, CostTracker
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
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.session = session
        self.model = model or settings.EMBEDDING_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.cache_max_size = cache_max_size or settings.EMBEDDING_CACHE_MAX_SIZE

        self.client = client or self._create_client()
        self.cost_tracker = cost_tracker or CostTracker(session=session)
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

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
        if not texts:
            return ([], 0, 0)

        normalized_texts = [self._normalize_text(text) for text in texts]
        cache_hits = 0
        api_calls = 0

        results: list[list[float] | None] = [None] * len(normalized_texts)
        misses_by_key: dict[str, list[int]] = {}
        miss_text_by_key: dict[str, str] = {}

        for index, normalized_text in enumerate(normalized_texts):
            cache_key = self._cache_key(normalized_text)
            cached_vector = self._cache_get(cache_key)
            if cached_vector is not None:
                results[index] = cached_vector
                cache_hits += 1
                continue

            misses_by_key.setdefault(cache_key, []).append(index)
            miss_text_by_key.setdefault(cache_key, normalized_text)

        miss_keys = list(misses_by_key.keys())
        for chunk_start in range(0, len(miss_keys), self.batch_size):
            chunk_keys = miss_keys[chunk_start : chunk_start + self.batch_size]
            chunk_texts = [miss_text_by_key[key] for key in chunk_keys]
            vectors = await self._request_embeddings(chunk_texts)
            api_calls += 1

            for key, vector in zip(chunk_keys, vectors, strict=True):
                self._cache_set(key, vector)
                for result_index in misses_by_key[key]:
                    results[result_index] = vector

        finalized = [vector for vector in results if vector is not None]
        if len(finalized) != len(texts):
            msg = "Embedding generation failed to produce vectors for all inputs"
            raise RuntimeError(msg)

        return (finalized, cache_hits, api_calls)

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
        vectors, cache_hits, api_calls = await self.embed_texts(item_texts)
        generated_at = datetime.now(tz=UTC)

        for item, vector in zip(items, vectors, strict=True):
            item.embedding = vector
            item.embedding_model = self.model
            item.embedding_generated_at = generated_at

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
        vectors, cache_hits, api_calls = await self.embed_texts(event_texts)
        generated_at = datetime.now(tz=UTC)

        for event, vector in zip(events, vectors, strict=True):
            event.embedding = vector
            event.embedding_model = self.model
            event.embedding_generated_at = generated_at

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

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = " ".join(text.split())
        if not normalized:
            msg = "Embedding input text must not be empty"
            raise ValueError(msg)
        return normalized
