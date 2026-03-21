"""Runtime helpers for report fallback narratives and generation manifests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from inspect import isawaitable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.narrative_grounding import (
    build_grounding_references,
    evaluate_narrative_grounding,
)
from src.core.runtime_provenance import build_prompt_provenance, current_trend_scoring_contract
from src.core.trend_engine import TrendEngine
from src.storage.models import TrendEvidence


@dataclass(slots=True)
class NarrativeResult:
    narrative: str
    grounding_status: str
    grounding_violation_count: int
    grounding_references: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    provisional: bool = False


def build_fallback_narrative_result(
    *,
    trend: Any,
    report_type: str,
    statistics: dict[str, Any],
    payload: dict[str, Any],
    prompt_path: str,
    prompt_template: str,
    fallback_reason: str,
    attempted_provenance: dict[str, Any] | None = None,
    violation_threshold: int,
    numeric_tolerance: float,
) -> NarrativeResult:
    narrative = _fallback_narrative(
        trend=trend,
        report_type=report_type,
        statistics=statistics,
    )
    evaluation = evaluate_narrative_grounding(
        narrative=narrative,
        evidence_payload=payload,
        violation_threshold=violation_threshold,
        numeric_tolerance=numeric_tolerance,
    )
    return NarrativeResult(
        narrative=narrative,
        grounding_status="fallback" if evaluation.is_grounded else "flagged",
        grounding_violation_count=evaluation.violation_count,
        grounding_references=build_grounding_references(evaluation),
        provenance={
            "stage": "reporting",
            "mode": "fallback",
            "fallback_reason": fallback_reason,
            "prompt": build_prompt_provenance(
                prompt_path=prompt_path,
                prompt_template=prompt_template,
            ),
            "attempted_llm_provenance": attempted_provenance,
        },
        provisional=True,
    )


async def build_report_generation_manifest(
    *,
    session: AsyncSession,
    trend: Any,
    period_start: datetime,
    period_end: datetime,
    report_type: str,
    top_events: list[dict[str, Any]],
    narrative: NarrativeResult,
) -> dict[str, Any]:
    evidence_ids, event_ids = await _load_report_input_ids(
        session=session,
        trend_id=getattr(trend, "id", None),
        period_start=period_start,
        period_end=period_end,
    )
    live_state_evidence_ids, live_state_event_ids = await _load_active_trend_input_ids(
        session=session,
        trend_id=getattr(trend, "id", None),
    )
    return {
        "report_type": report_type,
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "trend": {
            "id": str(getattr(trend, "id", None)),
            "runtime_trend_id": getattr(trend, "runtime_trend_id", None),
            "definition_hash": TrendEngine._definition_hash(getattr(trend, "definition", {})),
        },
        "inputs": {
            "evidence_ids": evidence_ids,
            "event_ids": event_ids,
            "live_state_evidence_ids": live_state_evidence_ids,
            "live_state_event_ids": live_state_event_ids,
            "top_event_ids": [
                str(event_id)
                for event_id in (row.get("event_id") for row in top_events)
                if event_id is not None
            ],
            "counts": {
                "evidence": len(evidence_ids),
                "events": len(event_ids),
                "live_state_evidence": len(live_state_evidence_ids),
                "live_state_events": len(live_state_event_ids),
                "top_events": len(top_events),
            },
        },
        "scoring": current_trend_scoring_contract(),
        "artifact_status": {
            "provisional": narrative.provisional,
            "grounding_status": narrative.grounding_status,
        },
        "narrative_provenance": narrative.provenance,
    }


async def _load_report_input_ids(
    *,
    session: AsyncSession,
    trend_id: UUID | None,
    period_start: datetime,
    period_end: datetime,
) -> tuple[list[str], list[str]]:
    if trend_id is None:
        return ([], [])

    rows = (
        await session.execute(
            select(TrendEvidence.id, TrendEvidence.event_id)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
            .where(TrendEvidence.is_invalidated.is_(False))
            .order_by(TrendEvidence.created_at.asc(), TrendEvidence.id.asc())
        )
    ).all()
    if isawaitable(rows):
        rows = await rows
    evidence_ids = [str(evidence_id) for evidence_id, _ in rows if evidence_id is not None]
    event_ids = sorted({str(event_id) for _, event_id in rows if event_id is not None})
    return (evidence_ids, event_ids)


async def _load_active_trend_input_ids(
    *,
    session: AsyncSession,
    trend_id: UUID | None,
) -> tuple[list[str], list[str]]:
    if trend_id is None:
        return ([], [])

    rows = (
        await session.execute(
            select(TrendEvidence.id, TrendEvidence.event_id)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.is_invalidated.is_(False))
            .order_by(TrendEvidence.created_at.asc(), TrendEvidence.id.asc())
        )
    ).all()
    if isawaitable(rows):
        rows = await rows
    evidence_ids = [str(evidence_id) for evidence_id, _ in rows if evidence_id is not None]
    event_ids = sorted({str(event_id) for _, event_id in rows if event_id is not None})
    return (evidence_ids, event_ids)


def _fallback_narrative(
    *,
    trend: Any,
    report_type: str,
    statistics: dict[str, Any],
) -> str:
    contradiction_summary = ""
    confidence_modifier = ""
    contradiction_stats = statistics.get("contradiction_analytics")
    unresolved_events_count = 0
    if isinstance(contradiction_stats, dict):
        contradicted_events_count = int(contradiction_stats.get("contradicted_events_count", 0))
        resolved_events_count = int(contradiction_stats.get("resolved_events_count", 0))
        unresolved_events_count = int(contradiction_stats.get("unresolved_events_count", 0))
        if contradicted_events_count > 0:
            contradiction_summary = (
                f" Contradiction review tracked {contradicted_events_count} events "
                f"({resolved_events_count} resolved, {unresolved_events_count} unresolved)."
            )
            if unresolved_events_count > 0:
                confidence_modifier = " unresolved contradictions"

    confidence = _confidence_label(
        int(
            statistics.get(
                "evidence_count_monthly" if report_type == "monthly" else "evidence_count_weekly",
                0,
            )
        )
    )
    direction = str(statistics.get("direction", "stable"))
    current_probability = float(statistics.get("current_probability", 0.0))
    trend_name = getattr(trend, "name", "Unknown trend")

    if report_type == "monthly":
        monthly_change = float(statistics.get("monthly_change", 0.0))
        evidence_count = int(statistics.get("evidence_count_monthly", 0))
        return (
            f"{trend_name} is currently at {current_probability:.1%} with a monthly change of "
            f"{monthly_change:+.1%}. Direction over 30 days is {direction}, with "
            f"{evidence_count} evidence updates. Confidence is {confidence} based on available "
            f"coverage{confidence_modifier}.{contradiction_summary}"
        )

    weekly_change = float(statistics.get("weekly_change", 0.0))
    evidence_count = int(statistics.get("evidence_count_weekly", 0))
    return (
        f"{trend_name} is currently at {current_probability:.1%} with a weekly change of "
        f"{weekly_change:+.1%}. Direction is {direction}, based on {evidence_count} "
        f"evidence updates in the reporting window. Confidence is {confidence} based on "
        f"current evidence volume{confidence_modifier}.{contradiction_summary}"
    )


def _confidence_label(evidence_count: int) -> str:
    if evidence_count >= 20:
        return "high"
    if evidence_count >= 8:
        return "moderate"
    return "limited"
