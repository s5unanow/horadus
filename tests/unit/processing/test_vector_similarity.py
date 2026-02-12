from __future__ import annotations

import pytest

from src.processing.vector_similarity import (
    max_distance_for_similarity,
    nearest_neighbors,
)

pytestmark = pytest.mark.unit


def test_max_distance_for_similarity_converts_threshold() -> None:
    assert max_distance_for_similarity(0.88) == pytest.approx(0.12)


def test_nearest_neighbors_respects_similarity_threshold_and_ordering() -> None:
    query = [1.0, 0.0, 0.0]
    candidates = [
        ("alpha", [0.99, 0.10, 0.0]),
        ("beta", [0.95, 0.25, 0.0]),
        ("gamma", [0.2, 0.98, 0.0]),
    ]

    rows = nearest_neighbors(
        query_embedding=query,
        candidates=candidates,
        similarity_threshold=0.9,
        limit=3,
    )

    assert [row.entity_id for row in rows] == ["alpha", "beta"]
    assert rows[0].similarity > rows[1].similarity


def test_nearest_neighbors_applies_limit() -> None:
    query = [1.0, 0.0, 0.0]
    candidates = [
        ("a", [1.0, 0.0, 0.0]),
        ("b", [0.99, 0.10, 0.0]),
        ("c", [0.98, 0.20, 0.0]),
    ]

    rows = nearest_neighbors(
        query_embedding=query,
        candidates=candidates,
        similarity_threshold=0.7,
        limit=2,
    )

    assert len(rows) == 2
