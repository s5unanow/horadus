"""
Trends API endpoints.

CRUD operations for trend management plus config-file sync.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.calibration import CalibrationService
from src.core.retrospective_analyzer import RetrospectiveAnalyzer
from src.core.risk import (
    ConfidenceRating,
    calculate_probability_band,
    get_confidence_rating,
    get_risk_level,
)
from src.core.trend_config import TrendConfig
from src.core.trend_engine import calculate_evidence_delta, logodds_to_prob, prob_to_logodds
from src.storage.database import get_session
from src.storage.models import OutcomeType, Trend, TrendEvidence, TrendOutcome, TrendSnapshot

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class TrendCreate(BaseModel):
    """Request body for creating a trend."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "EU-Russia Military Conflict",
                "description": "Probability of direct military confrontation.",
                "definition": {"region": "Europe"},
                "baseline_probability": 0.08,
                "current_probability": 0.10,
                "indicators": {
                    "military_movement": {"direction": "escalatory", "weight": 0.04},
                    "diplomatic_talks": {"direction": "de_escalatory", "weight": 0.03},
                },
                "decay_half_life_days": 30,
                "is_active": True,
            }
        }
    )

    name: str = Field(..., min_length=1)
    description: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)
    baseline_probability: float = Field(..., ge=0, le=1)
    current_probability: float | None = Field(default=None, ge=0, le=1)
    indicators: dict[str, Any] = Field(default_factory=dict)
    decay_half_life_days: int = Field(default=30, ge=1)
    is_active: bool = True


class TrendUpdate(BaseModel):
    """Request body for updating a trend."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_probability": 0.18,
                "decay_half_life_days": 45,
                "is_active": True,
            }
        }
    )

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    definition: dict[str, Any] | None = None
    baseline_probability: float | None = Field(default=None, ge=0, le=1)
    current_probability: float | None = Field(default=None, ge=0, le=1)
    indicators: dict[str, Any] | None = None
    decay_half_life_days: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class TrendResponse(BaseModel):
    """Response body for a trend."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "name": "EU-Russia Military Conflict",
                "description": "Probability of direct military confrontation.",
                "definition": {"id": "eu-russia-military-conflict"},
                "baseline_probability": 0.08,
                "current_probability": 0.18,
                "risk_level": "guarded",
                "probability_band": [0.11, 0.25],
                "confidence": "medium",
                "top_movers_7d": [
                    "Multiple sources corroborate force-movement reports.",
                    "Diplomatic talks were suspended after border incident.",
                ],
                "indicators": {"military_movement": {"direction": "escalatory", "weight": 0.04}},
                "decay_half_life_days": 30,
                "is_active": True,
                "updated_at": "2026-02-07T19:56:00Z",
            }
        },
    )

    id: UUID
    name: str
    description: str | None
    definition: dict[str, Any]
    baseline_probability: float
    current_probability: float
    risk_level: str
    probability_band: tuple[float, float]
    confidence: ConfidenceRating
    top_movers_7d: list[str]
    indicators: dict[str, Any]
    decay_half_life_days: int
    is_active: bool
    updated_at: datetime


class TrendConfigLoadResponse(BaseModel):
    """Summary for loading trends from YAML config files."""

    loaded_files: int = 0
    created: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)


class TrendEvidenceResponse(BaseModel):
    """Response body for one evidence record."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "signal_type": "military_movement",
                "credibility_score": 0.9,
                "corroboration_factor": 0.67,
                "novelty_score": 1.0,
                "evidence_age_days": 2.4,
                "temporal_decay_factor": 0.91,
                "severity_score": 0.8,
                "confidence_score": 0.95,
                "delta_log_odds": 0.021,
                "reasoning": "Multiple corroborated force-movement reports.",
                "is_invalidated": False,
                "invalidated_at": None,
                "invalidation_feedback_id": None,
                "created_at": "2026-02-07T18:00:00Z",
            }
        },
    )

    id: UUID
    trend_id: UUID
    event_id: UUID
    signal_type: str
    credibility_score: float | None
    corroboration_factor: float | None
    novelty_score: float | None
    evidence_age_days: float | None
    temporal_decay_factor: float | None
    severity_score: float | None
    confidence_score: float | None
    delta_log_odds: float
    reasoning: str | None
    is_invalidated: bool
    invalidated_at: datetime | None
    invalidation_feedback_id: UUID | None
    created_at: datetime


class RemoveEventImpactSimulationRequest(BaseModel):
    """Simulation payload for removing historical event impact from a trend."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "remove_event_impact",
                "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "signal_type": "military_movement",
            }
        }
    )

    mode: Literal["remove_event_impact"]
    event_id: UUID
    signal_type: str | None = Field(default=None, min_length=1)


class InjectHypotheticalSignalSimulationRequest(BaseModel):
    """Simulation payload for injecting a hypothetical signal impact."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "inject_hypothetical_signal",
                "signal_type": "military_movement",
                "indicator_weight": 0.04,
                "source_credibility": 0.9,
                "corroboration_count": 3,
                "novelty_score": 1.0,
                "direction": "escalatory",
                "severity": 0.8,
                "confidence": 0.95,
            }
        }
    )

    mode: Literal["inject_hypothetical_signal"]
    signal_type: str = Field(..., min_length=1)
    indicator_weight: float = Field(..., gt=0)
    source_credibility: float = Field(..., ge=0, le=1)
    corroboration_count: int = Field(..., ge=1)
    novelty_score: float = Field(..., ge=0, le=1)
    direction: Literal["escalatory", "de_escalatory"]
    severity: float = Field(default=1.0, ge=0, le=1)
    confidence: float = Field(default=1.0, ge=0, le=1)


TrendSimulationRequest = Annotated[
    RemoveEventImpactSimulationRequest | InjectHypotheticalSignalSimulationRequest,
    Field(discriminator="mode"),
]


class TrendSimulationResponse(BaseModel):
    """Response payload for counterfactual trend simulations."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "inject_hypothetical_signal",
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "current_probability": 0.18,
                "projected_probability": 0.204,
                "delta_probability": 0.024,
                "delta_log_odds": 0.15,
                "factor_breakdown": {
                    "base_weight": 0.04,
                    "severity": 0.8,
                    "confidence": 0.95,
                    "credibility": 0.9,
                    "corroboration": 0.577,
                    "novelty": 1.0,
                    "direction_multiplier": 1.0,
                    "raw_delta": 0.0158,
                    "clamped_delta": 0.0158,
                },
            }
        }
    )

    mode: Literal["remove_event_impact", "inject_hypothetical_signal"]
    trend_id: UUID
    current_probability: float
    projected_probability: float
    delta_probability: float
    delta_log_odds: float
    factor_breakdown: dict[str, Any]


class TrendHistoryPoint(BaseModel):
    """Response body for one historical trend snapshot."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-02-07T18:00:00Z",
                "log_odds": -1.65,
                "probability": 0.161,
            }
        }
    )

    timestamp: datetime
    log_odds: float
    probability: float


class TrendOutcomeCreate(BaseModel):
    """Request body for recording a trend outcome."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "outcome": "occurred",
                "outcome_date": "2026-02-07T00:00:00Z",
                "outcome_notes": "Frontline engagements confirmed by multiple sources.",
                "outcome_evidence": {"report_ids": ["abc-123", "def-456"]},
                "recorded_by": "analyst@horadus",
            }
        }
    )

    outcome: OutcomeType
    outcome_date: datetime
    outcome_notes: str | None = None
    outcome_evidence: dict[str, Any] | None = None
    recorded_by: str | None = None


class TrendOutcomeResponse(BaseModel):
    """Response body for one recorded trend outcome."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "f4f9f95b-82f7-42f0-a628-f44ca8d50f55",
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "prediction_date": "2026-02-07T00:00:00Z",
                "predicted_probability": 0.31,
                "predicted_risk_level": "elevated",
                "probability_band_low": 0.21,
                "probability_band_high": 0.41,
                "outcome_date": "2026-02-07T00:00:00Z",
                "outcome": "occurred",
                "outcome_notes": "Confirmed military engagement.",
                "outcome_evidence": {"report_ids": ["abc-123"]},
                "brier_score": 0.4761,
                "recorded_by": "analyst@horadus",
                "created_at": "2026-02-07T00:05:00Z",
            }
        },
    )

    id: UUID
    trend_id: UUID
    prediction_date: datetime
    predicted_probability: float
    predicted_risk_level: str
    probability_band_low: float
    probability_band_high: float
    outcome_date: datetime | None
    outcome: str | None
    outcome_notes: str | None
    outcome_evidence: dict[str, Any] | None
    brier_score: float | None
    recorded_by: str | None
    created_at: datetime


class CalibrationBucketResponse(BaseModel):
    """One bucket in a calibration report."""

    bucket_start: float
    bucket_end: float
    prediction_count: int
    occurred_count: int
    actual_rate: float
    expected_rate: float
    calibration_error: float


class TrendCalibrationResponse(BaseModel):
    """Calibration report response payload."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "total_predictions": 14,
                "resolved_predictions": 10,
                "mean_brier_score": 0.18,
                "overconfident": False,
                "underconfident": False,
                "buckets": [
                    {
                        "bucket_start": 0.2,
                        "bucket_end": 0.3,
                        "prediction_count": 4,
                        "occurred_count": 1,
                        "actual_rate": 0.25,
                        "expected_rate": 0.25,
                        "calibration_error": 0.0,
                    }
                ],
            }
        }
    )

    trend_id: UUID
    total_predictions: int
    resolved_predictions: int
    mean_brier_score: float | None
    overconfident: bool
    underconfident: bool
    buckets: list[CalibrationBucketResponse]


class RetrospectiveEvent(BaseModel):
    """One pivotal event in retrospective analysis."""

    event_id: UUID
    summary: str
    categories: list[str]
    evidence_count: int
    net_delta_log_odds: float
    abs_delta_log_odds: float
    direction: Literal["up", "down", "mixed"]


class RetrospectiveSignal(BaseModel):
    """One predictive signal summary in retrospective analysis."""

    signal_type: str
    evidence_count: int
    net_delta_log_odds: float
    abs_delta_log_odds: float


class TrendRetrospectiveResponse(BaseModel):
    """Trend retrospective analysis response payload."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "trend_name": "EU-Russia Military Conflict",
                "period_start": "2026-01-08T00:00:00Z",
                "period_end": "2026-02-07T00:00:00Z",
                "pivotal_events": [
                    {
                        "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                        "summary": "Large troop repositioning near border sectors.",
                        "categories": ["military"],
                        "evidence_count": 4,
                        "net_delta_log_odds": 0.132,
                        "abs_delta_log_odds": 0.132,
                        "direction": "up",
                    }
                ],
                "category_breakdown": {"military": 3, "diplomacy": 1},
                "predictive_signals": [
                    {
                        "signal_type": "military_movement",
                        "evidence_count": 5,
                        "net_delta_log_odds": 0.201,
                        "abs_delta_log_odds": 0.201,
                    }
                ],
                "accuracy_assessment": {
                    "outcome_count": 2,
                    "resolved_outcomes": 1,
                    "scored_outcomes": 1,
                    "mean_brier_score": 0.18,
                    "resolved_rate": 0.5,
                },
                "narrative": "Military movement signals were most predictive in this window.",
                "grounding_status": "grounded",
                "grounding_violation_count": 0,
                "grounding_references": None,
            }
        }
    )

    trend_id: UUID
    trend_name: str
    period_start: datetime
    period_end: datetime
    pivotal_events: list[RetrospectiveEvent]
    category_breakdown: dict[str, int]
    predictive_signals: list[RetrospectiveSignal]
    accuracy_assessment: dict[str, int | float | None]
    narrative: str
    grounding_status: str
    grounding_violation_count: int
    grounding_references: dict[str, Any] | None


# =============================================================================
# Helpers
# =============================================================================


def _slugify_name(name: str) -> str:
    normalized = "-".join(name.lower().strip().split())
    return normalized.replace("/", "-").replace("_", "-")


def _ensure_definition_id(definition: dict[str, Any], *, trend_name: str) -> dict[str, Any]:
    updated_definition = dict(definition)
    raw_id = updated_definition.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        return updated_definition
    updated_definition["id"] = _slugify_name(trend_name)
    return updated_definition


def _sync_definition_baseline_probability(
    definition: dict[str, Any],
    *,
    baseline_log_odds: float,
) -> dict[str, Any]:
    updated_definition = dict(definition)
    updated_definition["baseline_probability"] = round(
        logodds_to_prob(float(baseline_log_odds)),
        6,
    )
    return updated_definition


async def _get_evidence_stats(
    session: AsyncSession,
    *,
    trend_id: UUID,
) -> tuple[int, float, int]:
    now = datetime.now(tz=UTC)
    since_30d = now - timedelta(days=30)

    count_stmt = select(
        func.count(TrendEvidence.id),
        func.avg(TrendEvidence.corroboration_factor),
        func.max(TrendEvidence.created_at),
    ).where(
        TrendEvidence.trend_id == trend_id,
        TrendEvidence.created_at >= since_30d,
        TrendEvidence.is_invalidated.is_(False),
    )
    count_row = (await session.execute(count_stmt)).one()
    evidence_count = int(count_row[0] or 0)
    avg_corroboration = float(count_row[1]) if count_row[1] is not None else 0.5
    most_recent = count_row[2]

    if most_recent is None:
        days_since_last = 30
    else:
        most_recent_utc = most_recent if most_recent.tzinfo else most_recent.replace(tzinfo=UTC)
        elapsed_days = (now - most_recent_utc).days
        days_since_last = max(0, elapsed_days)

    return evidence_count, avg_corroboration, days_since_last


async def _get_top_movers_7d(
    session: AsyncSession,
    *,
    trend_id: UUID,
    limit: int = 3,
) -> list[str]:
    since_7d = datetime.now(tz=UTC) - timedelta(days=7)
    query = (
        select(TrendEvidence)
        .where(TrendEvidence.trend_id == trend_id)
        .where(TrendEvidence.created_at >= since_7d)
        .where(TrendEvidence.is_invalidated.is_(False))
        .order_by(func.abs(TrendEvidence.delta_log_odds).desc())
        .limit(limit)
    )
    records = list((await session.scalars(query)).all())
    movers = [record.reasoning.strip() for record in records if record.reasoning]
    if movers:
        return movers
    return [record.signal_type for record in records[:limit]]


async def _to_response(
    trend: Trend,
    *,
    session: AsyncSession,
) -> TrendResponse:
    probability = logodds_to_prob(float(trend.current_log_odds))
    evidence_count, avg_corroboration, days_since_last = await _get_evidence_stats(
        session,
        trend_id=trend.id,
    )
    band_low, band_high = calculate_probability_band(
        probability=probability,
        evidence_count_30d=evidence_count,
        avg_corroboration=avg_corroboration,
        days_since_last_evidence=days_since_last,
    )
    confidence = get_confidence_rating(
        band_width=band_high - band_low,
        evidence_count=evidence_count,
        avg_corroboration=avg_corroboration,
    )
    top_movers = await _get_top_movers_7d(session, trend_id=trend.id)

    return TrendResponse(
        id=trend.id,
        name=trend.name,
        description=trend.description,
        definition=trend.definition,
        baseline_probability=logodds_to_prob(float(trend.baseline_log_odds)),
        current_probability=probability,
        risk_level=get_risk_level(probability).value,
        probability_band=(band_low, band_high),
        confidence=confidence,
        top_movers_7d=top_movers,
        indicators=trend.indicators,
        decay_half_life_days=trend.decay_half_life_days,
        is_active=trend.is_active,
        updated_at=trend.updated_at,
    )


def _to_evidence_response(evidence: TrendEvidence) -> TrendEvidenceResponse:
    return TrendEvidenceResponse(
        id=evidence.id,
        trend_id=evidence.trend_id,
        event_id=evidence.event_id,
        signal_type=evidence.signal_type,
        credibility_score=(
            float(evidence.credibility_score) if evidence.credibility_score is not None else None
        ),
        corroboration_factor=(
            float(evidence.corroboration_factor)
            if evidence.corroboration_factor is not None
            else None
        ),
        novelty_score=float(evidence.novelty_score) if evidence.novelty_score is not None else None,
        evidence_age_days=(
            float(evidence.evidence_age_days) if evidence.evidence_age_days is not None else None
        ),
        temporal_decay_factor=(
            float(evidence.temporal_decay_factor)
            if evidence.temporal_decay_factor is not None
            else None
        ),
        severity_score=(
            float(evidence.severity_score) if evidence.severity_score is not None else None
        ),
        confidence_score=(
            float(evidence.confidence_score) if evidence.confidence_score is not None else None
        ),
        delta_log_odds=float(evidence.delta_log_odds),
        reasoning=evidence.reasoning,
        is_invalidated=bool(evidence.is_invalidated),
        invalidated_at=evidence.invalidated_at,
        invalidation_feedback_id=evidence.invalidation_feedback_id,
        created_at=evidence.created_at,
    )


def _to_history_point(snapshot: TrendSnapshot) -> TrendHistoryPoint:
    log_odds = float(snapshot.log_odds)
    return TrendHistoryPoint(
        timestamp=snapshot.timestamp,
        log_odds=log_odds,
        probability=logodds_to_prob(log_odds),
    )


def _to_outcome_response(outcome: TrendOutcome) -> TrendOutcomeResponse:
    return TrendOutcomeResponse(
        id=outcome.id,
        trend_id=outcome.trend_id,
        prediction_date=outcome.prediction_date,
        predicted_probability=float(outcome.predicted_probability),
        predicted_risk_level=outcome.predicted_risk_level,
        probability_band_low=float(outcome.probability_band_low),
        probability_band_high=float(outcome.probability_band_high),
        outcome_date=outcome.outcome_date,
        outcome=outcome.outcome,
        outcome_notes=outcome.outcome_notes,
        outcome_evidence=outcome.outcome_evidence,
        brier_score=float(outcome.brier_score) if outcome.brier_score is not None else None,
        recorded_by=outcome.recorded_by,
        created_at=outcome.created_at,
    )


def _history_bucket_key(
    timestamp: datetime,
    interval: Literal["hourly", "daily", "weekly"],
) -> tuple[int, ...]:
    if interval == "hourly":
        return (
            timestamp.year,
            timestamp.month,
            timestamp.day,
            timestamp.hour,
        )
    if interval == "daily":
        return (timestamp.year, timestamp.month, timestamp.day)

    iso = timestamp.isocalendar()
    return (iso.year, iso.week)


def _downsample_snapshots(
    snapshots: list[TrendSnapshot],
    interval: Literal["hourly", "daily", "weekly"],
) -> list[TrendSnapshot]:
    if interval == "hourly":
        return snapshots

    bucketed: dict[tuple[int, ...], TrendSnapshot] = {}
    for snapshot in snapshots:
        bucketed[_history_bucket_key(snapshot.timestamp, interval)] = snapshot

    return list(bucketed.values())


async def _get_trend_or_404(session: AsyncSession, trend_id: UUID) -> Trend:
    trend = await session.get(Trend, trend_id)
    if trend is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trend '{trend_id}' not found",
        )
    return trend


async def load_trends_from_config(
    session: AsyncSession,
    *,
    config_dir: str = "config/trends",
) -> TrendConfigLoadResponse:
    """Load trends from YAML files and upsert by trend name."""
    config_path = Path(config_dir)
    if not config_path.exists() or not config_path.is_dir():
        return TrendConfigLoadResponse(errors=[f"Config directory not found: {config_dir}"])

    files = sorted([*config_path.glob("*.yaml"), *config_path.glob("*.yml")])
    result = TrendConfigLoadResponse(loaded_files=len(files))

    for file_path in files:
        try:
            raw_config = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw_config, dict):
                raise ValueError("YAML root must be a mapping")

            parsed_config = TrendConfig.model_validate(raw_config)
            trend_name = parsed_config.name
            baseline_log_odds = prob_to_logodds(parsed_config.baseline_probability)
            indicators = {
                signal_name: indicator.model_dump(mode="json")
                for signal_name, indicator in parsed_config.indicators.items()
            }
            definition = _ensure_definition_id(
                parsed_config.model_dump(mode="json", exclude_none=True),
                trend_name=trend_name,
            )
            definition = _sync_definition_baseline_probability(
                definition,
                baseline_log_odds=baseline_log_odds,
            )

            existing = await session.scalar(select(Trend).where(Trend.name == trend_name).limit(1))
            if existing is None:
                trend = Trend(
                    name=trend_name,
                    description=parsed_config.description,
                    definition=definition,
                    baseline_log_odds=baseline_log_odds,
                    current_log_odds=baseline_log_odds,
                    indicators=indicators,
                    decay_half_life_days=parsed_config.decay_half_life_days,
                    is_active=True,
                )
                session.add(trend)
                result.created += 1
                continue

            existing.description = parsed_config.description
            existing.definition = definition
            existing.baseline_log_odds = baseline_log_odds
            existing.indicators = indicators
            existing.decay_half_life_days = parsed_config.decay_half_life_days
            result.updated += 1
        except Exception as exc:
            result.errors.append(f"{file_path.name}: {exc}")

    await session.flush()
    return result


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[TrendResponse])
async def list_trends(
    active_only: bool = True,
    sync_from_config: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[TrendResponse]:
    """List trends with current and baseline probabilities."""
    if sync_from_config:
        await load_trends_from_config(session=session)

    query = select(Trend).order_by(Trend.updated_at.desc())
    if active_only:
        query = query.where(Trend.is_active.is_(True))

    trends = list((await session.scalars(query)).all())
    return [await _to_response(trend, session=session) for trend in trends]


@router.post("", response_model=TrendResponse, status_code=status.HTTP_201_CREATED)
async def create_trend(
    trend: TrendCreate,
    session: AsyncSession = Depends(get_session),
) -> TrendResponse:
    """Create a new trend."""
    existing = await session.scalar(select(Trend.id).where(Trend.name == trend.name).limit(1))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trend '{trend.name}' already exists",
        )

    definition = _ensure_definition_id(trend.definition, trend_name=trend.name)
    baseline_log_odds = prob_to_logodds(trend.baseline_probability)
    definition = _sync_definition_baseline_probability(
        definition,
        baseline_log_odds=baseline_log_odds,
    )
    current_probability = (
        trend.current_probability
        if trend.current_probability is not None
        else trend.baseline_probability
    )
    current_log_odds = prob_to_logodds(current_probability)

    trend_record = Trend(
        name=trend.name,
        description=trend.description,
        definition=definition,
        baseline_log_odds=baseline_log_odds,
        current_log_odds=current_log_odds,
        indicators=trend.indicators,
        decay_half_life_days=trend.decay_half_life_days,
        is_active=trend.is_active,
    )
    session.add(trend_record)
    await session.flush()

    return await _to_response(trend_record, session=session)


@router.post("/sync-config", response_model=TrendConfigLoadResponse)
async def sync_trends_from_config(
    config_dir: str = Query(default="config/trends"),
    session: AsyncSession = Depends(get_session),
) -> TrendConfigLoadResponse:
    """Load or update trends from YAML files under `config/trends/`."""
    return await load_trends_from_config(session=session, config_dir=config_dir)


@router.get("/{trend_id}", response_model=TrendResponse)
async def get_trend(
    trend_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> TrendResponse:
    """Get one trend by id."""
    trend = await _get_trend_or_404(session, trend_id)
    return await _to_response(trend, session=session)


@router.get("/{trend_id}/evidence", response_model=list[TrendEvidenceResponse])
async def list_trend_evidence(
    trend_id: UUID,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
    include_invalidated: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    session: AsyncSession = Depends(get_session),
) -> list[TrendEvidenceResponse]:
    """List evidence records for one trend, optionally filtered by date range."""
    await _get_trend_or_404(session, trend_id)

    if start_at and end_at and start_at > end_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_at must be less than or equal to end_at",
        )

    query = (
        select(TrendEvidence)
        .where(TrendEvidence.trend_id == trend_id)
        .order_by(TrendEvidence.created_at.desc())
        .limit(limit)
    )
    if start_at is not None:
        query = query.where(TrendEvidence.created_at >= start_at)
    if end_at is not None:
        query = query.where(TrendEvidence.created_at <= end_at)
    if not include_invalidated:
        query = query.where(TrendEvidence.is_invalidated.is_(False))

    evidence_records = (await session.scalars(query)).all()
    return [_to_evidence_response(record) for record in evidence_records]


@router.get("/{trend_id}/history", response_model=list[TrendHistoryPoint])
async def get_trend_history(
    trend_id: UUID,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
    interval: Annotated[Literal["hourly", "daily", "weekly"], Query()] = "hourly",
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
    session: AsyncSession = Depends(get_session),
) -> list[TrendHistoryPoint]:
    """Get historical snapshots for one trend with optional downsampling."""
    await _get_trend_or_404(session, trend_id)

    if start_at and end_at and start_at > end_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_at must be less than or equal to end_at",
        )

    query = (
        select(TrendSnapshot)
        .where(TrendSnapshot.trend_id == trend_id)
        .order_by(TrendSnapshot.timestamp.asc())
        .limit(limit)
    )
    if start_at is not None:
        query = query.where(TrendSnapshot.timestamp >= start_at)
    if end_at is not None:
        query = query.where(TrendSnapshot.timestamp <= end_at)

    snapshots = list((await session.scalars(query)).all())
    downsampled = _downsample_snapshots(snapshots=snapshots, interval=interval)
    return [_to_history_point(snapshot) for snapshot in downsampled]


@router.post("/{trend_id}/simulate", response_model=TrendSimulationResponse)
async def simulate_trend(
    trend_id: UUID,
    payload: TrendSimulationRequest,
    session: AsyncSession = Depends(get_session),
) -> TrendSimulationResponse:
    """
    Run a non-persistent trend projection from either historical removal or hypothetical injection.
    """
    trend = await _get_trend_or_404(session, trend_id)
    current_log_odds = float(trend.current_log_odds)
    current_probability = logodds_to_prob(current_log_odds)

    if payload.mode == "remove_event_impact":
        query = select(TrendEvidence).where(
            TrendEvidence.trend_id == trend_id,
            TrendEvidence.event_id == payload.event_id,
            TrendEvidence.is_invalidated.is_(False),
        )
        if payload.signal_type is not None:
            query = query.where(TrendEvidence.signal_type == payload.signal_type)

        evidence_rows = list((await session.scalars(query)).all())
        if not evidence_rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No matching trend evidence found for requested simulation.",
            )

        removed_delta = sum(float(row.delta_log_odds) for row in evidence_rows)
        delta_log_odds = -removed_delta
        factor_breakdown: dict[str, Any] = {
            "evidence_count": len(evidence_rows),
            "removed_sum_delta_log_odds": round(removed_delta, 6),
        }
        if payload.signal_type is not None:
            factor_breakdown["signal_type"] = payload.signal_type
    else:
        delta_log_odds, factors = calculate_evidence_delta(
            signal_type=payload.signal_type,
            indicator_weight=payload.indicator_weight,
            source_credibility=payload.source_credibility,
            corroboration_count=payload.corroboration_count,
            novelty_score=payload.novelty_score,
            direction=payload.direction,
            severity=payload.severity,
            confidence=payload.confidence,
        )
        factor_breakdown = factors.to_dict()

    projected_probability = logodds_to_prob(current_log_odds + delta_log_odds)
    return TrendSimulationResponse(
        mode=payload.mode,
        trend_id=trend.id,
        current_probability=current_probability,
        projected_probability=projected_probability,
        delta_probability=projected_probability - current_probability,
        delta_log_odds=delta_log_odds,
        factor_breakdown=factor_breakdown,
    )


@router.get("/{trend_id}/retrospective", response_model=TrendRetrospectiveResponse)
async def get_trend_retrospective(
    trend_id: UUID,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
) -> TrendRetrospectiveResponse:
    """
    Analyze pivotal events/signals for one trend over a selected time window.
    """
    trend = await _get_trend_or_404(session, trend_id)

    if end_date is None:
        period_end = datetime.now(tz=UTC)
    elif end_date.tzinfo is None:
        period_end = end_date.replace(tzinfo=UTC)
    else:
        period_end = end_date.astimezone(UTC)

    if start_date is None:
        period_start = period_end - timedelta(days=30)
    elif start_date.tzinfo is None:
        period_start = start_date.replace(tzinfo=UTC)
    else:
        period_start = start_date.astimezone(UTC)
    if period_start > period_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be less than or equal to end_date",
        )

    analyzer = RetrospectiveAnalyzer(session=session)
    analysis = await analyzer.analyze(
        trend=trend,
        start_date=period_start,
        end_date=period_end,
    )
    return TrendRetrospectiveResponse(**analysis)


@router.post(
    "/{trend_id}/outcomes",
    response_model=TrendOutcomeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_trend_outcome(
    trend_id: UUID,
    payload: TrendOutcomeCreate,
    session: AsyncSession = Depends(get_session),
) -> TrendOutcomeResponse:
    """
    Record a resolved trend outcome and compute Brier score for calibration.
    """
    service = CalibrationService(session)
    try:
        outcome = await service.record_outcome(
            trend_id=trend_id,
            outcome=payload.outcome,
            outcome_date=payload.outcome_date,
            notes=payload.outcome_notes,
            evidence=payload.outcome_evidence,
            recorded_by=payload.recorded_by,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return _to_outcome_response(outcome)


@router.get("/{trend_id}/calibration", response_model=TrendCalibrationResponse)
async def get_trend_calibration(
    trend_id: UUID,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
) -> TrendCalibrationResponse:
    """
    Get calibration analysis for one trend.
    """
    await _get_trend_or_404(session, trend_id)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be less than or equal to end_date",
        )

    service = CalibrationService(session)
    report = await service.get_calibration_report(
        trend_id=trend_id,
        start_date=start_date,
        end_date=end_date,
    )
    return TrendCalibrationResponse(
        trend_id=trend_id,
        total_predictions=report.total_predictions,
        resolved_predictions=report.resolved_predictions,
        mean_brier_score=report.mean_brier_score,
        overconfident=report.overconfident,
        underconfident=report.underconfident,
        buckets=[
            CalibrationBucketResponse(
                bucket_start=bucket.bucket_start,
                bucket_end=bucket.bucket_end,
                prediction_count=bucket.prediction_count,
                occurred_count=bucket.occurred_count,
                actual_rate=bucket.actual_rate,
                expected_rate=bucket.expected_rate,
                calibration_error=bucket.calibration_error,
            )
            for bucket in report.buckets
        ],
    )


@router.patch("/{trend_id}", response_model=TrendResponse)
async def update_trend(
    trend_id: UUID,
    trend: TrendUpdate,
    session: AsyncSession = Depends(get_session),
) -> TrendResponse:
    """Update a trend."""
    trend_record = await _get_trend_or_404(session, trend_id)
    updates = trend.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] is not None and updates["name"] != trend_record.name:
        existing_id = await session.scalar(
            select(Trend.id).where(Trend.name == updates["name"]).limit(1)
        )
        if existing_id is not None and existing_id != trend_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Trend '{updates['name']}' already exists",
            )

    if "definition" in updates and updates["definition"] is not None:
        updates["definition"] = _ensure_definition_id(
            updates["definition"], trend_name=updates.get("name", trend_record.name)
        )

    if "baseline_probability" in updates and updates["baseline_probability"] is not None:
        updates["baseline_log_odds"] = prob_to_logodds(updates.pop("baseline_probability"))

    if "definition" in updates or "baseline_log_odds" in updates:
        baseline_log_odds = updates.get("baseline_log_odds", float(trend_record.baseline_log_odds))
        base_definition = updates.get("definition", trend_record.definition)
        updates["definition"] = _sync_definition_baseline_probability(
            base_definition,
            baseline_log_odds=baseline_log_odds,
        )

    if "current_probability" in updates and updates["current_probability"] is not None:
        updates["current_log_odds"] = prob_to_logodds(updates.pop("current_probability"))

    for field_name, field_value in updates.items():
        setattr(trend_record, field_name, field_value)

    await session.flush()
    return await _to_response(trend_record, session=session)


@router.delete("/{trend_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trend(
    trend_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deactivate a trend (soft delete)."""
    trend = await _get_trend_or_404(session, trend_id)
    trend.is_active = False
    await session.flush()
