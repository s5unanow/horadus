"""
Trends API endpoints.

CRUD operations for trend management plus config-file sync.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.trend_engine import logodds_to_prob, prob_to_logodds
from src.storage.database import get_session
from src.storage.models import Trend, TrendEvidence

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class TrendCreate(BaseModel):
    """Request body for creating a trend."""

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

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    definition: dict[str, Any]
    baseline_probability: float
    current_probability: float
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

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trend_id: UUID
    event_id: UUID
    signal_type: str
    credibility_score: float | None
    corroboration_factor: float | None
    novelty_score: float | None
    severity_score: float | None
    confidence_score: float | None
    delta_log_odds: float
    reasoning: str | None
    created_at: datetime


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


def _to_response(trend: Trend) -> TrendResponse:
    return TrendResponse(
        id=trend.id,
        name=trend.name,
        description=trend.description,
        definition=trend.definition,
        baseline_probability=logodds_to_prob(float(trend.baseline_log_odds)),
        current_probability=logodds_to_prob(float(trend.current_log_odds)),
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
        severity_score=(
            float(evidence.severity_score) if evidence.severity_score is not None else None
        ),
        confidence_score=(
            float(evidence.confidence_score) if evidence.confidence_score is not None else None
        ),
        delta_log_odds=float(evidence.delta_log_odds),
        reasoning=evidence.reasoning,
        created_at=evidence.created_at,
    )


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

            trend_name = str(raw_config.get("name", "")).strip()
            if not trend_name:
                raise ValueError("name is required")

            baseline_probability = float(raw_config.get("baseline_probability", 0.0))
            if not 0 <= baseline_probability <= 1:
                raise ValueError("baseline_probability must be in range [0, 1]")

            indicators = raw_config.get("indicators", {})
            if not isinstance(indicators, dict):
                raise ValueError("indicators must be a mapping")

            decay_half_life_days = int(raw_config.get("decay_half_life_days", 30))
            if decay_half_life_days < 1:
                raise ValueError("decay_half_life_days must be >= 1")

            definition = _ensure_definition_id(raw_config, trend_name=trend_name)
            baseline_log_odds = prob_to_logodds(baseline_probability)

            existing = await session.scalar(select(Trend).where(Trend.name == trend_name).limit(1))
            if existing is None:
                trend = Trend(
                    name=trend_name,
                    description=raw_config.get("description"),
                    definition=definition,
                    baseline_log_odds=baseline_log_odds,
                    current_log_odds=baseline_log_odds,
                    indicators=indicators,
                    decay_half_life_days=decay_half_life_days,
                    is_active=True,
                )
                session.add(trend)
                result.created += 1
                continue

            existing.description = raw_config.get("description")
            existing.definition = definition
            existing.baseline_log_odds = baseline_log_odds
            existing.indicators = indicators
            existing.decay_half_life_days = decay_half_life_days
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

    trends = (await session.scalars(query)).all()
    return [_to_response(trend) for trend in trends]


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

    return _to_response(trend_record)


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
    return _to_response(trend)


@router.get("/{trend_id}/evidence", response_model=list[TrendEvidenceResponse])
async def list_trend_evidence(
    trend_id: UUID,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
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

    evidence_records = (await session.scalars(query)).all()
    return [_to_evidence_response(record) for record in evidence_records]


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
    if "current_probability" in updates and updates["current_probability"] is not None:
        updates["current_log_odds"] = prob_to_logodds(updates.pop("current_probability"))

    for field_name, field_value in updates.items():
        setattr(trend_record, field_name, field_value)

    await session.flush()
    return _to_response(trend_record)


@router.delete("/{trend_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trend(
    trend_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deactivate a trend (soft delete)."""
    trend = await _get_trend_or_404(session, trend_id)
    trend.is_active = False
    await session.flush()
