from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.eval.behavior as behavior_module
import src.eval.behavior_cases_retrieval as behavior_cases_retrieval_module

pytestmark = pytest.mark.unit


def test_behavior_suites_include_context_retrieval(tmp_path: Path) -> None:
    result = behavior_module.run_behavior_evals(
        output_dir=tmp_path,
        suites=["context-retrieval"],
    )

    assert result.passes_validation is True
    assert result.selected_suites == ("context-retrieval",)
    assert result.selected_cases == 2
    assert "context-retrieval" in behavior_module.available_behavior_suites()

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["suites"] == [
        {
            "failed_cases": 0,
            "selected_cases": 2,
            "suite": "context-retrieval",
        }
    ]

    for case in payload["cases"]:
        assert case["suite"] == "context-retrieval"
        evidence = case["evidence"]
        assert evidence["retrieval_mode"] == "implement"
        assert evidence["retrieval_phase"] == "phase-1-cli-first"
        assert evidence["authoritative_source_basis"]["policy_registry_id"] == (
            "implement-mode-legacy-policy-v1"
        )


def test_retrieval_behavior_cases_require_raises_on_false_condition() -> None:
    with pytest.raises(ValueError, match="boom"):
        behavior_cases_retrieval_module._require(False, "boom")
