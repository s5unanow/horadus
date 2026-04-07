from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval import regression_intake as intake_module

pytestmark = pytest.mark.unit


def test_run_regression_intake_writes_taxonomy_gap_cases_with_redaction_metadata(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "taxonomy-gaps.json"
    input_path.write_text(
        json.dumps(
            {
                "trace_context": {"trace_id": "abc123"},
                "items": [
                    {
                        "id": "gap-1",
                        "event_id": "event-1",
                        "trend_id": "eu-russia",
                        "signal_type": "force_posture_shift",
                        "reason": "unknown_signal_type",
                        "source": "pipeline",
                        "status": "open",
                        "observed_at": "2026-04-07T10:00:00Z",
                        "details": {"rationale": "Model emitted a new signal."},
                        "resolved_by": "analyst@horadus",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = intake_module.run_regression_intake(
        source_surface="taxonomy-gap",
        input_path=str(input_path),
        output_dir=str(tmp_path / "results"),
    )

    assert result.source_surface == "taxonomy-gap"
    assert result.total_records == 1
    assert result.emitted_cases == 1

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    case = payload["cases"][0]
    assert payload["format_version"] == "regression-intake.v1"
    assert payload["provenance"]["trace_context"] == {"trace_id": "abc123"}
    assert case["recommended_behavior_suite"] == "taxonomy-safety"
    assert case["seed"]["details"] == {"rationale": "Model emitted a new signal."}
    assert case["redaction_expectations"]["freeform_fields"] == ["details.rationale"]
    assert case["redaction_expectations"]["operator_identity_fields"] == ["resolved_by"]


def test_run_regression_intake_filters_report_grounding_rows_to_violations(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "reports.json"
    input_path.write_text(
        json.dumps(
            {
                "reports": [
                    {
                        "id": "report-1",
                        "report_type": "weekly",
                        "grounding_status": "grounded",
                        "grounding_violation_count": 0,
                    },
                    {
                        "id": "report-2",
                        "report_type": "monthly",
                        "trend_id": "trend-1",
                        "grounding_status": "flagged",
                        "grounding_violation_count": 2,
                        "narrative": "Unsupported claim with specific source text.",
                        "grounding_references": {"unsupported_claims": ["claim-1"]},
                        "generation_manifest": {"artifact_status": {"provisional": True}},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = intake_module.run_regression_intake(
        source_surface="report-grounding",
        input_path=str(input_path),
        output_dir=str(tmp_path / "results"),
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    case = payload["cases"][0]
    assert result.total_records == 2
    assert result.emitted_cases == 1
    assert case["recommended_behavior_suite"] == "report-grounding"
    assert case["seed"]["grounding_violation_count"] == 2
    assert case["seed"]["narrative_excerpt"] == "Unsupported claim with specific source text."
    assert case["redaction_expectations"]["freeform_fields"] == [
        "narrative",
        "grounding_references",
        "generation_manifest",
    ]


def test_run_regression_intake_rejects_inputs_without_matching_candidates(tmp_path: Path) -> None:
    input_path = tmp_path / "reports.json"
    input_path.write_text(
        json.dumps(
            {
                "reports": [
                    {
                        "id": "report-1",
                        "report_type": "weekly",
                        "grounding_status": "grounded",
                        "grounding_violation_count": 0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="No regression-intake candidates found for surface 'report-grounding'",
    ):
        intake_module.run_regression_intake(
            source_surface="report-grounding",
            input_path=str(input_path),
            output_dir=str(tmp_path / "results"),
        )


def test_helper_paths_cover_surface_and_payload_validation(tmp_path: Path) -> None:
    assert intake_module.available_regression_intake_surfaces() == (
        "report-grounding",
        "taxonomy-gap",
    )

    with pytest.raises(ValueError, match="Unknown source surface 'unknown'"):
        intake_module._normalize_source_surface("unknown")

    with pytest.raises(ValueError, match="Input artifact not found"):
        intake_module._load_json_payload(tmp_path / "missing.json")

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Input artifact is not valid JSON"):
        intake_module._load_json_payload(invalid_json)

    assert intake_module._extract_records([{"id": "row-1"}]) == [{"id": "row-1"}]
    assert intake_module._extract_records({"items": [{"id": "row-2"}]}) == [{"id": "row-2"}]
    assert intake_module._extract_records({"id": "row-3"}) == [{"id": "row-3"}]

    with pytest.raises(ValueError, match="Input artifact must decode to a JSON object or array"):
        intake_module._extract_records("bad")

    with pytest.raises(ValueError, match="Each input record must be a JSON object"):
        intake_module._ensure_mapping_records([{"id": "ok"}, "bad"])


def test_helper_paths_cover_redaction_trace_and_scalar_edges() -> None:
    taxonomy_redaction = intake_module._taxonomy_gap_redaction_expectations(
        {"resolution_notes": "review text"}
    )
    report_redaction = intake_module._report_grounding_redaction_expectations({})

    assert taxonomy_redaction["freeform_fields"] == ["details.rationale", "resolution_notes"]
    assert taxonomy_redaction["operator_identity_fields"] == []
    assert report_redaction["freeform_fields"] == ["narrative", "grounding_references"]
    assert intake_module._extract_trace_context("bad") is None
    assert intake_module._extract_trace_context(
        {
            "trace": {"trace_id": "trace-1"},
            "traceparent": "parent-1",
        }
    ) == {"trace_id": "trace-1", "traceparent": "parent-1"}

    with pytest.raises(ValueError, match="Record is missing required field 'trend_id'"):
        intake_module._required_string({}, "trend_id")

    assert intake_module._optional_string({"value": "  trimmed  "}, "value") == "trimmed"
    assert intake_module._optional_string({"value": "   "}, "value") is None
    assert intake_module._coerce_int(None) == 0
    with pytest.raises(ValueError, match="grounding_violation_count must be an integer-like value"):
        intake_module._coerce_int("not-an-int")
    assert intake_module._narrative_excerpt(None) is None
    assert intake_module._narrative_excerpt("x" * 10, limit=8) == "xxxxx..."
    assert intake_module._recommended_behavior_suites(
        [
            {"recommended_behavior_suite": "report-grounding"},
            {"recommended_behavior_suite": "taxonomy-safety"},
            {"recommended_behavior_suite": "report-grounding"},
            {},
        ]
    ) == ["report-grounding", "taxonomy-safety"]
