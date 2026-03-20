"""Helpers for event feedback payloads and review-queue ranking."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.api.routes.feedback_models import ReviewQueueItem, ReviewQueueTrendImpact
from src.core.trend_restatement import HISTORICAL_ARTIFACT_POLICY
from src.storage.event_state import event_state_snapshot

if TYPE_CHECKING:
    from src.storage.models import Event, TrendEvidence


def event_feedback_original_value(
    evidences: list[TrendEvidence],
    *,
    event: Event | None = None,
) -> dict[str, Any]:
    """Serialize the pre-feedback evidence and optional event-state snapshot."""

    trend_deltas: dict[str, float] = {}
    for evidence in evidences:
        trend_key = str(evidence.trend_id)
        trend_deltas[trend_key] = trend_deltas.get(trend_key, 0.0) + float(evidence.delta_log_odds)
    payload = {
        "evidence_count": len(evidences),
        "active_evidence_ids": [
            str(evidence.id) for evidence in evidences if evidence.id is not None
        ],
        "active_event_claim_ids": sorted({str(evidence.event_claim_id) for evidence in evidences}),
        "trend_deltas": trend_deltas,
    }
    if event is not None:
        payload.update(event_state_snapshot(event))
    return payload


def event_feedback_corrected_value(
    *,
    action: str,
    event_id: UUID,
    at: datetime,
    evidences: list[TrendEvidence],
    total_compensation_delta: float,
    trend_adjustments: dict[str, dict[str, float]] | None = None,
    event: Event | None = None,
    changed_axes: tuple[str, ...] = (),
    axis_reasons: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Serialize the post-feedback effect summary plus optional state metadata."""

    evidence_ids = [str(evidence.id) for evidence in evidences if evidence.id is not None]
    event_claim_ids = sorted({str(evidence.event_claim_id) for evidence in evidences})
    payload = {
        "event_id": str(event_id),
        "action": action,
        "affected_trend_count": len({evidence.trend_id for evidence in evidences}),
        "affected_evidence_count": len(evidences),
        "affected_evidence_ids": evidence_ids,
        "affected_event_claim_ids": event_claim_ids,
        "total_compensation_delta_log_odds": total_compensation_delta,
        "historical_artifact_policy": HISTORICAL_ARTIFACT_POLICY,
        "recorded_at": at.isoformat(),
    }
    if action == "invalidate":
        payload.update(
            {
                "reverted_event_id": str(event_id),
                "invalidated_evidence_count": len(evidences),
                "invalidated_evidence_ids": evidence_ids,
                "invalidated_event_claim_ids": event_claim_ids,
                "trend_adjustments": trend_adjustments or {},
                "invalidated_at": at.isoformat(),
            }
        )
    if event is not None:
        payload.update(event_state_snapshot(event))
    if changed_axes:
        payload["changed_axes"] = list(changed_axes)
        payload["axis_reasons"] = axis_reasons or {}
    return payload


def _claim_graph_contradiction_links(event: Event) -> int:
    if not isinstance(event.extracted_claims, dict):
        return 0
    claim_graph = event.extracted_claims.get("claim_graph")
    if not isinstance(claim_graph, dict):
        return 0
    links = claim_graph.get("links")
    if not isinstance(links, list):
        return 0
    return sum(
        1
        for link in links
        if isinstance(link, dict) and str(link.get("relation", "")).strip().lower() == "contradict"
    )


def _uncertainty_score(evidence_rows: list[tuple[Any, ...]]) -> float:
    confidences = [float(row[5]) for row in evidence_rows if row[5] is not None]
    corroborations = [float(row[6]) for row in evidence_rows if row[6] is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
    avg_corroboration = sum(corroborations) / len(corroborations) if corroborations else 0.33
    confidence_uncertainty = max(0.0, 1.0 - avg_confidence)
    corroboration_uncertainty = max(0.0, 1.0 - min(1.0, avg_corroboration))
    return max(0.1, min(1.0, 0.7 * confidence_uncertainty + 0.3 * corroboration_uncertainty))


def _contradiction_risk(event: Event) -> float:
    risk = 1.0 + min(1.5, 0.25 * _claim_graph_contradiction_links(event))
    if event.has_contradictions:
        risk += 0.5
    return min(3.0, risk)


def build_review_queue_item(
    *,
    event: Event,
    event_evidence: list[tuple[Any, ...]],
    feedback_actions: list[str],
) -> ReviewQueueItem:
    """Project one ranked review-queue row from an event and its evidence."""

    projected_delta = sum(abs(float(row[4])) for row in event_evidence)
    uncertainty_score = _uncertainty_score(event_evidence)
    contradiction_risk = _contradiction_risk(event)
    state = event_state_snapshot(event)
    impacts = sorted(
        (
            ReviewQueueTrendImpact(
                trend_id=row[1],
                trend_name=str(row[2]),
                signal_type=str(row[3]),
                delta_log_odds=float(row[4]),
                confidence_score=float(row[5]) if row[5] is not None else None,
            )
            for row in event_evidence
        ),
        key=lambda impact: abs(impact.delta_log_odds),
        reverse=True,
    )
    return ReviewQueueItem(
        event_id=event.id,
        summary=event.canonical_summary,
        epistemic_state=state["epistemic_state"],
        activity_state=state["activity_state"],
        lifecycle_status=event.lifecycle_status,
        last_mention_at=event.last_mention_at or event.created_at or datetime.now(tz=UTC),
        source_count=event.source_count,
        unique_source_count=event.unique_source_count,
        has_contradictions=bool(event.has_contradictions),
        contradiction_notes=event.contradiction_notes,
        evidence_count=len(event_evidence),
        projected_delta=projected_delta,
        uncertainty_score=uncertainty_score,
        contradiction_risk=contradiction_risk,
        ranking_score=uncertainty_score * projected_delta * contradiction_risk,
        feedback_count=len(feedback_actions),
        feedback_actions=feedback_actions,
        requires_human_verification=len(feedback_actions) == 0,
        trend_impacts=impacts[:3],
    )
