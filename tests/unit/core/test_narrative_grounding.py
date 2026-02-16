from __future__ import annotations

import pytest

from src.core.narrative_grounding import (
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
