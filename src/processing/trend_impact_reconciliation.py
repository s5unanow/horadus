"""Helpers for reconciling active trend evidence with current Tier-2 impacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.trend_config import index_trends_by_runtime_id, trend_runtime_id_for_record
from src.core.trend_engine import EvidenceFactors, TrendEngine, calculate_evidence_delta
from src.core.trend_restatement import apply_compensating_restatement
from src.processing import trend_impact_reconciliation_lineage as reconciliation_lineage
from src.processing.event_claims import FALLBACK_EVENT_CLAIM_KEY, sync_event_claims
from src.processing.trend_evidence_matching import _evidence_matches
from src.storage.models import Event, EventClaim, TaxonomyGapReason, Trend, TrendEvidence

logger = structlog.get_logger(__name__)
TREND_IMPACT_RECONCILIATION_KEY = reconciliation_lineage.TREND_IMPACT_RECONCILIATION_KEY
_append_reconciliation_history = reconciliation_lineage._append_reconciliation_history
_lineage_entry = reconciliation_lineage._lineage_entry
_taxonomy_gap_details = reconciliation_lineage._taxonomy_gap_details


@dataclass(frozen=True)
class ParsedTrendImpact:
    """Validated Tier-2 impact payload."""

    trend_id: str
    signal_type: str
    direction: str
    severity: float
    confidence: float
    rationale: str | None
    event_claim_key: str | None = None


@dataclass(frozen=True)
class DesiredTrendEvidence:
    """Normalized desired evidence state for one active trend impact."""

    trend: Trend
    impact: ParsedTrendImpact
    event_claim: EventClaim
    delta: float
    factors: EvidenceFactors
    reasoning: str

    @property
    def key(self) -> tuple[UUID, UUID, str]:
        trend_id = self.trend.id
        if trend_id is None:
            msg = "Trend must have an id before reconciling impacts"
            raise ValueError(msg)
        event_claim_id = self.event_claim.id
        if event_claim_id is None:
            msg = "Event claim must have an id before reconciling impacts"
            raise ValueError(msg)
        return (trend_id, event_claim_id, self.impact.signal_type)


def parse_trend_impact(payload: Any) -> ParsedTrendImpact | None:
    """Return a normalized impact payload or None when malformed."""
    if not isinstance(payload, dict):
        return None

    trend_id = payload.get("trend_id")
    signal_type = payload.get("signal_type")
    direction = payload.get("direction")
    if not isinstance(trend_id, str) or not trend_id.strip():
        return None
    if not isinstance(signal_type, str) or not signal_type.strip():
        return None
    if direction not in ("escalatory", "de_escalatory"):
        return None

    try:
        severity = float(payload.get("severity", 1.0))
        confidence = float(payload.get("confidence", 1.0))
    except (TypeError, ValueError):
        return None

    rationale = payload.get("rationale")
    rationale_text = rationale.strip() if isinstance(rationale, str) and rationale.strip() else None
    event_claim_key = payload.get("event_claim_key")
    claim_key_text = (
        event_claim_key.strip()
        if isinstance(event_claim_key, str) and event_claim_key.strip()
        else None
    )
    return ParsedTrendImpact(
        trend_id=trend_id.strip(),
        signal_type=signal_type.strip(),
        direction=direction,
        severity=max(0.0, min(1.0, severity)),
        confidence=max(0.0, min(1.0, confidence)),
        rationale=rationale_text,
        event_claim_key=claim_key_text,
    )


def impact_reasoning(impact: ParsedTrendImpact) -> str:
    """Return the stored reasoning for an impact."""
    if impact.rationale:
        return impact.rationale
    return f"Tier 2 classified {impact.signal_type} as {impact.direction}"


def resolve_indicator_weight(*, trend: Trend, signal_type: str) -> float | None:
    """Resolve the configured indicator weight for a trend/signal pair."""
    indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
    indicator_config = indicators.get(signal_type)
    if not isinstance(indicator_config, dict):
        return None

    raw_weight = indicator_config.get("weight")
    if raw_weight is None or not isinstance(raw_weight, str | int | float):
        return None
    try:
        weight = float(raw_weight)
    except (TypeError, ValueError):
        return None
    if weight <= 0:
        return None
    return weight


def resolve_indicator_decay_half_life(*, trend: Trend, signal_type: str) -> float | None:
    """Resolve indicator-specific decay, falling back to the trend value."""
    indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
    indicator_config = indicators.get(signal_type)
    if isinstance(indicator_config, dict):
        raw_indicator_half_life = indicator_config.get("decay_half_life_days")
        if isinstance(raw_indicator_half_life, str | int | float):
            try:
                parsed_indicator_half_life = float(raw_indicator_half_life)
            except (TypeError, ValueError):
                parsed_indicator_half_life = 0.0
            if parsed_indicator_half_life > 0:
                return parsed_indicator_half_life

    raw_trend_half_life = getattr(trend, "decay_half_life_days", None)
    if not isinstance(raw_trend_half_life, str | int | float):
        return None
    try:
        parsed_trend_half_life = float(raw_trend_half_life)
    except (TypeError, ValueError):
        return None
    if parsed_trend_half_life <= 0:
        return None
    return parsed_trend_half_life


def event_age_days(event: Event) -> float:
    """Return event age in days for deterministic evidence scoring."""
    reference_time = event.extracted_when or event.last_mention_at or event.first_seen_at
    if reference_time is None:
        return 0.0
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)
    else:
        reference_time = reference_time.astimezone(UTC)
    return max(0.0, (datetime.now(tz=UTC) - reference_time).total_seconds() / 86400.0)


async def reconcile_event_trend_impacts(
    *,
    session: AsyncSession,
    trend_engine: TrendEngine,
    event: Event,
    trends: list[Trend],
    load_event_source_credibility: Any,
    load_corroboration_score: Any,
    load_novelty_score: Any,
    capture_taxonomy_gap: Any,
) -> tuple[int, int]:
    """Reconcile active evidence rows to the event's current Tier-2 impacts."""
    if event.id is None:
        raise ValueError("Event must have an id before applying trend impacts")

    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    impacts_payload = claims.get("trend_impacts", [])
    if not isinstance(impacts_payload, list):
        return (0, 0)

    active_evidence = await _load_active_event_evidence(session=session, event_id=event.id)
    claim_by_key = await sync_event_claims(session=session, event=event)
    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    impacts_payload = claims.get("trend_impacts", [])
    if not isinstance(impacts_payload, list):
        return (0, 0)
    (
        desired_by_key,
        impacts_seen,
        safe_to_remove_absent_keys,
        trend_by_uuid,
    ) = await _build_desired_evidence(
        event=event,
        trends=trends,
        impacts_payload=impacts_payload,
        claim_by_key=claim_by_key,
        load_event_source_credibility=load_event_source_credibility,
        load_corroboration_score=load_corroboration_score,
        load_novelty_score=load_novelty_score,
        capture_taxonomy_gap=capture_taxonomy_gap,
    )
    active_by_key = {
        (row.trend_id, row.event_claim_id, row.signal_type): row for row in active_evidence
    }
    invalidated_at = datetime.now(tz=UTC)
    updates_applied, lineage_entries = await _reconcile_desired_evidence(
        session=session,
        trend_engine=trend_engine,
        event_id=event.id,
        desired_by_key=desired_by_key,
        active_by_key=active_by_key,
        trend_by_uuid=trend_by_uuid,
        invalidated_at=invalidated_at,
    )
    if safe_to_remove_absent_keys:
        removed_updates, removed_lineage = await _invalidate_absent_evidence(
            session=session,
            trend_engine=trend_engine,
            active_by_key=active_by_key,
            trend_by_uuid=trend_by_uuid,
            invalidated_at=invalidated_at,
        )
        updates_applied += removed_updates
        lineage_entries.extend(removed_lineage)
    if lineage_entries:
        reconciliation_lineage._append_reconciliation_history(
            event=event,
            invalidated_at=invalidated_at,
            lineage_entries=lineage_entries,
        )
    return (impacts_seen, updates_applied)


async def _build_desired_evidence(
    *,
    event: Event,
    trends: list[Trend],
    impacts_payload: list[Any],
    claim_by_key: dict[str, EventClaim],
    load_event_source_credibility: Any,
    load_corroboration_score: Any,
    load_novelty_score: Any,
    capture_taxonomy_gap: Any,
) -> tuple[dict[tuple[UUID, UUID, str], DesiredTrendEvidence], int, bool, dict[UUID, Trend]]:
    trend_by_runtime_id = index_trends_by_runtime_id(trends)
    trend_by_uuid = {trend.id: trend for trend in trends if trend.id is not None}
    desired_by_key: dict[tuple[UUID, UUID, str], DesiredTrendEvidence] = {}
    impacts_seen = 0
    safe_to_remove_absent_keys = True
    source_credibility: float | None = None
    corroboration_score: float | None = None
    evidence_days = event_age_days(event)

    for payload in impacts_payload:
        impact = parse_trend_impact(payload)
        if impact is None:
            safe_to_remove_absent_keys = False
            logger.warning("Skipping malformed trend impact payload", event_id=str(event.id))
            continue
        impacts_seen += 1
        desired, source_credibility, corroboration_score = await _build_desired_impact(
            event=event,
            impact=impact,
            trend_by_runtime_id=trend_by_runtime_id,
            claim_by_key=claim_by_key,
            load_event_source_credibility=load_event_source_credibility,
            load_corroboration_score=load_corroboration_score,
            load_novelty_score=load_novelty_score,
            capture_taxonomy_gap=capture_taxonomy_gap,
            source_credibility=source_credibility,
            corroboration_score=corroboration_score,
            evidence_days=evidence_days,
        )
        if desired is None:
            safe_to_remove_absent_keys = False
            continue
        if desired.key in desired_by_key:
            safe_to_remove_absent_keys = False
            logger.warning(
                "Skipping duplicate trend impact key from Tier-2 payload",
                event_id=str(event.id),
                trend_id=impact.trend_id,
                signal_type=impact.signal_type,
            )
            continue
        desired_by_key[desired.key] = desired
    return (desired_by_key, impacts_seen, safe_to_remove_absent_keys, trend_by_uuid)


async def _build_desired_impact(
    *,
    event: Event,
    impact: ParsedTrendImpact,
    trend_by_runtime_id: dict[str, Trend],
    claim_by_key: dict[str, EventClaim],
    load_event_source_credibility: Any,
    load_corroboration_score: Any,
    load_novelty_score: Any,
    capture_taxonomy_gap: Any,
    source_credibility: float | None,
    corroboration_score: float | None,
    evidence_days: float,
) -> tuple[DesiredTrendEvidence | None, float | None, float | None]:
    trend = trend_by_runtime_id.get(impact.trend_id)
    if trend is None or trend.id is None:
        await _handle_missing_trend(
            event=event,
            impact=impact,
            capture_taxonomy_gap=capture_taxonomy_gap,
            trend=trend,
        )
        return (None, source_credibility, corroboration_score)
    indicator_weight = resolve_indicator_weight(trend=trend, signal_type=impact.signal_type)
    if indicator_weight is None:
        await _handle_missing_indicator(
            event=event,
            impact=impact,
            trend=trend,
            capture_taxonomy_gap=capture_taxonomy_gap,
        )
        return (None, source_credibility, corroboration_score)
    event_claim = _event_claim_for_impact(impact=impact, claim_by_key=claim_by_key)
    source_credibility = source_credibility or await load_event_source_credibility(event)
    corroboration_score = corroboration_score or await load_corroboration_score(event)
    novelty_score = await load_novelty_score(
        trend_id=trend.id,
        signal_type=impact.signal_type,
        event_id=event.id,
    )
    delta, factors = calculate_evidence_delta(
        signal_type=impact.signal_type,
        indicator_weight=indicator_weight,
        source_credibility=source_credibility,
        corroboration_count=corroboration_score,
        novelty_score=novelty_score,
        direction=impact.direction,
        severity=impact.severity,
        confidence=impact.confidence,
        evidence_age_days=evidence_days,
        indicator_decay_half_life_days=resolve_indicator_decay_half_life(
            trend=trend,
            signal_type=impact.signal_type,
        ),
    )
    return (
        DesiredTrendEvidence(
            trend=trend,
            impact=impact,
            event_claim=event_claim,
            delta=delta,
            factors=factors,
            reasoning=impact_reasoning(impact),
        ),
        source_credibility,
        corroboration_score,
    )


def _event_claim_for_impact(
    *,
    impact: ParsedTrendImpact,
    claim_by_key: dict[str, EventClaim],
) -> EventClaim:
    claim_key = impact.event_claim_key or FALLBACK_EVENT_CLAIM_KEY
    event_claim = claim_by_key.get(claim_key)
    if event_claim is None:
        event_claim = claim_by_key[FALLBACK_EVENT_CLAIM_KEY]
    return event_claim


async def _reconcile_desired_evidence(
    *,
    session: AsyncSession,
    trend_engine: TrendEngine,
    event_id: UUID,
    desired_by_key: dict[tuple[UUID, UUID, str], DesiredTrendEvidence],
    active_by_key: dict[tuple[UUID, UUID, str], TrendEvidence],
    trend_by_uuid: dict[UUID, Trend],
    invalidated_at: datetime,
) -> tuple[int, list[dict[str, Any]]]:
    updates_applied = 0
    lineage_entries: list[dict[str, Any]] = []
    for desired in desired_by_key.values():
        existing = active_by_key.pop(desired.key, None)
        desired_hash = TrendEngine._definition_hash(desired.trend.definition)
        if existing is not None and _evidence_matches(existing, desired, desired_hash=desired_hash):
            continue
        existing_delta: float | None = 0.0
        if existing is not None:
            existing_delta = await _invalidate_existing_match(
                session=session,
                trend_engine=trend_engine,
                evidence=existing,
                trend_by_uuid=trend_by_uuid,
                invalidated_at=invalidated_at,
            )
            if existing_delta is not None:
                lineage_entries.append(
                    reconciliation_lineage._lineage_entry(
                        evidence=existing,
                        trend_runtime_id=trend_runtime_id_for_record(desired.trend),
                        invalidated_at=invalidated_at,
                        replacement=desired,
                        change_type="replaced",
                    )
                )
        update = await trend_engine.apply_evidence(
            trend=desired.trend,
            delta=desired.delta,
            event_id=event_id,
            event_claim_id=desired.event_claim.id,
            signal_type=desired.impact.signal_type,
            factors=desired.factors,
            reasoning=desired.reasoning,
        )
        if (existing_delta is not None and abs(existing_delta) > 0.0) or abs(
            update.delta_applied
        ) > 0.0:
            updates_applied += 1
    return (updates_applied, lineage_entries)


async def _invalidate_absent_evidence(
    *,
    session: AsyncSession,
    trend_engine: TrendEngine,
    active_by_key: dict[tuple[UUID, UUID, str], TrendEvidence],
    trend_by_uuid: dict[UUID, Trend],
    invalidated_at: datetime,
) -> tuple[int, list[dict[str, Any]]]:
    updates_applied = 0
    lineage_entries: list[dict[str, Any]] = []
    for existing in active_by_key.values():
        existing_trend = await _trend_for_evidence(
            session=session,
            evidence=existing,
            trend_by_uuid=trend_by_uuid,
        )
        existing_delta = await _invalidate_active_evidence(
            session=session,
            trend_engine=trend_engine,
            evidence=existing,
            trend=existing_trend,
            invalidated_at=invalidated_at,
        )
        if existing_delta is None:
            continue
        lineage_entries.append(
            reconciliation_lineage._lineage_entry(
                evidence=existing,
                trend_runtime_id=(
                    trend_runtime_id_for_record(existing_trend)
                    if existing_trend is not None
                    else str(existing.trend_id)
                ),
                invalidated_at=invalidated_at,
                replacement=None,
                change_type="removed",
            )
        )
        if abs(existing_delta) > 0.0:
            updates_applied += 1
    return (updates_applied, lineage_entries)


async def _handle_missing_trend(
    *,
    event: Event,
    impact: ParsedTrendImpact,
    capture_taxonomy_gap: Any,
    trend: Trend | None,
) -> None:
    if trend is None:
        await capture_taxonomy_gap(
            event_id=event.id,
            trend_id=impact.trend_id,
            signal_type=impact.signal_type,
            reason=TaxonomyGapReason.UNKNOWN_TREND_ID,
            details=reconciliation_lineage._taxonomy_gap_details(impact),
        )
        logger.warning(
            "Skipping unknown trend impact",
            event_id=str(event.id),
            trend_id=impact.trend_id,
        )
        return
    logger.warning(
        "Skipping trend impact because trend id is missing",
        event_id=str(event.id),
        trend_name=trend.name,
        signal_type=impact.signal_type,
    )


async def _handle_missing_indicator(
    *,
    event: Event,
    impact: ParsedTrendImpact,
    trend: Trend,
    capture_taxonomy_gap: Any,
) -> None:
    await capture_taxonomy_gap(
        event_id=event.id,
        trend_id=trend_runtime_id_for_record(trend),
        signal_type=impact.signal_type,
        reason=TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE,
        details={
            "trend_uuid": str(trend.id),
            **reconciliation_lineage._taxonomy_gap_details(impact),
        },
    )
    logger.warning(
        "Skipping trend impact with unknown indicator weight",
        event_id=str(event.id),
        trend_id=str(trend.id),
        signal_type=impact.signal_type,
    )


async def _invalidate_existing_match(
    *,
    session: AsyncSession,
    trend_engine: TrendEngine,
    evidence: TrendEvidence,
    trend_by_uuid: dict[UUID, Trend],
    invalidated_at: datetime,
) -> float | None:
    existing_trend = await _trend_for_evidence(
        session=session,
        evidence=evidence,
        trend_by_uuid=trend_by_uuid,
    )
    return await _invalidate_active_evidence(
        session=session,
        trend_engine=trend_engine,
        evidence=evidence,
        trend=existing_trend,
        invalidated_at=invalidated_at,
    )


async def _trend_for_evidence(
    *,
    session: AsyncSession,
    evidence: TrendEvidence,
    trend_by_uuid: dict[UUID, Trend],
) -> Trend | None:
    existing_trend = trend_by_uuid.get(evidence.trend_id)
    if existing_trend is None:
        existing_trend = await session.get(Trend, evidence.trend_id)
        if existing_trend is not None and existing_trend.id is not None:
            trend_by_uuid[existing_trend.id] = existing_trend
    return existing_trend


async def _load_active_event_evidence(
    *,
    session: AsyncSession,
    event_id: UUID,
) -> list[TrendEvidence]:
    result = await session.scalars(
        select(TrendEvidence)
        .where(TrendEvidence.event_id == event_id)
        .where(TrendEvidence.is_invalidated.is_(False))
        .order_by(TrendEvidence.created_at.asc())
    )
    rows = result.all()
    if isawaitable(rows):
        rows = await rows
    return list(rows)


async def _invalidate_active_evidence(
    *,
    session: AsyncSession,
    trend_engine: TrendEngine,
    evidence: TrendEvidence,
    trend: Trend | None,
    invalidated_at: datetime,
) -> float | None:
    if trend is None or trend.id is None:
        raise ValueError(f"Trend {evidence.trend_id} not found while reconciling active evidence")
    if evidence.id is None:
        raise ValueError("Evidence must have an id before reconciliation invalidation")

    claimed_invalidation = await _claim_evidence_invalidation(
        session=session,
        evidence=evidence,
        invalidated_at=invalidated_at,
    )
    if not claimed_invalidation:
        return None

    delta_to_reverse = float(evidence.delta_log_odds)
    await apply_compensating_restatement(
        trend_engine=trend_engine,
        trend=trend,
        compensation_delta_log_odds=-delta_to_reverse,
        restatement_kind="reclassification",
        source="tier2_reconciliation",
        recorded_at=invalidated_at,
        trend_evidence=evidence,
        original_evidence_delta_log_odds=delta_to_reverse,
        details={"reason": "tier2_reclassification"},
    )

    return delta_to_reverse


async def _claim_evidence_invalidation(
    *,
    session: AsyncSession,
    evidence: TrendEvidence,
    invalidated_at: datetime,
) -> bool:
    stmt = (
        update(TrendEvidence)
        .where(TrendEvidence.id == evidence.id)
        .where(TrendEvidence.is_invalidated.is_(False))
        .values(is_invalidated=True, invalidated_at=invalidated_at)
        .returning(TrendEvidence.id)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    claimed_id = result.scalar_one_or_none()
    if isawaitable(claimed_id):
        claimed_id = await claimed_id
    if claimed_id is None:
        return False
    evidence.is_invalidated = True
    evidence.invalidated_at = invalidated_at
    return True
