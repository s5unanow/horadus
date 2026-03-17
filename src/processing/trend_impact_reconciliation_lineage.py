"""Lineage helpers kept separate to preserve code-shape budgets in reconciliation."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.core.trend_config import trend_runtime_id_for_record

if TYPE_CHECKING:
    from src.processing.trend_impact_reconciliation import DesiredTrendEvidence, ParsedTrendImpact
    from src.storage.models import Event, TrendEvidence

TREND_IMPACT_RECONCILIATION_KEY = "_trend_impact_reconciliation"


def _append_reconciliation_history(
    *,
    event: Event,
    invalidated_at: datetime,
    lineage_entries: list[dict[str, Any]],
) -> None:
    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    history_raw = claims.get(TREND_IMPACT_RECONCILIATION_KEY)
    history = list(history_raw) if isinstance(history_raw, list) else []
    history.append(
        {
            "reason": "tier2_reclassification",
            "recorded_at": invalidated_at.isoformat(),
            "superseded_evidence": lineage_entries,
        }
    )
    claims[TREND_IMPACT_RECONCILIATION_KEY] = history
    event.extracted_claims = claims


def _lineage_entry(
    *,
    evidence: TrendEvidence,
    trend_runtime_id: str,
    invalidated_at: datetime,
    replacement: DesiredTrendEvidence | None,
    change_type: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "change_type": change_type,
        "evidence_id": str(evidence.id) if evidence.id is not None else None,
        "trend_id": trend_runtime_id,
        "event_claim_id": str(evidence.event_claim_id),
        "signal_type": evidence.signal_type,
        "delta_log_odds": round(float(evidence.delta_log_odds), 6),
        "invalidated_at": invalidated_at.isoformat(),
    }
    if replacement is not None:
        entry["replacement"] = {
            "trend_id": trend_runtime_id_for_record(replacement.trend),
            "event_claim_id": str(replacement.event_claim.id),
            "signal_type": replacement.impact.signal_type,
            "direction": replacement.impact.direction,
            "severity": round(replacement.impact.severity, 6),
            "confidence": round(replacement.impact.confidence, 6),
        }
    return entry


def _taxonomy_gap_details(impact: ParsedTrendImpact) -> dict[str, Any]:
    return {
        "direction": impact.direction,
        "severity": impact.severity,
        "confidence": impact.confidence,
        "rationale": impact.rationale,
        "event_claim_key": impact.event_claim_key,
    }
