from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval import audit as audit_module

pytestmark = pytest.mark.unit


def _write_dataset(path: Path, *, human_verified: int, llm_seeded: int, duplicate: bool) -> None:
    rows: list[dict[str, object]] = []
    for index in range(human_verified):
        content = "Repeated human content." if duplicate else f"Human content {index}."
        rows.append(
            {
                "item_id": f"human-{index}",
                "title": f"Human row {index}",
                "content": content,
                "label_verification": "human_verified",
                "expected": {
                    "tier1": {
                        "trend_scores": {"eu-russia": 8, "us-china": 2, "middle-east": 1},
                        "max_relevance": 8,
                    },
                    "tier2": {
                        "trend_id": "eu-russia",
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                        "severity": 0.8,
                        "confidence": 0.9,
                    },
                },
            }
        )
    for index in range(llm_seeded):
        rows.append(
            {
                "item_id": f"llm-{index}",
                "title": f"LLM row {index}",
                "content": "Repeated llm content." if duplicate else f"LLM content {index}.",
                "label_verification": "llm_seeded",
                "expected": {
                    "tier1": {
                        "trend_scores": {"eu-russia": 1, "us-china": 1, "middle-east": 1},
                        "max_relevance": 1,
                    },
                    "tier2": None,
                },
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_run_gold_set_audit_reports_warnings_for_low_quality_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    _write_dataset(dataset_path, human_verified=0, llm_seeded=4, duplicate=True)

    result = audit_module.run_gold_set_audit(
        gold_set_path=str(dataset_path),
        output_dir=str(output_dir),
        max_items=200,
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["items_evaluated"] == 4
    assert payload["passes_quality_gate"] is False
    assert payload["summary"]["label_verification_counts"] == {"llm_seeded": 4}
    assert payload["summary"]["content"]["unique_count"] == 1
    assert payload["summary"]["content"]["duplicate_group_count"] == 1
    assert any("No human_verified labels present." in warning for warning in payload["warnings"])
    assert any("Low content diversity" in warning for warning in payload["warnings"])
    assert any("Duplicate content groups detected" in warning for warning in payload["warnings"])


def test_run_gold_set_audit_passes_for_human_verified_diverse_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    _write_dataset(dataset_path, human_verified=4, llm_seeded=0, duplicate=False)

    result = audit_module.run_gold_set_audit(
        gold_set_path=str(dataset_path),
        output_dir=str(output_dir),
        max_items=200,
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["items_evaluated"] == 4
    assert payload["passes_quality_gate"] is True
    assert payload["warnings"] == []
    assert payload["summary"]["label_verification_counts"] == {"human_verified": 4}
