"""Shared mutation helpers for privileged trend writes."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast
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


_DIRECT_PROBABILITY_OVERRIDE_DETAIL = (
    "PATCH /api/v1/trends/{id} cannot modify current_probability directly; "
    "use POST /api/v1/trends/{id}/override."
)
_CURRENT_PROBABILITY_NOOP_ABS_TOL = 1e-6


@dataclass(slots=True)
class TrendMutationResult:
    """Useful linkage ids returned after a trend mutation succeeds."""

    trend: Trend
    runtime_trend_id: str
    definition_version_id: UUID | None
    state_version_id: UUID | None


@dataclass(slots=True)
class TrendUpdatePlan:
    """Resolved candidate state for a trend update mutation."""

    previous_definition: dict[str, Any]
    updates: dict[str, Any]
    activation_mode: str | None
    activation_notes: str | None
    definition_updated: bool
    candidate_name: str
    candidate_description: str | None
    candidate_definition: dict[str, Any] | Any
    candidate_forecast_contract: Any
    candidate_baseline_probability: float
    candidate_indicators: dict[str, Any] | Any
    candidate_decay_half_life_days: int


TrendActivationKind = Literal["create", "rebase", "replay", "new_line"]


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


def _definition_update_requested(updates: dict[str, Any]) -> bool:
    return any(
        key in updates for key in ("definition", "forecast_contract", "baseline_probability")
    )


def _normalize_noop_current_probability(
    *,
    trend: Trend,
    updates: dict[str, Any],
    activation_mode: str | None,
    candidate_baseline_probability: float,
    state_activation_required: bool,
) -> None:
    if "current_probability" not in updates:
        return
    requested_probability = updates["current_probability"]
    if requested_probability is None:
        updates.pop("current_probability", None)
        return
    requested_probability = float(requested_probability)
    current_probability = logodds_to_prob(float(trend.current_log_odds))
    if (
        activation_mode in ("replay", "new_line")
        and state_activation_required
        and (
            math.isclose(
                requested_probability,
                current_probability,
                rel_tol=0.0,
                abs_tol=_CURRENT_PROBABILITY_NOOP_ABS_TOL,
            )
            or math.isclose(
                requested_probability,
                candidate_baseline_probability,
                rel_tol=0.0,
                abs_tol=_CURRENT_PROBABILITY_NOOP_ABS_TOL,
            )
        )
    ):
        updates.pop("current_probability", None)
        return
    if activation_mode not in (None, "rebase"):
        return
    if math.isclose(
        requested_probability,
        current_probability,
        rel_tol=0.0,
        abs_tol=_CURRENT_PROBABILITY_NOOP_ABS_TOL,
    ):
        updates.pop("current_probability", None)


def _resolved_candidate_definition(
    *,
    trend: Trend,
    updates: dict[str, Any],
    definition_updated: bool,
) -> dict[str, Any] | Any:
    candidate_definition = updates.get("definition", trend.definition)
    if ("forecast_contract" in updates and "definition" not in updates) or not definition_updated:
        candidate_definition = normalize_definition_payload(
            trend.definition if isinstance(trend.definition, dict) else None
        )
        candidate_definition.pop("forecast_contract", None)
    return candidate_definition


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


def _build_trend_update_plan(trend: Trend, payload: TrendUpdate) -> TrendUpdatePlan:
    previous_definition = normalize_definition_payload(
        trend.definition if isinstance(trend.definition, dict) else None
    )
    updates = payload.model_dump(exclude_unset=True)
    activation_mode = updates.pop("activation_mode", None)
    activation_notes = updates.pop("activation_notes", None)
    definition_updated = _definition_update_requested(updates)
    candidate_definition = _resolved_candidate_definition(
        trend=trend,
        updates=updates,
        definition_updated=definition_updated,
    )
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
    state_activation_required = _state_contract_changed(
        updates=updates,
        trend=trend,
        candidate_definition=candidate_definition,
        previous_definition=previous_definition,
        candidate_baseline_probability=candidate_baseline_probability,
        candidate_indicators=candidate_indicators,
        candidate_decay_half_life_days=candidate_decay_half_life_days,
    )
    _normalize_noop_current_probability(
        trend=trend,
        updates=updates,
        activation_mode=activation_mode,
        candidate_baseline_probability=candidate_baseline_probability,
        state_activation_required=state_activation_required,
    )
    return TrendUpdatePlan(
        previous_definition=previous_definition,
        updates=updates,
        activation_mode=activation_mode,
        activation_notes=activation_notes,
        definition_updated=definition_updated,
        candidate_name=updates.get("name", trend.name),
        candidate_description=updates.get("description", trend.description),
        candidate_definition=candidate_definition,
        candidate_forecast_contract=updates.get("forecast_contract"),
        candidate_baseline_probability=candidate_baseline_probability,
        candidate_indicators=candidate_indicators,
        candidate_decay_half_life_days=candidate_decay_half_life_days,
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


def _state_activation_required(*, trend: Trend, plan: TrendUpdatePlan) -> bool:
    return _state_contract_changed(
        updates=plan.updates,
        trend=trend,
        candidate_definition=plan.candidate_definition,
        previous_definition=plan.previous_definition,
        candidate_baseline_probability=plan.candidate_baseline_probability,
        candidate_indicators=plan.candidate_indicators,
        candidate_decay_half_life_days=plan.candidate_decay_half_life_days,
    )


def _enforce_activation_mode(*, trend: Trend, plan: TrendUpdatePlan) -> None:
    if not _state_activation_required(trend=trend, plan=plan) or plan.activation_mode is not None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Material live-state changes require activation_mode "
            "('rebase', 'replay', or 'new_line')."
        ),
    )


def _enforce_override_route(*, trend: Trend, plan: TrendUpdatePlan) -> None:
    if "current_probability" not in plan.updates:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_DIRECT_PROBABILITY_OVERRIDE_DETAIL,
    )


def _apply_trend_updates(
    *,
    trend: Trend,
    plan: TrendUpdatePlan,
    write_payload: Any,
    validated_config: Any,
) -> None:
    updates = plan.updates
    if "name" in updates:
        trend.name = validated_config.name
    if "description" in updates:
        trend.description = validated_config.description
    if plan.definition_updated:
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


async def _record_definition_history_if_needed(
    *,
    session: AsyncSession,
    trend: Trend,
    plan: TrendUpdatePlan,
) -> None:
    if not plan.definition_updated:
        return
    await record_definition_version_if_material_change(
        session,
        trend=trend,
        previous_definition=plan.previous_definition,
        actor="api",
        context="update_trend",
    )


async def _activate_trend_state_if_needed(
    *,
    session: AsyncSession,
    trend: Trend,
    plan: TrendUpdatePlan,
) -> UUID | None:
    definition_version_id = trend.active_definition_version_id
    if not _state_activation_required(trend=trend, plan=plan):
        return definition_version_id
    assert plan.activation_mode is not None
    definition_version = await ensure_definition_version(
        session=session,
        trend=trend,
        actor="api",
        context="update_trend",
    )
    await activate_trend_state(
        session=session,
        trend=trend,
        activation_kind=cast("TrendActivationKind", plan.activation_mode),
        actor="api",
        context="update_trend",
        definition_version=definition_version,
        details={"notes": plan.activation_notes} if plan.activation_notes else None,
    )
    return definition_version.id


async def update_trend_mutation(
    *,
    session: AsyncSession,
    trend_id: UUID,
    trend: Trend,
    payload: TrendUpdate,
) -> TrendMutationResult:
    """Apply a trend update plus any required versioned-state activation."""

    plan = _build_trend_update_plan(trend, payload)
    _enforce_override_route(trend=trend, plan=plan)
    _enforce_activation_mode(trend=trend, plan=plan)

    try:
        write_payload = build_validated_trend_write_payload(
            name=plan.candidate_name,
            description=plan.candidate_description,
            baseline_probability=plan.candidate_baseline_probability,
            decay_half_life_days=plan.candidate_decay_half_life_days,
            indicators=plan.candidate_indicators,
            definition=plan.candidate_definition,
            forecast_contract=plan.candidate_forecast_contract,
            require_forecast_contract=plan.definition_updated,
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

    _apply_trend_updates(
        trend=trend,
        plan=plan,
        write_payload=write_payload,
        validated_config=validated_config,
    )
    await _record_definition_history_if_needed(session=session, trend=trend, plan=plan)
    definition_version_id = await _activate_trend_state_if_needed(
        session=session,
        trend=trend,
        plan=plan,
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
