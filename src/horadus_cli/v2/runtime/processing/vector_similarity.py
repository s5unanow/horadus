"""
Vector similarity helpers used by retrieval and benchmarking paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeVar

EntityT = TypeVar("EntityT")


@dataclass(slots=True, frozen=True)
class NeighborResult:
    """Nearest-neighbor candidate with similarity score."""

    entity_id: str
    similarity: float


def max_distance_for_similarity(similarity_threshold: float) -> float:
    """Convert cosine similarity threshold into pgvector cosine-distance upper bound."""
    if not 0 <= similarity_threshold <= 1:
        msg = "similarity_threshold must be between 0 and 1"
        raise ValueError(msg)
    return 1.0 - similarity_threshold


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity for two equal-length vectors."""
    if len(left) != len(right):
        msg = "Vectors must have matching dimensions"
        raise ValueError(msg)
    if not left:
        msg = "Vectors must not be empty"
        raise ValueError(msg)

    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def nearest_neighbors(
    *,
    query_embedding: list[float],
    candidates: list[tuple[str, list[float]]],
    similarity_threshold: float,
    limit: int,
) -> list[NeighborResult]:
    """Return nearest neighbors above a configured similarity threshold."""
    if limit < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)

    rows: list[NeighborResult] = []
    for entity_id, embedding in candidates:
        similarity = cosine_similarity(query_embedding, embedding)
        if similarity < similarity_threshold:
            continue
        rows.append(NeighborResult(entity_id=entity_id, similarity=similarity))

    rows.sort(key=lambda row: (-row.similarity, row.entity_id))
    return rows[:limit]
