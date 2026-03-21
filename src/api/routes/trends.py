"""
Trends API endpoints.

CRUD operations for trend management plus config-file sync.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes._trend_forecast_contract import forecast_contract_from_definition
from src.api.routes._trend_write_contract import (
    build_validated_trend_write_payload,
)
from src.api.routes._trend_write_persistence import (
    enforce_trend_uniqueness,
    get_existing_trend_by_runtime_id,
    is_unique_integrity_error,
)
from src.api.routes._trend_write_persistence import (
    raise_payload_validation_error as raise_trend_payload_validation_error,
)
from src.api.routes.trend_api_models import (
    CalibrationBucketResponse,
    InjectHypotheticalSignalSimulationRequest,
    RemoveEventImpactSimulationRequest,
    TrendCalibrationResponse,
    TrendCreate,
    TrendOutcomeCreate,
    TrendOutcomeResponse,
    TrendResponse,
    TrendRetrospectiveResponse,
    TrendSimulationRequest,
    TrendSimulationResponse,
    TrendUpdate,
)
from src.api.routes.trend_response_models import (
    TrendConfigLoadResponse,
    TrendDefinitionVersionResponse,
    TrendEvidenceResponse,
    TrendHistoryPoint,
)
from src.api.routes.trend_route_auth import (
    AUTHORIZE_TREND_CREATE,
    AUTHORIZE_TREND_DELETE,
    AUTHORIZE_TREND_OUTCOME,
    AUTHORIZE_TREND_SYNC,
    AUTHORIZE_TREND_UPDATE,
)
from src.core.calibration import CalibrationService
from src.core.retrospective_analyzer import RetrospectiveAnalyzer
from src.core.risk import (
    calculate_probability_band,
    get_confidence_rating,
    get_risk_level,
)
from src.core.runtime_provenance import current_trend_scoring_contract
from src.core.trend_config import (
    DEFAULT_TREND_CONFIG_SYNC_DIR,
    TrendConfigSyncPathError,
    normalize_definition_payload,
    resolve_trend_config_sync_dir,
)
from src.core.trend_engine import calculate_evidence_delta, logodds_to_prob, prob_to_logodds
from src.storage.database import get_session
from src.storage.models import (
    Trend,
    TrendDefinitionVersion,
    TrendEvidence,
    TrendOutcome,
    TrendSnapshot,
)

router = APIRouter()
SYNC_FROM_CONFIG_QUERY_REJECTED_DETAIL = (
    "sync_from_config is no longer supported on GET /api/v1/trends; "
    "use POST /api/v1/trends/sync-config instead"
)
__all__ = [
    "InjectHypotheticalSignalSimulationRequest",
    "RemoveEventImpactSimulationRequest",
    "TrendCreate",
    "TrendResponse",
    "TrendUpdate",
]


def _hash_definition_payload(definition: dict[str, Any]) -> str:
    canonical = json.dumps(
        definition,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _record_definition_version_if_material_change(
    session: AsyncSession,
    *,
    trend: Trend,
    previous_definition: dict[str, Any] | None,
    actor: str | None,
    context: str | None,
    force: bool = False,
) -> bool:
    trend_id = trend.id
    if trend_id is None:
        trend_id = uuid4()
        trend.id = trend_id

    current_definition = normalize_definition_payload(
        trend.definition if isinstance(trend.definition, dict) else None
    )
    current_hash = _hash_definition_payload(current_definition)

    if not force:
        if previous_definition is None:
            msg = "previous_definition is required when force=False"
            raise ValueError(msg)
        previous_hash = _hash_definition_payload(
            normalize_definition_payload(
                previous_definition if isinstance(previous_definition, dict) else None
            )
        )
        if current_hash == previous_hash:
            return False

    session.add(
        TrendDefinitionVersion(
            trend_id=trend_id,
            definition_hash=current_hash,
            definition=current_definition,
            actor=actor,
            context=context,
        )
    )
    return True


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
    try:
        forecast_contract = forecast_contract_from_definition(
            trend.definition if isinstance(trend.definition, dict) else None
        )
    except ValueError:
        forecast_contract = None

    return TrendResponse(
        id=trend.id,
        name=trend.name,
        description=trend.description,
        definition=trend.definition,
        forecast_contract=forecast_contract,
        baseline_probability=logodds_to_prob(float(trend.baseline_log_odds)),
        current_probability=probability,
        risk_level=get_risk_level(probability).value,
        probability_band=(band_low, band_high),
        confidence=confidence,
        top_movers_7d=top_movers,
        indicators=trend.indicators,
        active_scoring_math_version=current_trend_scoring_contract()["math_version"],
        active_scoring_parameter_set=current_trend_scoring_contract()["parameter_set"],
        decay_half_life_days=trend.decay_half_life_days,
        is_active=trend.is_active,
        updated_at=trend.updated_at,
    )


def _to_evidence_response(evidence: TrendEvidence) -> TrendEvidenceResponse:
    scoring_contract = current_trend_scoring_contract()
    return TrendEvidenceResponse(
        id=evidence.id,
        trend_id=evidence.trend_id,
        event_id=evidence.event_id,
        event_claim_id=evidence.event_claim_id,
        signal_type=evidence.signal_type,
        trend_definition_hash=evidence.trend_definition_hash,
        scoring_math_version=evidence.scoring_math_version or scoring_contract["math_version"],
        scoring_parameter_set=(evidence.scoring_parameter_set or scoring_contract["parameter_set"]),
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
    config_dir: str = DEFAULT_TREND_CONFIG_SYNC_DIR,
) -> TrendConfigLoadResponse:
    """Load trends from YAML files and upsert by runtime trend identifier."""
    config_path = resolve_trend_config_sync_dir(config_dir)
    if not config_path.exists() or not config_path.is_dir():
        return TrendConfigLoadResponse(errors=[f"Config directory not found: {config_dir}"])

    files = sorted([*config_path.glob("*.yaml"), *config_path.glob("*.yml")])
    result = TrendConfigLoadResponse(loaded_files=len(files))

    for file_path in files:
        try:
            raw_config = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw_config, dict):
                raise ValueError("YAML root must be a mapping")

            write_payload = build_validated_trend_write_payload(
                name=raw_config.get("name", ""),
                description=raw_config.get("description"),
                baseline_probability=raw_config.get("baseline_probability"),
                decay_half_life_days=raw_config.get("decay_half_life_days", 30),
                indicators=raw_config.get("indicators", {}),
                definition=raw_config,
                forecast_contract=raw_config.get("forecast_contract"),
                require_forecast_contract=True,
            )
            validated_config = write_payload.trend_config
            runtime_trend_id = write_payload.runtime_trend_id

            existing_by_runtime = await get_existing_trend_by_runtime_id(
                session,
                runtime_trend_id=runtime_trend_id,
            )
            existing_by_name = await session.scalar(
                select(Trend).where(Trend.name == validated_config.name).limit(1)
            )
            if (
                existing_by_runtime is not None
                and existing_by_name is not None
                and existing_by_runtime.id != existing_by_name.id
            ):
                msg = (
                    "Config sync found conflicting trend identity rows for "
                    f"name '{validated_config.name}' and runtime id '{runtime_trend_id}'"
                )
                raise ValueError(msg)

            existing = existing_by_runtime or existing_by_name
            if existing is None:
                trend = Trend(
                    name=validated_config.name,
                    description=validated_config.description,
                    runtime_trend_id=runtime_trend_id,
                    definition=write_payload.definition,
                    baseline_log_odds=write_payload.baseline_log_odds,
                    current_log_odds=write_payload.baseline_log_odds,
                    indicators=write_payload.indicators,
                    decay_half_life_days=validated_config.decay_half_life_days,
                    is_active=True,
                )
                session.add(trend)
                await session.flush()
                await _record_definition_version_if_material_change(
                    session,
                    trend=trend,
                    previous_definition=None,
                    actor="system",
                    context=f"config_sync:{file_path.name}",
                    force=True,
                )
                result.created += 1
                continue

            previous_definition = normalize_definition_payload(
                existing.definition if isinstance(existing.definition, dict) else None
            )
            existing.name = validated_config.name
            existing.description = validated_config.description
            existing.runtime_trend_id = runtime_trend_id
            existing.definition = write_payload.definition
            existing.baseline_log_odds = write_payload.baseline_log_odds
            existing.indicators = write_payload.indicators
            existing.decay_half_life_days = validated_config.decay_half_life_days
            await _record_definition_version_if_material_change(
                session,
                trend=existing,
                previous_definition=previous_definition,
                actor="system",
                context=f"config_sync:{file_path.name}",
            )
            result.updated += 1
        except Exception as exc:
            result.errors.append(f"{file_path.name}: {exc}")

    await session.flush()
    return result


# Endpoints


@router.get("", response_model=list[TrendResponse])
async def list_trends(
    active_only: bool = True,
    sync_from_config: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[TrendResponse]:
    """List trends with current and baseline probabilities."""
    if sync_from_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=SYNC_FROM_CONFIG_QUERY_REJECTED_DETAIL,
        )

    query = select(Trend).order_by(Trend.updated_at.desc())
    if active_only:
        query = query.where(Trend.is_active.is_(True))

    trends = list((await session.scalars(query)).all())
    return [await _to_response(trend, session=session) for trend in trends]


@router.post(
    "",
    response_model=TrendResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AUTHORIZE_TREND_CREATE],
)
async def create_trend(
    trend: TrendCreate,
    session: AsyncSession = Depends(get_session),
) -> TrendResponse:
    """Create a new trend."""
    try:
        write_payload = build_validated_trend_write_payload(
            name=trend.name,
            description=trend.description,
            baseline_probability=trend.baseline_probability,
            decay_half_life_days=trend.decay_half_life_days,
            indicators=trend.indicators,
            definition=trend.definition,
            forecast_contract=trend.forecast_contract,
            require_forecast_contract=True,
        )
    except ValueError as exc:
        raise_trend_payload_validation_error(exc)
    validated_config = write_payload.trend_config

    await enforce_trend_uniqueness(
        session,
        trend_name=validated_config.name,
        runtime_trend_id=write_payload.runtime_trend_id,
    )

    current_probability = (
        trend.current_probability
        if trend.current_probability is not None
        else validated_config.baseline_probability
    )
    current_log_odds = prob_to_logodds(current_probability)

    trend_record = Trend(
        name=validated_config.name,
        description=validated_config.description,
        runtime_trend_id=write_payload.runtime_trend_id,
        definition=write_payload.definition,
        baseline_log_odds=write_payload.baseline_log_odds,
        current_log_odds=current_log_odds,
        indicators=write_payload.indicators,
        decay_half_life_days=validated_config.decay_half_life_days,
        is_active=trend.is_active,
    )
    session.add(trend_record)
    try:
        await session.flush()
    except IntegrityError as exc:
        if is_unique_integrity_error(exc, marker="runtime_trend_id"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Trend runtime id '{write_payload.runtime_trend_id}' already exists",
            ) from exc
        raise
    await _record_definition_version_if_material_change(
        session,
        trend=trend_record,
        previous_definition=None,
        actor="api",
        context="create_trend",
        force=True,
    )

    return await _to_response(trend_record, session=session)


@router.post(
    "/sync-config", response_model=TrendConfigLoadResponse, dependencies=[AUTHORIZE_TREND_SYNC]
)
async def sync_trends_from_config(
    config_dir: str = Query(default=DEFAULT_TREND_CONFIG_SYNC_DIR),
    session: AsyncSession = Depends(get_session),
) -> TrendConfigLoadResponse:
    """Load or update trends from YAML files under `config/trends/`."""
    try:
        return await load_trends_from_config(session=session, config_dir=config_dir)
    except TrendConfigSyncPathError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/{trend_id}", response_model=TrendResponse)
async def get_trend(
    trend_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> TrendResponse:
    """Get one trend by id."""
    trend = await _get_trend_or_404(session, trend_id)
    return await _to_response(trend, session=session)


@router.get(
    "/{trend_id}/definition-history",
    response_model=list[TrendDefinitionVersionResponse],
)
async def get_trend_definition_history(
    trend_id: UUID,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: AsyncSession = Depends(get_session),
) -> list[TrendDefinitionVersionResponse]:
    """List append-only definition versions for one trend (newest first)."""
    await _get_trend_or_404(session, trend_id)
    records = list(
        (
            await session.scalars(
                select(TrendDefinitionVersion)
                .where(TrendDefinitionVersion.trend_id == trend_id)
                .order_by(TrendDefinitionVersion.recorded_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return [TrendDefinitionVersionResponse.model_validate(record) for record in records]


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
    dependencies=[AUTHORIZE_TREND_OUTCOME],
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


@router.patch("/{trend_id}", response_model=TrendResponse, dependencies=[AUTHORIZE_TREND_UPDATE])
async def update_trend(
    trend_id: UUID,
    trend: TrendUpdate,
    session: AsyncSession = Depends(get_session),
) -> TrendResponse:
    """Update a trend."""
    trend_record = await _get_trend_or_404(session, trend_id)
    previous_definition = normalize_definition_payload(
        trend_record.definition if isinstance(trend_record.definition, dict) else None
    )
    updates = trend.model_dump(exclude_unset=True)
    definition_updated = any(
        key in updates for key in ("definition", "forecast_contract", "baseline_probability")
    )

    candidate_name = updates.get("name", trend_record.name)
    candidate_description = updates.get("description", trend_record.description)
    candidate_definition = updates.get("definition", trend_record.definition)
    candidate_forecast_contract = updates.get("forecast_contract")
    if ("forecast_contract" in updates and "definition" not in updates) or not definition_updated:
        candidate_definition = normalize_definition_payload(
            trend_record.definition if isinstance(trend_record.definition, dict) else None
        )
        candidate_definition.pop("forecast_contract", None)
    candidate_baseline_probability = (
        updates["baseline_probability"]
        if "baseline_probability" in updates
        else logodds_to_prob(float(trend_record.baseline_log_odds))
    )
    candidate_indicators = updates.get("indicators", trend_record.indicators)
    candidate_decay_half_life_days = updates.get(
        "decay_half_life_days",
        trend_record.decay_half_life_days,
    )

    try:
        write_payload = build_validated_trend_write_payload(
            name=candidate_name,
            description=candidate_description,
            baseline_probability=candidate_baseline_probability,
            decay_half_life_days=candidate_decay_half_life_days,
            indicators=candidate_indicators,
            definition=candidate_definition,
            forecast_contract=candidate_forecast_contract,
            require_forecast_contract=definition_updated,
        )
    except ValueError as exc:
        raise_trend_payload_validation_error(exc)
    validated_config = write_payload.trend_config

    await enforce_trend_uniqueness(
        session,
        trend_name=validated_config.name,
        runtime_trend_id=write_payload.runtime_trend_id,
        current_trend_id=trend_id,
    )

    if "name" in updates:
        trend_record.name = validated_config.name
    if "description" in updates:
        trend_record.description = validated_config.description
    if definition_updated:
        trend_record.runtime_trend_id = write_payload.runtime_trend_id
        trend_record.definition = write_payload.definition
    if "baseline_probability" in updates:
        trend_record.baseline_log_odds = write_payload.baseline_log_odds
    if "indicators" in updates:
        trend_record.indicators = write_payload.indicators
    if "decay_half_life_days" in updates:
        trend_record.decay_half_life_days = validated_config.decay_half_life_days
    if "is_active" in updates:
        trend_record.is_active = updates["is_active"]
    if "current_probability" in updates and updates["current_probability"] is not None:
        trend_record.current_log_odds = prob_to_logodds(updates["current_probability"])

    if definition_updated:
        await _record_definition_version_if_material_change(
            session,
            trend=trend_record,
            previous_definition=previous_definition,
            actor="api",
            context="update_trend",
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        if is_unique_integrity_error(exc, marker="runtime_trend_id"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Trend runtime id '{write_payload.runtime_trend_id}' already exists",
            ) from exc
        raise
    return await _to_response(trend_record, session=session)


@router.delete(
    "/{trend_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AUTHORIZE_TREND_DELETE]
)
async def delete_trend(
    trend_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deactivate a trend (soft delete)."""
    trend = await _get_trend_or_404(session, trend_id)
    trend.is_active = False
    await session.flush()
