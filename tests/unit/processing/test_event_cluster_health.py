from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.processing.event_cluster_health import (
    apply_default_cluster_health,
    apply_merge_cluster_health,
    apply_repaired_cluster_health,
    cluster_cohesion_score,
    cluster_health_payload,
    ensure_cluster_health,
    split_risk_score,
)

pytestmark = pytest.mark.unit


def test_cluster_health_payload_defaults_when_provenance_missing_or_invalid() -> None:
    assert cluster_health_payload(SimpleNamespace(provenance_summary=None)) == {
        "cluster_cohesion_score": 1.0,
        "split_risk_score": 0.0,
    }
    assert cluster_health_payload(SimpleNamespace(provenance_summary={"method": "fallback"})) == {
        "cluster_cohesion_score": 1.0,
        "split_risk_score": 0.0,
    }
    assert cluster_health_payload(
        SimpleNamespace(
            provenance_summary={
                "cluster_health": {
                    "cluster_cohesion_score": "bad",
                    "split_risk_score": 4,
                }
            }
        )
    ) == {
        "cluster_cohesion_score": 1.0,
        "split_risk_score": 1.0,
    }


def test_apply_default_cluster_health_persists_default_scores() -> None:
    event = SimpleNamespace(provenance_summary={"method": "provenance_aware"})

    apply_default_cluster_health(event)

    assert event.provenance_summary["cluster_health"]["cluster_cohesion_score"] == pytest.approx(
        1.0
    )
    assert event.provenance_summary["cluster_health"]["split_risk_score"] == pytest.approx(0.0)


def test_apply_merge_cluster_health_updates_running_scores_and_getters() -> None:
    event = SimpleNamespace(
        source_count=4,
        provenance_summary={
            "cluster_health": {
                "cluster_cohesion_score": 0.8,
                "split_risk_score": 0.25,
            }
        },
    )

    apply_merge_cluster_health(event, similarity=0.5)

    assert cluster_cohesion_score(event) == pytest.approx(0.725)
    assert split_risk_score(event) == pytest.approx(0.5)


def test_apply_repaired_cluster_health_recomputes_pairwise_similarity() -> None:
    event = SimpleNamespace(provenance_summary={"method": "provenance_aware"})

    apply_repaired_cluster_health(
        event,
        item_embeddings=[
            [1.0, 0.0],
            [0.0, 1.0],
        ],
    )

    assert cluster_cohesion_score(event) == pytest.approx(0.0)
    assert split_risk_score(event) == pytest.approx(1.0)


def test_apply_repaired_cluster_health_defaults_when_no_comparable_embeddings() -> None:
    event = SimpleNamespace(
        provenance_summary={
            "cluster_health": {
                "cluster_cohesion_score": 0.2,
                "split_risk_score": 0.8,
            }
        }
    )

    apply_repaired_cluster_health(
        event,
        item_embeddings=[
            None,
            None,
        ],
    )

    assert cluster_cohesion_score(event) == pytest.approx(1.0)
    assert split_risk_score(event) == pytest.approx(0.0)


def test_apply_repaired_cluster_health_ignores_invalid_embedding_pairs() -> None:
    event = SimpleNamespace(provenance_summary={"method": "provenance_aware"})

    apply_repaired_cluster_health(
        event,
        item_embeddings=[
            [1.0],
            [1.0, 0.0],
        ],
    )

    assert cluster_cohesion_score(event) == pytest.approx(1.0)
    assert split_risk_score(event) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_ensure_cluster_health_backfills_missing_scores_from_item_embeddings() -> None:
    event = SimpleNamespace(id=uuid4(), provenance_summary={"method": "provenance_aware"})
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: [[1.0, 0.0], [0.0, 1.0]])

    payload = await ensure_cluster_health(session=session, event=event)

    assert payload["cluster_cohesion_score"] == pytest.approx(0.0)
    assert payload["split_risk_score"] == pytest.approx(1.0)
    assert event.provenance_summary["cluster_health"] == {
        "cluster_cohesion_score": pytest.approx(0.0),
        "split_risk_score": pytest.approx(1.0),
    }


@pytest.mark.asyncio
async def test_ensure_cluster_health_defaults_when_event_has_no_id() -> None:
    event = SimpleNamespace(id=None, provenance_summary={"method": "provenance_aware"})
    session = AsyncMock()

    payload = await ensure_cluster_health(session=session, event=event)

    assert payload == {
        "cluster_cohesion_score": 1.0,
        "split_risk_score": 0.0,
    }
    session.scalars.assert_not_called()
