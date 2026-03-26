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
from src.core.trend_config import horizon_variant_payload_from_definition
from src.core.trend_state import resolve_active_definition_hash, resolve_active_scoring_contract
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
        state_version_id=getattr(trend, "active_state_version_id", None),
    )
    scoring_contract = await _load_active_trend_scoring_contract(
        session=session,
        trend_id=getattr(trend, "id", None),
        trend=trend,
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
            "definition_hash": resolve_active_definition_hash(trend),
            "active_definition_version_id": (
                str(getattr(trend, "active_definition_version_id", None))
                if getattr(trend, "active_definition_version_id", None) is not None
                else None
            ),
            "active_state_version_id": (
                str(getattr(trend, "active_state_version_id", None))
                if getattr(trend, "active_state_version_id", None) is not None
                else None
            ),
            "horizon_variant": horizon_variant_payload_from_definition(
                getattr(trend, "definition", None)
            ),
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
        "scoring": scoring_contract,
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
    state_version_id: UUID | None = None,
) -> tuple[list[str], list[str]]:
    if trend_id is None:
        return ([], [])

    query = (
        select(TrendEvidence.id, TrendEvidence.event_id)
        .where(TrendEvidence.trend_id == trend_id)
        .where(TrendEvidence.is_invalidated.is_(False))
        .order_by(TrendEvidence.created_at.asc(), TrendEvidence.id.asc())
    )
    if state_version_id is not None:
        query = query.where(TrendEvidence.state_version_id == state_version_id)
    rows = (await session.execute(query)).all()
    if isawaitable(rows):
        rows = await rows
    evidence_ids = [str(evidence_id) for evidence_id, _ in rows if evidence_id is not None]
    event_ids = sorted({str(event_id) for _, event_id in rows if event_id is not None})
    return (evidence_ids, event_ids)


async def _load_active_trend_scoring_contract(
    *,
    session: AsyncSession,
    trend_id: UUID | None,
    trend: Any | None = None,
) -> dict[str, Any]:
    if trend is not None:
        return resolve_active_scoring_contract(trend)
    if trend_id is None:
        return current_trend_scoring_contract()

    from src.storage.restatement_models import TrendRestatement

    evidence_rows = (
        await session.execute(
            select(
                TrendEvidence.scoring_math_version,
                TrendEvidence.scoring_parameter_set,
                TrendEvidence.id,
            )
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.is_invalidated.is_(False))
        )
    ).all()
    if isawaitable(evidence_rows):
        evidence_rows = await evidence_rows
    restatement_rows = (
        await session.execute(
            select(
                TrendRestatement.scoring_math_version,
                TrendRestatement.scoring_parameter_set,
                TrendRestatement.id,
            ).where(TrendRestatement.trend_id == trend_id)
        )
    ).all()
    if isawaitable(restatement_rows):
        restatement_rows = await restatement_rows

    aggregated: dict[tuple[str, str, str], int] = {}
    for math_version, parameter_set, marker in evidence_rows:
        if math_version is None or parameter_set is None:
            continue
        key = ("trend_evidence", str(math_version), str(parameter_set))
        aggregated[key] = aggregated.get(key, 0) + (int(marker) if isinstance(marker, int) else 1)
    for math_version, parameter_set, marker in restatement_rows:
        if math_version is None or parameter_set is None:
            continue
        key = ("trend_restatements", str(math_version), str(parameter_set))
        aggregated[key] = aggregated.get(key, 0) + (int(marker) if isinstance(marker, int) else 1)

    observed_rows = [
        {
            "source": source,
            "math_version": math_version,
            "parameter_set": parameter_set,
            "row_count": row_count,
        }
        for (source, math_version, parameter_set), row_count in aggregated.items()
    ]
    return _summarize_scoring_contract_rows(observed_rows)


def _summarize_scoring_contract_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return current_trend_scoring_contract()

    current_contract = current_trend_scoring_contract()
    math_versions = sorted({str(row["math_version"]) for row in rows})
    parameter_sets = sorted({str(row["parameter_set"]) for row in rows})
    payload: dict[str, Any] = {
        "math_version": math_versions[0] if len(math_versions) == 1 else "mixed",
        "parameter_set": parameter_sets[0] if len(parameter_sets) == 1 else "mixed",
        "observed_rows": sorted(
            [
                {
                    "source": str(row["source"]),
                    "math_version": str(row["math_version"]),
                    "parameter_set": str(row["parameter_set"]),
                    "row_count": int(row["row_count"]),
                }
                for row in rows
            ],
            key=lambda row: (
                row["source"],
                row["math_version"],
                row["parameter_set"],
            ),
        ),
    }
    if (
        payload["math_version"] == current_contract["math_version"]
        and payload["parameter_set"] == current_contract["parameter_set"]
    ):
        payload["promotion_check"] = current_contract["promotion_check"]
    return payload


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
