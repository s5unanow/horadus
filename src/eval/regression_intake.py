"""Convert runtime failure artifacts into reviewable eval-regression intake cases."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.eval import artifact_provenance as provenance

_FORMAT_VERSION = "regression-intake.v1"
_RESULT_PREFIX = "regression-intake"
_SUPPORTED_SURFACES = ("report-grounding", "taxonomy-gap")
_TRACE_CONTEXT_KEYS = ("trace_id", "span_id", "traceparent", "request_id")


@dataclass(frozen=True, slots=True)
class RegressionIntakeRunResult:
    """Summary handle for a completed regression-intake run."""

    output_path: Path
    source_surface: str
    total_records: int
    emitted_cases: int


def available_regression_intake_surfaces() -> tuple[str, ...]:
    """Return supported runtime-failure surfaces for intake generation."""

    return _SUPPORTED_SURFACES


def run_regression_intake(
    *,
    source_surface: str,
    input_path: str,
    output_dir: str,
) -> RegressionIntakeRunResult:
    """Normalize a runtime failure export into reviewable regression-intake cases."""

    normalized_surface = _normalize_source_surface(source_surface)
    artifact_path = Path(input_path).resolve()
    payload = _load_json_payload(artifact_path)
    records = _extract_records(payload)
    cases = _build_cases(
        source_surface=normalized_surface,
        records=records,
        artifact_path=artifact_path,
    )
    if not cases:
        msg = f"No regression-intake candidates found for surface '{normalized_surface}'."
        raise ValueError(msg)

    artifact_manifest = provenance.build_file_manifest_provenance(
        {"input_artifact": artifact_path}
    )["input_artifact"]
    output_path = _write_result(
        output_dir=Path(output_dir),
        payload={
            "format_version": _FORMAT_VERSION,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "source_surface": normalized_surface,
            "summary": {
                "total_records": len(records),
                "emitted_cases": len(cases),
                "recommended_behavior_suites": _recommended_behavior_suites(cases),
            },
            "review_flow": {
                "steps": [
                    "Review freeform text and operator identifiers before promotion.",
                    "Promote repeated labeling/classification failures into ai/eval/gold_set.jsonl.",
                    "Promote deterministic contract failures into the recommended behavior suite.",
                ],
                "redaction_required": True,
            },
            "provenance": {
                "source_control": provenance.build_source_control_provenance(),
                "input_artifact": artifact_manifest,
                "trace_context": _extract_trace_context(payload),
            },
            "cases": cases,
        },
    )
    return RegressionIntakeRunResult(
        output_path=output_path,
        source_surface=normalized_surface,
        total_records=len(records),
        emitted_cases=len(cases),
    )


def _normalize_source_surface(source_surface: str) -> str:
    normalized = source_surface.strip().lower()
    if normalized not in _SUPPORTED_SURFACES:
        supported = ", ".join(_SUPPORTED_SURFACES)
        msg = f"Unknown source surface '{source_surface}'. Available: {supported}"
        raise ValueError(msg)
    return normalized


def _load_json_payload(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        msg = f"Input artifact not found: {path}"
        raise ValueError(msg) from None
    except json.JSONDecodeError as exc:
        msg = f"Input artifact is not valid JSON: {exc}"
        raise ValueError(msg) from exc


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _ensure_mapping_records(payload)
    if not isinstance(payload, dict):
        msg = "Input artifact must decode to a JSON object or array."
        raise ValueError(msg)
    for key in ("items", "reports"):
        nested = payload.get(key)
        if isinstance(nested, list):
            return _ensure_mapping_records(nested)
    return _ensure_mapping_records([payload])


def _ensure_mapping_records(records: list[Any]) -> list[dict[str, Any]]:
    if any(not isinstance(record, dict) for record in records):
        msg = "Each input record must be a JSON object."
        raise ValueError(msg)
    return [dict(record) for record in records]


def _build_cases(
    *,
    source_surface: str,
    records: list[dict[str, Any]],
    artifact_path: Path,
) -> list[dict[str, Any]]:
    if source_surface == "taxonomy-gap":
        return _taxonomy_gap_cases(records=records, artifact_path=artifact_path)
    return _report_grounding_cases(records=records, artifact_path=artifact_path)


def _taxonomy_gap_cases(
    *,
    records: list[dict[str, Any]],
    artifact_path: Path,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        trend_id = _required_string(record, "trend_id")
        signal_type = _required_string(record, "signal_type")
        reason = _required_string(record, "reason")
        case_id = _record_case_id("taxonomy-gap", record)
        cases.append(
            {
                "case_id": case_id,
                "title": f"Taxonomy gap: {trend_id}/{signal_type}",
                "source_surface": "taxonomy-gap",
                "failure_mode": reason,
                "summary": (
                    "Deterministic trend-impact mapping skipped a runtime impact and "
                    "recorded a taxonomy-gap row for analyst review."
                ),
                "tags": ["runtime", "taxonomy-gap", "mapping-safety"],
                "recommended_behavior_suite": "taxonomy-safety",
                "alternate_promotion_targets": ["ai/eval/gold_set.jsonl"],
                "redaction_expectations": _taxonomy_gap_redaction_expectations(record),
                "provenance": _record_provenance(
                    artifact_path=artifact_path,
                    record=record,
                    record_index=index,
                    event_id=_optional_string(record, "event_id"),
                    observed_at=_optional_string(record, "observed_at"),
                    status=_optional_string(record, "status"),
                ),
                "seed": {
                    "trend_id": trend_id,
                    "signal_type": signal_type,
                    "reason": reason,
                    "source": _optional_string(record, "source"),
                    "details": record.get("details")
                    if isinstance(record.get("details"), dict)
                    else {},
                },
            }
        )
    return cases


def _report_grounding_cases(
    *,
    records: list[dict[str, Any]],
    artifact_path: Path,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        grounding_status = _required_string(record, "grounding_status")
        violation_count = _coerce_int(record.get("grounding_violation_count"))
        if grounding_status != "flagged" and violation_count <= 0:
            continue
        case_id = _record_case_id("report-grounding", record)
        cases.append(
            {
                "case_id": case_id,
                "title": (
                    f"Report grounding violation: "
                    f"{_optional_string(record, 'report_type') or 'report'}"
                ),
                "source_surface": "report-grounding",
                "failure_mode": grounding_status,
                "summary": (
                    "A generated report surfaced unsupported narrative claims or "
                    "grounding violations and should seed a regression check."
                ),
                "tags": ["runtime", "reporting", "grounding"],
                "recommended_behavior_suite": "report-grounding",
                "alternate_promotion_targets": ["ai/eval/gold_set.jsonl"],
                "redaction_expectations": _report_grounding_redaction_expectations(record),
                "provenance": _record_provenance(
                    artifact_path=artifact_path,
                    record=record,
                    record_index=index,
                    trend_id=_optional_string(record, "trend_id"),
                    created_at=_optional_string(record, "created_at"),
                ),
                "seed": {
                    "report_type": _optional_string(record, "report_type"),
                    "trend_id": _optional_string(record, "trend_id"),
                    "grounding_status": grounding_status,
                    "grounding_violation_count": violation_count,
                    "grounding_references": record.get("grounding_references"),
                    "generation_manifest": record.get("generation_manifest"),
                    "narrative_excerpt": _narrative_excerpt(_optional_string(record, "narrative")),
                },
            }
        )
    return cases


def _taxonomy_gap_redaction_expectations(record: dict[str, Any]) -> dict[str, Any]:
    freeform_fields = ["details.rationale"]
    operator_identity_fields: list[str] = []
    if record.get("resolution_notes") not in (None, ""):
        freeform_fields.append("resolution_notes")
    if record.get("resolved_by") not in (None, ""):
        operator_identity_fields.append("resolved_by")
    return {
        "review_required": True,
        "freeform_fields": freeform_fields,
        "operator_identity_fields": operator_identity_fields,
        "notes": [
            "Review mapping rationale before promotion.",
            "Remove analyst names, emails, and ticket references from resolution fields.",
        ],
    }


def _report_grounding_redaction_expectations(record: dict[str, Any]) -> dict[str, Any]:
    freeform_fields = ["narrative", "grounding_references"]
    if record.get("generation_manifest") is not None:
        freeform_fields.append("generation_manifest")
    return {
        "review_required": True,
        "freeform_fields": freeform_fields,
        "operator_identity_fields": [],
        "notes": [
            "Review quoted report text before promotion.",
            "Drop unsupported claims or source identifiers that should not enter tracked eval data.",
        ],
    }


def _record_provenance(
    *,
    artifact_path: Path,
    record: dict[str, Any],
    record_index: int,
    **metadata: str | None,
) -> dict[str, Any]:
    provenance_payload: dict[str, Any] = {
        "source_record_id": _optional_string(record, "id"),
        "source_artifact_path": str(artifact_path),
        "record_index": record_index,
        "record_sha256": _record_sha256(record),
        "trace_context": _extract_trace_context(record),
    }
    for key, value in metadata.items():
        if value is not None:
            provenance_payload[key] = value
    return provenance_payload


def _record_case_id(source_surface: str, record: dict[str, Any]) -> str:
    raw_id = _optional_string(record, "id")
    suffix = raw_id or _record_sha256(record)[:12]
    return f"{source_surface}-{suffix}"


def _record_sha256(record: dict[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _recommended_behavior_suites(cases: list[dict[str, Any]]) -> list[str]:
    suites = {
        str(case["recommended_behavior_suite"])
        for case in cases
        if case.get("recommended_behavior_suite")
    }
    return sorted(suites)


def _extract_trace_context(payload: Any) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    candidates = [payload]
    for key in ("trace_context", "trace"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            candidates.insert(0, nested)

    trace_context: dict[str, str] = {}
    for candidate in candidates:
        for key in _TRACE_CONTEXT_KEYS:
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                trace_context[key] = value.strip()
    return trace_context or None


def _required_string(record: dict[str, Any], key: str) -> str:
    value = _optional_string(record, key)
    if value is None:
        msg = f"Record is missing required field '{key}'."
        raise ValueError(msg)
    return value


def _optional_string(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        msg = "grounding_violation_count must be an integer-like value."
        raise ValueError(msg) from exc


def _narrative_excerpt(narrative: str | None, *, limit: int = 280) -> str | None:
    if narrative is None:
        return None
    if len(narrative) <= limit:
        return narrative
    return narrative[: limit - 3].rstrip() + "..."


def _write_result(*, output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{_RESULT_PREFIX}-{timestamp}-{uuid4().hex[:8]}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
