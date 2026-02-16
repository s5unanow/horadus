"""
Embedding lineage report utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import Event, RawItem


@dataclass(frozen=True, slots=True)
class EmbeddingModelCount:
    model: str
    count: int


@dataclass(frozen=True, slots=True)
class EmbeddingLineageSummary:
    entity: str
    vectors: int
    rows_without_vector: int
    target_model: str
    target_model_vectors: int
    vectors_missing_model: int
    vectors_other_models: int
    reembed_scope: int
    model_counts: tuple[EmbeddingModelCount, ...]

    @property
    def has_mixed_models(self) -> bool:
        return len(self.model_counts) > 1


@dataclass(frozen=True, slots=True)
class EmbeddingLineageReport:
    target_model: str
    raw_items: EmbeddingLineageSummary
    events: EmbeddingLineageSummary

    @property
    def total_vectors(self) -> int:
        return self.raw_items.vectors + self.events.vectors

    @property
    def total_reembed_scope(self) -> int:
        return self.raw_items.reembed_scope + self.events.reembed_scope

    @property
    def has_mixed_populations(self) -> bool:
        return self.raw_items.has_mixed_models or self.events.has_mixed_models


async def _count_rows(
    session: AsyncSession,
    *,
    entity_cls: Any,
    predicates: tuple[Any, ...] = (),
) -> int:
    query = select(func.count()).select_from(entity_cls)
    for predicate in predicates:
        query = query.where(predicate)
    count = await session.scalar(query)
    return int(count or 0)


async def _build_summary(
    session: AsyncSession,
    *,
    entity_cls: Any,
    entity: str,
    target_model: str,
) -> EmbeddingLineageSummary:
    vectors = await _count_rows(
        session,
        entity_cls=entity_cls,
        predicates=(entity_cls.embedding.is_not(None),),
    )
    rows_without_vector = await _count_rows(
        session,
        entity_cls=entity_cls,
        predicates=(entity_cls.embedding.is_(None),),
    )
    target_model_vectors = await _count_rows(
        session,
        entity_cls=entity_cls,
        predicates=(
            entity_cls.embedding.is_not(None),
            entity_cls.embedding_model == target_model,
        ),
    )
    vectors_missing_model = await _count_rows(
        session,
        entity_cls=entity_cls,
        predicates=(
            entity_cls.embedding.is_not(None),
            entity_cls.embedding_model.is_(None),
        ),
    )

    vectors_other_models = max(vectors - target_model_vectors - vectors_missing_model, 0)
    reembed_scope = max(vectors - target_model_vectors, 0)

    model_rows = (
        await session.execute(
            select(entity_cls.embedding_model, func.count().label("count"))
            .where(entity_cls.embedding.is_not(None))
            .where(entity_cls.embedding_model.is_not(None))
            .group_by(entity_cls.embedding_model)
            .order_by(func.count().desc(), entity_cls.embedding_model.asc())
        )
    ).all()
    model_counts = tuple(
        EmbeddingModelCount(model=str(row[0]), count=int(row[1])) for row in model_rows
    )

    return EmbeddingLineageSummary(
        entity=entity,
        vectors=vectors,
        rows_without_vector=rows_without_vector,
        target_model=target_model,
        target_model_vectors=target_model_vectors,
        vectors_missing_model=vectors_missing_model,
        vectors_other_models=vectors_other_models,
        reembed_scope=reembed_scope,
        model_counts=model_counts,
    )


async def build_embedding_lineage_report(
    session: AsyncSession,
    *,
    target_model: str,
) -> EmbeddingLineageReport:
    normalized_target = target_model.strip()
    if not normalized_target:
        msg = "target_model must not be empty"
        raise ValueError(msg)

    raw_items = await _build_summary(
        session,
        entity_cls=RawItem,
        entity="raw_items",
        target_model=normalized_target,
    )
    events = await _build_summary(
        session,
        entity_cls=Event,
        entity="events",
        target_model=normalized_target,
    )
    return EmbeddingLineageReport(
        target_model=normalized_target,
        raw_items=raw_items,
        events=events,
    )
