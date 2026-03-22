"""Deferred privileged-write audit state stored on route sessions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY = "pending_privileged_write_successes"


@dataclass(slots=True)
class PendingPrivilegedWriteSuccess:
    audit_id: Any
    observed_revision_token: str | None
    result_links: Mapping[str, Any] | None
    detail: str | None


def pending_write_successes(route_session: Any) -> list[PendingPrivilegedWriteSuccess]:
    session_info = cast("dict[str, Any]", route_session.info)
    pending = session_info.get(PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY)
    if isinstance(pending, list):
        return cast("list[PendingPrivilegedWriteSuccess]", pending)
    session_info[PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY] = []
    return cast(
        "list[PendingPrivilegedWriteSuccess]", session_info[PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY]
    )


def store_pending_write_success(
    route_session: Any,
    *,
    audit_id: Any,
    observed_revision_token: str | None,
    result_links: Mapping[str, Any] | None,
    detail: str | None,
) -> None:
    pending = pending_write_successes(route_session)
    for index, entry in enumerate(pending):
        if entry.audit_id == audit_id:
            pending[index] = PendingPrivilegedWriteSuccess(
                audit_id=audit_id,
                observed_revision_token=observed_revision_token,
                result_links=result_links,
                detail=detail,
            )
            return
    pending.append(
        PendingPrivilegedWriteSuccess(
            audit_id=audit_id,
            observed_revision_token=observed_revision_token,
            result_links=result_links,
            detail=detail,
        )
    )


def pop_pending_write_success(
    route_session: Any,
    *,
    audit_id: Any,
) -> PendingPrivilegedWriteSuccess | None:
    pending = pending_write_successes(route_session)
    for index, entry in enumerate(pending):
        if entry.audit_id == audit_id:
            return pending.pop(index)
    return None


def drain_pending_write_successes(route_session: Any) -> list[PendingPrivilegedWriteSuccess]:
    pending = pending_write_successes(route_session)
    drained = list(pending)
    pending.clear()
    return drained
