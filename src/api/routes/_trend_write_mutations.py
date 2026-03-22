"""Shared mutation helpers for privileged trend writes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes._trend_write_contract import build_validated_trend_write_payload
from src.api.routes._trend_write_persistence import (
    enforce_trend_uniqueness,
    is_unique_integrity_error,
    raise_payload_validation_error,
)
from src.core.trend_config import normalize_definition_payload
from src.core.trend_engine import logodds_to_prob, prob_to_logodds
from src.core.trend_state import activate_trend_state, ensure_definition_version
from src.storage.models import Trend
from src.storage.trend_state_models import TrendDefinitionVersion

if TYPE_CHECKING:
    from src.api.routes.trend_api_models import TrendCreate, TrendUpdate


@dataclass(slots=True)
class TrendMutationResult:
    """Useful linkage ids returned after a trend mutation succeeds."""

    trend: Trend
    runtime_trend_id: str
    definition_version_id: UUID | None
    state_version_id: UUID | None


def _hash_definition_payload(definition: dict[str, Any]) -> str:
    canonical = json.dumps(
        definition,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def requires_state_activation(updates: dict[str, Any]) -> bool:
    """Return whether the update touches state-versioned live fields."""

    return any(
        key in updates
        for key in (
            "definition",
            "baseline_probability",
            "indicators",
            "decay_half_life_days",
        )
    )


def _live_state_definition_basis(definition: Any) -> dict[str, Any]:
    normalized = normalize_definition_payload(definition if isinstance(definition, dict) else None)
    normalized.pop("forecast_contract", None)
    return normalized


async def record_definition_version_if_material_change(
    session: AsyncSession,
    *,
    trend: Trend,
    previous_definition: dict[str, Any] | None,
    actor: str | None,
    context: str | None,
    force: bool = False,
) -> bool:
    """Append a new definition-version row when the normalized definition changed."""

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


async def create_trend_mutation(
    *,
    session: AsyncSession,
    payload: TrendCreate,
) -> TrendMutationResult:
    """Persist a new trend plus the definition/state lineage it requires."""

    try:
        write_payload = build_validated_trend_write_payload(
            name=payload.name,
            description=payload.description,
            baseline_probability=payload.baseline_probability,
            decay_half_life_days=payload.decay_half_life_days,
            indicators=payload.indicators,
            definition=payload.definition,
            forecast_contract=payload.forecast_contract,
            require_forecast_contract=True,
        )
    except ValueError as exc:
        raise_payload_validation_error(exc)
    validated_config = write_payload.trend_config

    await enforce_trend_uniqueness(
        session,
        trend_name=validated_config.name,
        runtime_trend_id=write_payload.runtime_trend_id,
    )

    current_probability = (
        payload.current_probability
        if payload.current_probability is not None
        else validated_config.baseline_probability
    )
    trend_record = Trend(
        name=validated_config.name,
        description=validated_config.description,
        runtime_trend_id=write_payload.runtime_trend_id,
        definition=write_payload.definition,
        baseline_log_odds=write_payload.baseline_log_odds,
        current_log_odds=prob_to_logodds(current_probability),
        indicators=write_payload.indicators,
        decay_half_life_days=validated_config.decay_half_life_days,
        is_active=payload.is_active,
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
    await record_definition_version_if_material_change(
        session,
        trend=trend_record,
        previous_definition=None,
        actor="api",
        context="create_trend",
        force=True,
    )
    definition_version = await ensure_definition_version(
        session=session,
        trend=trend_record,
        actor="api",
        context="create_trend",
    )
    await activate_trend_state(
        session=session,
        trend=trend_record,
        activation_kind="create",
        actor="api",
        context="create_trend",
        definition_version=definition_version,
    )
    return TrendMutationResult(
        trend=trend_record,
        runtime_trend_id=write_payload.runtime_trend_id,
        definition_version_id=definition_version.id,
        state_version_id=trend_record.active_state_version_id,
    )


def _state_contract_changed(
    *,
    updates: dict[str, Any],
    trend: Trend,
    candidate_definition: dict[str, Any] | Any,
    previous_definition: dict[str, Any],
    candidate_baseline_probability: float,
    candidate_indicators: dict[str, Any] | Any,
    candidate_decay_half_life_days: int,
) -> bool:
    if not requires_state_activation(updates):
        return False
    return (
        _live_state_definition_basis(candidate_definition)
        != _live_state_definition_basis(previous_definition)
        or candidate_baseline_probability != logodds_to_prob(float(trend.baseline_log_odds))
        or candidate_indicators != trend.indicators
        or candidate_decay_half_life_days != trend.decay_half_life_days
    )


async def update_trend_mutation(
    *,
    session: AsyncSession,
    trend_id: UUID,
    trend: Trend,
    payload: TrendUpdate,
) -> TrendMutationResult:
    """Apply a trend update plus any required versioned-state activation."""

    previous_definition = normalize_definition_payload(
        trend.definition if isinstance(trend.definition, dict) else None
    )
    updates = payload.model_dump(exclude_unset=True)
    activation_mode = updates.pop("activation_mode", None)
    activation_notes = updates.pop("activation_notes", None)
    definition_updated = any(
        key in updates for key in ("definition", "forecast_contract", "baseline_probability")
    )
    candidate_name = updates.get("name", trend.name)
    candidate_description = updates.get("description", trend.description)
    candidate_definition = updates.get("definition", trend.definition)
    candidate_forecast_contract = updates.get("forecast_contract")
    if ("forecast_contract" in updates and "definition" not in updates) or not definition_updated:
        candidate_definition = normalize_definition_payload(
            trend.definition if isinstance(trend.definition, dict) else None
        )
        candidate_definition.pop("forecast_contract", None)
    candidate_baseline_probability = (
        updates["baseline_probability"]
        if "baseline_probability" in updates
        else logodds_to_prob(float(trend.baseline_log_odds))
    )
    candidate_indicators = updates.get("indicators", trend.indicators)
    candidate_decay_half_life_days = updates.get(
        "decay_half_life_days",
        trend.decay_half_life_days,
    )
    if (
        _state_contract_changed(
            updates=updates,
            trend=trend,
            candidate_definition=candidate_definition,
            previous_definition=previous_definition,
            candidate_baseline_probability=candidate_baseline_probability,
            candidate_indicators=candidate_indicators,
            candidate_decay_half_life_days=candidate_decay_half_life_days,
        )
        and activation_mode is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Material live-state changes require activation_mode "
                "('rebase', 'replay', or 'new_line')."
            ),
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
        raise_payload_validation_error(exc)
    validated_config = write_payload.trend_config
    await enforce_trend_uniqueness(
        session,
        trend_name=validated_config.name,
        runtime_trend_id=write_payload.runtime_trend_id,
        current_trend_id=trend_id,
    )

    if "name" in updates:
        trend.name = validated_config.name
    if "description" in updates:
        trend.description = validated_config.description
    if definition_updated:
        trend.runtime_trend_id = write_payload.runtime_trend_id
        trend.definition = write_payload.definition
    if "baseline_probability" in updates:
        trend.baseline_log_odds = write_payload.baseline_log_odds
    if "indicators" in updates:
        trend.indicators = write_payload.indicators
    if "decay_half_life_days" in updates:
        trend.decay_half_life_days = validated_config.decay_half_life_days
    if "is_active" in updates:
        trend.is_active = updates["is_active"]
    if "current_probability" in updates and updates["current_probability"] is not None:
        trend.current_log_odds = prob_to_logodds(updates["current_probability"])

    if definition_updated:
        await record_definition_version_if_material_change(
            session,
            trend=trend,
            previous_definition=previous_definition,
            actor="api",
            context="update_trend",
        )
    definition_version_id = trend.active_definition_version_id
    if _state_contract_changed(
        updates=updates,
        trend=trend,
        candidate_definition=candidate_definition,
        previous_definition=previous_definition,
        candidate_baseline_probability=candidate_baseline_probability,
        candidate_indicators=candidate_indicators,
        candidate_decay_half_life_days=candidate_decay_half_life_days,
    ):
        assert activation_mode is not None
        definition_version = await ensure_definition_version(
            session=session,
            trend=trend,
            actor="api",
            context="update_trend",
        )
        definition_version_id = definition_version.id
        await activate_trend_state(
            session=session,
            trend=trend,
            activation_kind=activation_mode,
            actor="api",
            context="update_trend",
            definition_version=definition_version,
            details={"notes": activation_notes} if activation_notes else None,
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
    return TrendMutationResult(
        trend=trend,
        runtime_trend_id=write_payload.runtime_trend_id,
        definition_version_id=definition_version_id,
        state_version_id=trend.active_state_version_id,
    )
