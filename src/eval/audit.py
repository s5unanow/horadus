"""
Gold-set quality audit utilities for evaluation datasets.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.eval.benchmark import HUMAN_VERIFIED_LABEL, GoldSetItem, load_gold_set


@dataclass(slots=True)
class AuditRunResult:
    """Result handle for a completed gold-set audit run."""

    output_path: Path
    warnings: list[str]


def run_gold_set_audit(
    *,
    gold_set_path: str,
    output_dir: str,
    max_items: int = 200,
) -> AuditRunResult:
    """Run gold-set quality audit and persist JSON result."""
    items = load_gold_set(Path(gold_set_path), max_items=max(1, max_items))
    payload = _build_audit_payload(items=items, gold_set_path=Path(gold_set_path))
    output_path = _write_audit_result(output_dir=Path(output_dir), payload=payload)
    warnings = [str(message) for message in payload["warnings"]]
    return AuditRunResult(output_path=output_path, warnings=warnings)


def _build_audit_payload(*, items: list[GoldSetItem], gold_set_path: Path) -> dict[str, Any]:
    label_counts = Counter(item.label_verification for item in items)
    content_counts = Counter(_normalize_text(item.content) for item in items)
    tier2_items = [item for item in items if item.tier2 is not None]
    max_relevance_counts = Counter(item.tier1.max_relevance for item in items)

    total_items = len(items)
    unique_content_count = len(content_counts)
    duplicate_groups = _duplicate_groups(content_counts)
    warnings: list[str] = []

    human_verified_count = label_counts.get(HUMAN_VERIFIED_LABEL, 0)
    if human_verified_count == 0:
        warnings.append("No human_verified labels present.")

    unique_content_ratio = unique_content_count / total_items if total_items > 0 else 0.0
    if unique_content_ratio < 0.8:
        warnings.append(
            "Low content diversity detected "
            f"({unique_content_count}/{total_items} unique contents)."
        )

    if duplicate_groups:
        warnings.append(
            "Duplicate content groups detected "
            f"({len(duplicate_groups)} groups, largest={duplicate_groups[0]['count']})."
        )

    if label_counts.get("unknown", 0) > 0:
        warnings.append("Rows with unknown label_verification value detected.")

    tier2_coverage = len(tier2_items) / total_items if total_items > 0 else 0.0
    if tier2_coverage < 0.3:
        warnings.append(
            f"Low Tier-2 label coverage detected ({len(tier2_items)}/{total_items} rows)."
        )

    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "gold_set_path": str(gold_set_path),
        "items_evaluated": total_items,
        "passes_quality_gate": len(warnings) == 0,
        "warnings": warnings,
        "summary": {
            "label_verification_counts": dict(sorted(label_counts.items())),
            "human_verified_ratio": round(human_verified_count / total_items, 6)
            if total_items > 0
            else 0.0,
            "tier2_labeled_items": len(tier2_items),
            "tier2_coverage_ratio": round(tier2_coverage, 6),
            "max_relevance_distribution": dict(sorted(max_relevance_counts.items())),
            "content": {
                "unique_count": unique_content_count,
                "unique_ratio": round(unique_content_ratio, 6),
                "duplicate_group_count": len(duplicate_groups),
                "top_duplicate_groups": duplicate_groups[:10],
            },
        },
    }


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _duplicate_groups(counts: Counter[str]) -> list[dict[str, Any]]:
    groups = [{"count": count, "sample": key[:120]} for key, count in counts.items() if count > 1]
    return sorted(groups, key=lambda row: int(row["count"]), reverse=True)


def _write_audit_result(*, output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"audit-{timestamp}-{uuid4().hex[:8]}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
