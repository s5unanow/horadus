"""Helpers for bounded cluster-health metadata stored on event provenance."""

from __future__ import annotations

from itertools import combinations
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.processing.vector_similarity import cosine_similarity
from src.storage.models import EventItem, RawItem

CLUSTER_HEALTH_KEY = "cluster_health"
DEFAULT_CLUSTER_COHESION_SCORE = 1.0
DEFAULT_SPLIT_RISK_SCORE = 0.0


def cluster_health_payload(event: Any) -> dict[str, float]:
    """Return normalized cluster-health values from provenance metadata."""

    provenance_summary = getattr(event, "provenance_summary", None)
    if not isinstance(provenance_summary, dict):
        return {
            "cluster_cohesion_score": DEFAULT_CLUSTER_COHESION_SCORE,
            "split_risk_score": DEFAULT_SPLIT_RISK_SCORE,
        }
    payload = provenance_summary.get(CLUSTER_HEALTH_KEY)
    if not isinstance(payload, dict):
        return {
            "cluster_cohesion_score": DEFAULT_CLUSTER_COHESION_SCORE,
            "split_risk_score": DEFAULT_SPLIT_RISK_SCORE,
        }
    return {
        "cluster_cohesion_score": _bounded_float(
            payload.get("cluster_cohesion_score"),
            default=DEFAULT_CLUSTER_COHESION_SCORE,
        ),
        "split_risk_score": _bounded_float(
            payload.get("split_risk_score"),
            default=DEFAULT_SPLIT_RISK_SCORE,
        ),
    }


def apply_default_cluster_health(event: Any) -> None:
    """Persist the default singleton-cluster health metadata on an event."""

    _store_cluster_health(
        event=event,
        cluster_cohesion_score=DEFAULT_CLUSTER_COHESION_SCORE,
        split_risk_score=DEFAULT_SPLIT_RISK_SCORE,
    )


def apply_merge_cluster_health(event: Any, *, similarity: float) -> None:
    """Update bounded cluster-health metadata after a similarity-based merge."""

    current = cluster_health_payload(event)
    current_count = max(1, int(getattr(event, "source_count", 1) or 1))
    prior_count = max(1, current_count - 1)
    bounded_similarity = _bounded_float(similarity, default=DEFAULT_CLUSTER_COHESION_SCORE)
    cluster_cohesion_score = (
        (current["cluster_cohesion_score"] * prior_count) + bounded_similarity
    ) / current_count
    split_risk_score = max(current["split_risk_score"], 1.0 - bounded_similarity)
    _store_cluster_health(
        event=event,
        cluster_cohesion_score=cluster_cohesion_score,
        split_risk_score=split_risk_score,
    )


def apply_repaired_cluster_health(
    event: Any,
    *,
    item_embeddings: list[list[float] | None],
) -> None:
    """Recompute cluster health from the repaired event's current item embeddings."""

    if len(item_embeddings) <= 1:
        apply_default_cluster_health(event)
        return
    similarities: list[float] = []
    for left_embedding, right_embedding in combinations(item_embeddings, 2):
        if left_embedding is None or right_embedding is None:
            continue
        try:
            similarities.append(cosine_similarity(left_embedding, right_embedding))
        except ValueError:
            continue
    if not similarities:
        apply_default_cluster_health(event)
        return
    _store_cluster_health(
        event=event,
        cluster_cohesion_score=sum(similarities) / len(similarities),
        split_risk_score=max(1.0 - similarity for similarity in similarities),
    )


def cluster_cohesion_score(event: Any) -> float:
    """Return the stored cluster-cohesion score with defaults."""

    return cluster_health_payload(event)["cluster_cohesion_score"]


def split_risk_score(event: Any) -> float:
    """Return the stored split-risk score with defaults."""

    return cluster_health_payload(event)["split_risk_score"]


async def ensure_cluster_health(
    *,
    session: AsyncSession,
    event: Any,
) -> dict[str, float]:
    """Hydrate missing cluster-health metadata from the event's current items."""

    if _has_stored_cluster_health(event):
        return cluster_health_payload(event)

    event_id = getattr(event, "id", None)
    if event_id is None:
        apply_default_cluster_health(event)
        return cluster_health_payload(event)

    item_embeddings = list(
        (
            await session.scalars(
                select(RawItem.embedding)
                .join(EventItem, EventItem.item_id == RawItem.id)
                .where(EventItem.event_id == event_id)
                .order_by(EventItem.added_at.asc(), RawItem.fetched_at.asc().nullslast())
            )
        ).all()
    )
    apply_repaired_cluster_health(event, item_embeddings=item_embeddings)
    return cluster_health_payload(event)


def _store_cluster_health(
    *,
    event: Any,
    cluster_cohesion_score: float,
    split_risk_score: float,
) -> None:
    provenance_summary = dict(getattr(event, "provenance_summary", None) or {})
    provenance_summary[CLUSTER_HEALTH_KEY] = {
        "cluster_cohesion_score": round(
            _bounded_float(cluster_cohesion_score, default=DEFAULT_CLUSTER_COHESION_SCORE), 6
        ),
        "split_risk_score": round(
            _bounded_float(split_risk_score, default=DEFAULT_SPLIT_RISK_SCORE), 6
        ),
    }
    event.provenance_summary = provenance_summary


def _bounded_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _has_stored_cluster_health(event: Any) -> bool:
    provenance_summary = getattr(event, "provenance_summary", None)
    return isinstance(provenance_summary, dict) and isinstance(
        provenance_summary.get(CLUSTER_HEALTH_KEY),
        dict,
    )
