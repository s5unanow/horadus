from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.processing.trend_impact_mapping import (
    TREND_IMPACT_MAPPING_KEY,
    iter_unresolved_mapping_gaps,
    map_event_trend_impacts,
    taxonomy_gap_reason_for_mapping,
)
from src.storage.models import Event, TaxonomyGapReason

pytestmark = pytest.mark.unit


def _trend(
    *,
    trend_id: str = "eu-russia",
    indicators: dict[str, dict[str, object]] | None = None,
    actors: list[str] | None = None,
    regions: list[str] | None = None,
):
    return SimpleNamespace(
        id=uuid4(),
        name=trend_id,
        definition={
            "id": trend_id,
            "actors": actors or ["NATO", "Russia"],
            "regions": regions or ["Baltic region"],
        },
        indicators=indicators
        or {
            "military_movement": {
                "direction": "escalatory",
                "description": "Force repositioning without direct hostile contact.",
                "keywords": ["troop deployment", "deployment"],
            }
        },
    )


def test_map_event_trend_impacts_maps_keywords_deterministically() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Troop movement near the border",
        extracted_claims={
            "claims": ["Troop deployment increased near the border."],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Troop deployment increased near the border.",
                    }
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert result.diagnostics["unresolved"] == []
    assert len(result.impacts) == 1
    assert result.impacts[0]["trend_id"] == "eu-russia"
    assert result.impacts[0]["signal_type"] == "military_movement"
    assert result.impacts[0]["event_claim_key"] == "troop deployment increased near the border"


def test_map_event_trend_impacts_records_ambiguous_and_no_match_paths() -> None:
    ambiguous_event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_what="Troop movement near the border",
        extracted_claims={
            "claims": ["Troop deployment increased near the border."],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Troop deployment increased near the border.",
                    }
                ],
                "links": [],
            },
        },
    )
    ambiguous = map_event_trend_impacts(
        event=ambiguous_event,
        trends=[
            _trend(trend_id="eu-russia", actors=[], regions=[]),
            _trend(trend_id="us-china", actors=[], regions=[]),
        ],
    )
    assert ambiguous.impacts == []
    assert ambiguous.diagnostics["unresolved"][0]["reason"] == "ambiguous_mapping"

    no_match_event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_what="Economic talks resumed",
        extracted_claims={"claims": [], "claim_graph": {"nodes": [], "links": []}},
    )
    no_match = map_event_trend_impacts(
        event=no_match_event,
        trends=[
            _trend(
                indicators={
                    "incident": {
                        "direction": "escalatory",
                        "keywords": ["fired upon"],
                    }
                }
            )
        ],
    )
    assert no_match.impacts == []
    assert no_match.diagnostics["unresolved"][0]["reason"] == "no_matching_indicator"
    assert no_match.diagnostics["unresolved"][0]["event_claim_key"] == "__event__"


def test_mapping_helpers_expose_unresolved_payloads_and_reason_translation() -> None:
    empty_event = Event(id=uuid4(), extracted_claims={})
    assert iter_unresolved_mapping_gaps(empty_event) == []

    event = Event(
        id=uuid4(),
        extracted_claims={
            TREND_IMPACT_MAPPING_KEY: {
                "unresolved": [
                    {"reason": "ambiguous_mapping", "trend_id": "a", "signal_type": "b"},
                    "bad",
                ]
            }
        },
    )
    assert iter_unresolved_mapping_gaps(event) == [
        {"reason": "ambiguous_mapping", "trend_id": "a", "signal_type": "b"}
    ]
    assert (
        taxonomy_gap_reason_for_mapping("ambiguous_mapping") == TaxonomyGapReason.AMBIGUOUS_MAPPING
    )
    assert (
        taxonomy_gap_reason_for_mapping("anything-else") == TaxonomyGapReason.NO_MATCHING_INDICATOR
    )
