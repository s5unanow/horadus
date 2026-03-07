from __future__ import annotations

import pytest

import src.core.narrative_grounding as narrative_grounding
from src.core.narrative_grounding import (
    _collect_payload_numbers,
    _parse_numeric_token,
    build_grounding_references,
    evaluate_narrative_grounding,
)

pytestmark = pytest.mark.unit


def test_evaluate_narrative_grounding_passes_for_payload_supported_numbers() -> None:
    evaluation = evaluate_narrative_grounding(
        narrative="Current probability is 42.0% with 4 evidence updates.",
        evidence_payload={
            "statistics": {
                "current_probability": 0.42,
                "evidence_count_weekly": 4,
            }
        },
        violation_threshold=0,
    )

    assert evaluation.is_grounded is True
    assert evaluation.violation_count == 0
    assert evaluation.unsupported_claims == ()
    assert build_grounding_references(evaluation) is None


def test_evaluate_narrative_grounding_flags_unsupported_claims() -> None:
    evaluation = evaluate_narrative_grounding(
        narrative="Current probability is 90% with 4 evidence updates.",
        evidence_payload={
            "statistics": {
                "current_probability": 0.42,
                "evidence_count_weekly": 4,
            }
        },
        violation_threshold=0,
    )

    assert evaluation.is_grounded is False
    assert evaluation.violation_count == 1
    assert evaluation.unsupported_claims == ("90%",)
    assert build_grounding_references(evaluation) == {"unsupported_claims": ["90%"]}


def test_evaluate_narrative_grounding_handles_nested_payloads_and_thresholds() -> None:
    evaluation = evaluate_narrative_grounding(
        narrative="Roughly 10% support, 3 events, and 2.5 confidence were observed.",
        evidence_payload={
            "statistics": {
                "current_probability": 0.1,
                "event_count": 3,
            },
            "notes": ["Confidence stayed near 2.5"],
            "ignored": [True, None, float("inf")],
        },
        violation_threshold=1,
    )

    assert evaluation.is_grounded is True
    assert evaluation.violation_count == 0
    assert evaluation.unsupported_claims == ()


def test_evaluate_narrative_grounding_deduplicates_unsupported_tokens() -> None:
    evaluation = evaluate_narrative_grounding(
        narrative="Unsupported 77% repeats 77% and impossible nan token is ignored.",
        evidence_payload={"statistics": {"current_probability": 0.42}},
        violation_threshold=0,
    )

    assert evaluation.is_grounded is False
    assert evaluation.violation_count == 1
    assert evaluation.unsupported_claims == ("77%",)


def test_parse_numeric_token_and_collect_payload_numbers_handle_edge_cases() -> None:
    assert _parse_numeric_token("12x") is None
    assert _parse_numeric_token("inf") is None

    collected: list[float] = []
    _collect_payload_numbers(None, collected)
    _collect_payload_numbers(True, collected)
    _collect_payload_numbers(float("inf"), collected)
    _collect_payload_numbers([], collected)
    _collect_payload_numbers((), collected)
    _collect_payload_numbers(set(), collected)
    _collect_payload_numbers(("5%", "2", "skip"), collected)

    assert collected == [0.05, 2.0]


def test_narrative_grounding_skips_unparseable_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(narrative_grounding, "_parse_numeric_token", lambda _token: None)

    collected: list[float] = []
    narrative_grounding._collect_payload_numbers("12 15", collected)
    evaluation = narrative_grounding.evaluate_narrative_grounding(
        narrative="12 15",
        evidence_payload={},
    )

    assert collected == []
    assert evaluation.unsupported_claims == ()
