"""Shared idempotency, revision, and audit helpers for privileged API writes."""

from __future__ import annotations

import enum
import hashlib
import inspect
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NoReturn, cast
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes._privileged_write_audit_deferred import (
    PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY,
    pop_pending_write_success,
    store_pending_write_success,
)
from src.storage.database import async_session_maker
from src.storage.restatement_models import PrivilegedWriteAudit

if TYPE_CHECKING:
    from src.storage.models import Event, TaxonomyGap, Trend

IDEMPOTENCY_HEADER = "X-Idempotency-Key"
REVISION_HEADER = "If-Match"
_MISSING_IDEMPOTENCY_DETAIL = f"{IDEMPOTENCY_HEADER} header is required for this privileged write."
_MISSING_REVISION_DETAIL = f"{REVISION_HEADER} header with the latest revision_token is required for this privileged write."
_STALE_REVISION_DETAIL = (
    "Revision token is stale. Re-read the resource and retry with the latest revision_token."
)
_PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY = PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY


def request_dependency(request: Request) -> Request:
    """Expose the live FastAPI request as an injectable dependency."""

    return request


def _request_or_none(request: Any) -> Request | None:
    return request if isinstance(request, Request) else None


def _normalize_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_jsonable(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list | tuple | set):
        return [_normalize_jsonable(item) for item in value]
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        value_utc = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return value_utc.astimezone(UTC).isoformat()
    if hasattr(value, "hex") and callable(value.hex):
        return str(value)
    return value


def normalize_request_intent(
    payload: Mapping[str, Any] | None = None,
    *,
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical request-intent payload for audit and idempotency."""

    normalized: dict[str, Any] = {}
    if payload:
        normalized["payload"] = _normalize_jsonable(dict(payload))
    if extras:
        normalized["extras"] = _normalize_jsonable(dict(extras))
    return normalized


def request_fingerprint(intent: Mapping[str, Any]) -> str:
    """Hash canonical request intent for conflicting idempotency-key detection."""

    canonical = json.dumps(
        _normalize_jsonable(dict(intent)),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _revision_token(parts: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        _normalize_jsonable(dict(parts)),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def trend_revision_token(trend: Trend) -> str:
    """Return the current optimistic-concurrency token for a trend."""

    return _revision_token(
        {
            "id": trend.id,
            "name": trend.name,
            "description": trend.description,
            "runtime_trend_id": trend.runtime_trend_id,
            "definition": trend.definition if isinstance(trend.definition, dict) else {},
            "baseline_log_odds": float(trend.baseline_log_odds),
            "current_log_odds": float(trend.current_log_odds),
            "indicators": trend.indicators if isinstance(trend.indicators, dict) else {},
            "decay_half_life_days": trend.decay_half_life_days,
            "is_active": trend.is_active,
            "active_definition_version_id": trend.active_definition_version_id,
            "active_state_version_id": trend.active_state_version_id,
            "updated_at": trend.updated_at,
        }
    )


def event_revision_token(event: Event) -> str:
    """Return the current optimistic-concurrency token for an event."""

    return _revision_token(
        {
            "id": event.id,
            "canonical_summary": event.canonical_summary,
            "epistemic_state": event.epistemic_state,
            "activity_state": event.activity_state,
            "lifecycle_status": event.lifecycle_status,
            "has_contradictions": event.has_contradictions,
            "contradiction_notes": event.contradiction_notes,
            "source_count": event.source_count,
            "unique_source_count": event.unique_source_count,
            "independent_evidence_count": event.independent_evidence_count,
            "last_mention_at": event.last_mention_at,
            "last_updated_at": event.last_updated_at,
        }
    )


def taxonomy_gap_revision_token(gap: TaxonomyGap) -> str:
    """Return the current optimistic-concurrency token for a taxonomy-gap row."""

    return _revision_token(
        {
            "id": gap.id,
            "status": gap.status,
            "resolution_notes": gap.resolution_notes,
            "resolved_by": gap.resolved_by,
            "resolved_at": gap.resolved_at,
            "observed_at": gap.observed_at,
        }
    )


def idempotency_key_from_request(request: Any) -> str | None:
    """Return the normalized idempotency key for the request, if present."""

    request_value = _request_or_none(request)
    if request_value is None:
        return None
    value = request_value.headers.get(IDEMPOTENCY_HEADER, "").strip()
    return value or None


def revision_token_from_request(request: Any) -> str | None:
    """Return the normalized caller revision token, if present."""

    request_value = _request_or_none(request)
    if request_value is None:
        return None
    value = request_value.headers.get(REVISION_HEADER, "").strip()
    return value or None


def _actor_key(request: Request) -> str:
    api_key_id = getattr(request.state, "api_key_id", None)
    if isinstance(api_key_id, str) and api_key_id.strip():
        return api_key_id.strip()
    api_key_name = getattr(request.state, "api_key_name", None)
    if isinstance(api_key_name, str) and api_key_name.strip():
        return f"name:{api_key_name.strip()}"
    client_host = request.client.host if request.client is not None else None
    if isinstance(client_host, str) and client_host.strip():
        return f"ip:{client_host.strip()}"
    return "unknown-actor"


def _classify_http_outcome(exc: HTTPException) -> str:
    if exc.status_code == 403:
        return "denied"
    if exc.status_code == 404:
        return "not_found"
    if exc.status_code == 409:
        return "conflict"
    if exc.status_code == 412:
        return "stale_revision"
    if exc.status_code == 422:
        return "validation_failed"
    return "failed"


def _uses_independent_audit_session(route_session: Any) -> bool:
    return isinstance(route_session, AsyncSession)


@asynccontextmanager
async def _audit_session(route_session: Any) -> AsyncIterator[Any]:
    if _uses_independent_audit_session(route_session):
        async with async_session_maker() as audit_session:
            try:
                yield audit_session
                await audit_session.commit()
            except Exception:
                await audit_session.rollback()
                raise
        return

    yield route_session


async def _insert_audit_row(
    route_session: Any, record: PrivilegedWriteAudit
) -> PrivilegedWriteAudit:
    async with _audit_session(route_session) as audit_session:
        add_result = audit_session.add(record)
        if inspect.isawaitable(add_result):
            await add_result
        await audit_session.flush()
        return record


async def _load_audit_row(
    route_session: Any,
    *,
    actor_key: str,
    action: str,
    idempotency_key: str,
) -> PrivilegedWriteAudit | None:
    async with _audit_session(route_session) as audit_session:
        result = await audit_session.scalar(
            select(PrivilegedWriteAudit).where(
                PrivilegedWriteAudit.actor_key == actor_key,
                PrivilegedWriteAudit.action == action,
                PrivilegedWriteAudit.idempotency_key == idempotency_key,
            )
        )
        return cast("PrivilegedWriteAudit | None", result)


async def _update_audit_row(
    route_session: Any,
    *,
    audit_id: Any,
    outcome: str,
    detail: str | None = None,
    observed_revision_token: str | None = None,
    result_links: Mapping[str, Any] | None = None,
    increment_replay: bool = False,
) -> None:
    async with _audit_session(route_session) as audit_session:
        record = await audit_session.get(PrivilegedWriteAudit, audit_id)
        if record is None:
            return
        record.outcome = outcome
        record.detail = detail
        record.last_seen_at = datetime.now(tz=UTC)
        if observed_revision_token is not None:
            record.observed_revision_token = observed_revision_token
        if result_links is not None:
            record.result_links = dict(_normalize_jsonable(dict(result_links)))
        if increment_replay:
            record.replay_count += 1
        await audit_session.flush()


async def record_privileged_write_rejection(
    *,
    route_session: Any,
    request: Any,
    action: str,
    target_type: str,
    target_identifier: str | None,
    intent: Mapping[str, Any],
    outcome: str,
    detail: str,
    operator_identity: str | None = None,
    expected_revision_token: str | None = None,
    observed_revision_token: str | None = None,
) -> None:
    """Persist a terminal rejection row when the request cannot start work."""

    request_value = _request_or_none(request)
    if request_value is None:
        return
    record = PrivilegedWriteAudit(
        actor_key=_actor_key(request_value),
        actor_api_key_id=getattr(request_value.state, "api_key_id", None),
        actor_api_key_name=getattr(request_value.state, "api_key_name", None),
        operator_identity=operator_identity,
        action=action,
        request_method=request_value.method,
        request_path=request_value.url.path,
        target_type=target_type,
        target_identifier=target_identifier,
        idempotency_key=idempotency_key_from_request(request_value),
        request_fingerprint=request_fingerprint(intent),
        request_intent=dict(_normalize_jsonable(dict(intent))),
        expected_revision_token=expected_revision_token,
        observed_revision_token=observed_revision_token,
        outcome=outcome,
        detail=detail,
    )
    try:
        await _insert_audit_row(route_session, record)
    except IntegrityError:
        if record.idempotency_key is None:
            raise
        existing = await _load_audit_row(
            route_session,
            actor_key=record.actor_key,
            action=record.action,
            idempotency_key=record.idempotency_key,
        )
        if existing is None:
            raise
        if existing.request_fingerprint != record.request_fingerprint:
            conflict_detail = (
                f"Idempotency key '{record.idempotency_key}' was already used for a different privileged "
                "write request."
            )
            await _update_audit_row(
                route_session,
                audit_id=existing.id,
                outcome="conflict",
                detail=conflict_detail,
                observed_revision_token=observed_revision_token,
                increment_replay=True,
            )
            raise HTTPException(status_code=409, detail=conflict_detail) from None
        await _update_audit_row(
            route_session,
            audit_id=existing.id,
            outcome=outcome,
            detail=detail,
            observed_revision_token=observed_revision_token,
            increment_replay=True,
        )


@dataclass(slots=True)
class PrivilegedWriteGuard:
    """Track one privileged write attempt until it completes or fails."""

    route_session: Any
    audit_id: Any

    async def succeed(
        self,
        *,
        observed_revision_token: str | None = None,
        result_links: Mapping[str, Any] | None = None,
        detail: str | None = None,
    ) -> None:
        if self.audit_id is None:
            return
        if _uses_independent_audit_session(self.route_session):
            store_pending_write_success(
                self.route_session,
                audit_id=self.audit_id,
                observed_revision_token=observed_revision_token,
                result_links=(
                    dict(_normalize_jsonable(dict(result_links)))
                    if result_links is not None
                    else None
                ),
                detail=detail,
            )
            return
        await _update_audit_row(
            self.route_session,
            audit_id=self.audit_id,
            outcome="applied",
            detail=detail,
            observed_revision_token=observed_revision_token,
            result_links=result_links,
        )

    async def fail(
        self,
        *,
        outcome: str,
        detail: str | None = None,
        observed_revision_token: str | None = None,
    ) -> None:
        if self.audit_id is None:
            return
        if _uses_independent_audit_session(self.route_session):
            pop_pending_write_success(self.route_session, audit_id=self.audit_id)
        await _update_audit_row(
            self.route_session,
            audit_id=self.audit_id,
            outcome=outcome,
            detail=detail,
            observed_revision_token=observed_revision_token,
        )


async def _reject_write_start(
    *,
    route_session: Any,
    request: Any,
    action: str,
    target_type: str,
    target_identifier: str | None,
    intent: Mapping[str, Any],
    outcome: str,
    detail: str,
    status_code: int,
    operator_identity: str | None,
    expected_revision_token: str | None,
    observed_revision_token: str | None,
) -> NoReturn:
    await record_privileged_write_rejection(
        route_session=route_session,
        request=request,
        action=action,
        target_type=target_type,
        target_identifier=target_identifier,
        intent=intent,
        outcome=outcome,
        detail=detail,
        operator_identity=operator_identity,
        expected_revision_token=expected_revision_token,
        observed_revision_token=observed_revision_token,
    )
    raise HTTPException(status_code=status_code, detail=detail)


def _build_in_progress_audit_record(
    *,
    request_value: Request,
    action: str,
    target_type: str,
    target_identifier: str | None,
    operator_identity: str | None,
    idempotency_key: str,
    fingerprint: str,
    normalized_intent: dict[str, Any],
    expected_revision_token: str | None,
    observed_revision_token: str | None,
) -> PrivilegedWriteAudit:
    return PrivilegedWriteAudit(
        actor_key=_actor_key(request_value),
        actor_api_key_id=getattr(request_value.state, "api_key_id", None),
        actor_api_key_name=getattr(request_value.state, "api_key_name", None),
        operator_identity=operator_identity,
        action=action,
        request_method=request_value.method,
        request_path=request_value.url.path,
        target_type=target_type,
        target_identifier=target_identifier,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        request_intent=normalized_intent,
        expected_revision_token=expected_revision_token,
        observed_revision_token=observed_revision_token,
        outcome="in_progress",
    )


async def _raise_duplicate_write_conflict(
    *,
    route_session: Any,
    request_value: Request,
    action: str,
    idempotency_key: str,
    fingerprint: str,
    observed_revision_token: str | None,
) -> None:
    existing = await _load_audit_row(
        route_session,
        actor_key=_actor_key(request_value),
        action=action,
        idempotency_key=idempotency_key,
    )
    if existing is None:
        raise
    conflict_detail = (
        f"Idempotency key '{idempotency_key}' was already used for a different privileged write request."
        if existing.request_fingerprint != fingerprint
        else f"Duplicate privileged write rejected for idempotency key '{idempotency_key}'."
    )
    await _update_audit_row(
        route_session,
        audit_id=existing.id,
        outcome="conflict",
        detail=conflict_detail,
        observed_revision_token=observed_revision_token,
        increment_replay=True,
    )
    raise HTTPException(status_code=409, detail=conflict_detail) from None


async def start_privileged_write(
    *,
    route_session: Any,
    request: Any,
    action: str,
    target_type: str,
    target_identifier: str | None,
    intent: Mapping[str, Any],
    operator_identity: str | None = None,
    require_revision: bool = False,
    observed_revision_token: str | None = None,
) -> PrivilegedWriteGuard:
    """Create the durable write-attempt record and enforce write preconditions."""

    request_value = _request_or_none(request)
    if request_value is None:
        return PrivilegedWriteGuard(route_session=None, audit_id=None)
    normalized_intent = dict(_normalize_jsonable(dict(intent)))
    fingerprint = request_fingerprint(normalized_intent)
    idempotency_key = idempotency_key_from_request(request_value)
    expected_revision_token = revision_token_from_request(request_value)
    if idempotency_key is None:
        await _reject_write_start(
            route_session=route_session,
            request=request,
            action=action,
            target_type=target_type,
            target_identifier=target_identifier,
            intent=normalized_intent,
            outcome="missing_idempotency_key",
            detail=_MISSING_IDEMPOTENCY_DETAIL,
            status_code=400,
            operator_identity=operator_identity,
            expected_revision_token=expected_revision_token,
            observed_revision_token=observed_revision_token,
        )
    if require_revision and expected_revision_token is None:
        await _reject_write_start(
            route_session=route_session,
            request=request,
            action=action,
            target_type=target_type,
            target_identifier=target_identifier,
            intent=normalized_intent,
            outcome="missing_revision_token",
            detail=_MISSING_REVISION_DETAIL,
            status_code=428,
            operator_identity=operator_identity,
            expected_revision_token=expected_revision_token,
            observed_revision_token=observed_revision_token,
        )
    record = _build_in_progress_audit_record(
        request_value=request_value,
        action=action,
        target_type=target_type,
        target_identifier=target_identifier,
        operator_identity=operator_identity,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        normalized_intent=normalized_intent,
        expected_revision_token=expected_revision_token,
        observed_revision_token=observed_revision_token,
    )
    try:
        inserted = await _insert_audit_row(route_session, record)
    except IntegrityError:
        await _raise_duplicate_write_conflict(
            route_session=route_session,
            request_value=request_value,
            action=action,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            observed_revision_token=observed_revision_token,
        )

    if require_revision and expected_revision_token != observed_revision_token:
        await _update_audit_row(
            route_session,
            audit_id=inserted.id,
            outcome="stale_revision",
            detail=_STALE_REVISION_DETAIL,
            observed_revision_token=observed_revision_token,
        )
        raise HTTPException(status_code=412, detail=_STALE_REVISION_DETAIL)
    return PrivilegedWriteGuard(route_session=route_session, audit_id=inserted.id)


@asynccontextmanager
async def privileged_write(
    *,
    route_session: Any,
    request: Any,
    action: str,
    target_type: str,
    target_identifier: str | None,
    intent: Mapping[str, Any],
    operator_identity: str | None = None,
    require_revision: bool = False,
    observed_revision_token: str | None = None,
) -> AsyncIterator[PrivilegedWriteGuard]:
    """Context manager that finalizes a write audit row on route exceptions."""

    guard = await start_privileged_write(
        route_session=route_session,
        request=request,
        action=action,
        target_type=target_type,
        target_identifier=target_identifier,
        intent=intent,
        operator_identity=operator_identity,
        require_revision=require_revision,
        observed_revision_token=observed_revision_token,
    )
    try:
        yield guard
    except HTTPException as exc:
        await guard.fail(
            outcome=_classify_http_outcome(exc),
            detail=str(exc.detail),
            observed_revision_token=observed_revision_token,
        )
        raise
    except Exception as exc:
        await guard.fail(
            outcome="failed",
            detail=str(exc),
            observed_revision_token=observed_revision_token,
        )
        raise
