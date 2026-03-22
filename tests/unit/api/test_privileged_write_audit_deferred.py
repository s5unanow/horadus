from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes._privileged_write_audit_deferred import (
    PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY,
    drain_pending_write_successes,
    pending_write_successes,
    pop_pending_write_success,
    store_pending_write_success,
)

pytestmark = pytest.mark.unit


def test_pending_write_success_helpers_cover_create_update_pop_and_drain() -> None:
    route_session = SimpleNamespace(info={})

    pending = pending_write_successes(route_session)

    assert pending == []
    assert route_session.info[PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY] == []

    store_pending_write_success(
        route_session,
        audit_id="audit-1",
        observed_revision_token="rev-1",
        result_links={"trend_id": "trend-1"},
        detail="done",
    )
    store_pending_write_success(
        route_session,
        audit_id="audit-1",
        observed_revision_token="rev-2",
        result_links={"trend_id": "trend-2"},
        detail="updated",
    )
    store_pending_write_success(
        route_session,
        audit_id="audit-2",
        observed_revision_token="rev-3",
        result_links={"trend_id": "trend-3"},
        detail="second",
    )
    store_pending_write_success(
        route_session,
        audit_id="audit-2",
        observed_revision_token="rev-4",
        result_links={"trend_id": "trend-4"},
        detail="second-updated",
    )

    updated = pending_write_successes(route_session)
    assert len(updated) == 2
    assert updated[0].observed_revision_token == "rev-2"
    assert updated[0].result_links == {"trend_id": "trend-2"}
    assert updated[1].observed_revision_token == "rev-4"
    assert updated[1].detail == "second-updated"

    missing = pop_pending_write_success(route_session, audit_id="missing")
    popped = pop_pending_write_success(route_session, audit_id="audit-1")

    assert missing is None
    assert popped is not None
    assert popped.detail == "updated"

    drained = drain_pending_write_successes(route_session)

    assert len(drained) == 1
    assert drained[0].audit_id == "audit-2"
    assert route_session.info[PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY] == []
