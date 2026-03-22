from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import src.api.routes._privileged_write_contract as write_contract_module
from src.storage.models import PrivilegedWriteAudit

pytestmark = pytest.mark.unit


def _request_with_headers(
    *,
    method: str = "POST",
    path: str = "/api/v1/test",
    headers: dict[str, str] | None = None,
    client: tuple[str, int] | None = ("127.0.0.1", 1234),
    api_key_id: str | None = "test-api-key-id",
    api_key_name: str | None = "test-client",
) -> Request:
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in (headers or {}).items()
            ],
            "query_string": b"",
            "client": client,
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request.state.api_key_id = api_key_id
    request.state.api_key_name = api_key_name
    return request


@pytest.mark.asyncio
async def test_request_helpers_and_actor_fallbacks_cover_edge_paths() -> None:
    request = _request_with_headers(
        headers={
            write_contract_module.IDEMPOTENCY_HEADER: "  idem-key  ",
            write_contract_module.REVISION_HEADER: "  rev-token  ",
        }
    )
    assert write_contract_module.request_dependency(request) is request
    assert write_contract_module.idempotency_key_from_request(request) == "idem-key"
    assert write_contract_module.revision_token_from_request(request) == "rev-token"
    assert write_contract_module.idempotency_key_from_request(object()) is None
    assert write_contract_module.revision_token_from_request(object()) is None
    assert (
        write_contract_module._actor_key(
            _request_with_headers(api_key_id=None, api_key_name="named-client")
        )
        == "name:named-client"
    )
    assert (
        write_contract_module._actor_key(_request_with_headers(api_key_id=None, api_key_name=None))
        == "ip:127.0.0.1"
    )
    assert (
        write_contract_module._actor_key(
            _request_with_headers(api_key_id=None, api_key_name=None, client=None)
        )
        == "unknown-actor"
    )
    assert write_contract_module._classify_http_outcome(HTTPException(status_code=403)) == "denied"
    assert (
        write_contract_module._classify_http_outcome(HTTPException(status_code=412))
        == "stale_revision"
    )


@pytest.mark.asyncio
async def test_audit_session_async_session_commits_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return audit_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    route_session = AsyncSession()
    monkeypatch.setattr(write_contract_module, "async_session_maker", _Factory())

    async with write_contract_module._audit_session(route_session) as yielded:
        assert yielded is audit_session
    audit_session.commit.assert_awaited_once()

    with pytest.raises(RuntimeError, match="boom"):
        async with write_contract_module._audit_session(route_session):
            raise RuntimeError("boom")
    audit_session.rollback.assert_awaited_once()
    await route_session.close()


@pytest.mark.asyncio
async def test_load_and_update_audit_rows_use_route_session(mock_db_session) -> None:
    record = PrivilegedWriteAudit(
        id=uuid4(),
        actor_key="test-api-key-id",
        action="trends.update",
        request_method="PATCH",
        request_path="/api/v1/trends/test",
        target_type="trend",
        target_identifier="trend-1",
        idempotency_key="idem-key",
        request_fingerprint="fingerprint",
        request_intent={},
        outcome="in_progress",
        replay_count=1,
    )
    mock_db_session.scalar.return_value = record

    loaded = await write_contract_module._load_audit_row(
        mock_db_session,
        actor_key="test-api-key-id",
        action="trends.update",
        idempotency_key="idem-key",
    )

    assert loaded is record
    mock_db_session.get.return_value = record
    await write_contract_module._update_audit_row(
        mock_db_session,
        audit_id=record.id,
        outcome="applied",
        detail="done",
        observed_revision_token="rev-2",
        result_links={"target_id": uuid4()},
        increment_replay=True,
    )

    assert record.outcome == "applied"
    assert record.detail == "done"
    assert record.observed_revision_token == "rev-2"
    assert record.result_links is not None
    assert isinstance(record.result_links["target_id"], str)
    assert record.replay_count == 2

    previous_revision = record.observed_revision_token
    previous_links = dict(record.result_links)
    await write_contract_module._update_audit_row(
        mock_db_session,
        audit_id=record.id,
        outcome="conflict",
    )

    assert record.outcome == "conflict"
    assert record.observed_revision_token == previous_revision
    assert record.result_links == previous_links
    assert record.replay_count == 2
    mock_db_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_record_privileged_write_rejection_inserts_expected_audit_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[PrivilegedWriteAudit] = []

    async def _capture(_route_session, record: PrivilegedWriteAudit) -> PrivilegedWriteAudit:
        captured.append(record)
        return record

    request = _request_with_headers(
        path="/api/v1/events/test-event/feedback",
        headers={write_contract_module.IDEMPOTENCY_HEADER: "reject-key"},
    )
    monkeypatch.setattr(write_contract_module, "_insert_audit_row", _capture)

    await write_contract_module.record_privileged_write_rejection(
        route_session=object(),
        request=request,
        action="feedback.event_feedback",
        target_type="event",
        target_identifier="test-event",
        intent={"payload": {"event_id": "test-event"}},
        outcome="not_found",
        detail="missing event",
        operator_identity="analyst@horadus",
        expected_revision_token="expected-rev",
        observed_revision_token="observed-rev",
    )

    assert len(captured) == 1
    record = captured[0]
    assert record.actor_key == "test-api-key-id"
    assert record.operator_identity == "analyst@horadus"
    assert record.idempotency_key == "reject-key"
    assert record.expected_revision_token == "expected-rev"
    assert record.observed_revision_token == "observed-rev"
    assert record.outcome == "not_found"


@pytest.mark.asyncio
async def test_guard_succeed_and_fail_delegate_to_audit_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_audit_row = AsyncMock()
    monkeypatch.setattr(write_contract_module, "_update_audit_row", update_audit_row)

    guard = write_contract_module.PrivilegedWriteGuard(route_session="session", audit_id="audit-id")
    await guard.succeed(observed_revision_token="rev-1", result_links={"trend_id": "trend-1"})
    await guard.fail(outcome="failed", detail="boom", observed_revision_token="rev-2")

    assert update_audit_row.await_count == 2
    assert update_audit_row.await_args_list[0].kwargs["outcome"] == "applied"
    assert update_audit_row.await_args_list[1].kwargs["outcome"] == "failed"


@pytest.mark.asyncio
async def test_start_privileged_write_rejects_missing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejection = AsyncMock()
    monkeypatch.setattr(write_contract_module, "record_privileged_write_rejection", rejection)

    with pytest.raises(HTTPException) as missing_idem:
        await write_contract_module.start_privileged_write(
            route_session=object(),
            request=_request_with_headers(headers={}),
            action="trends.update",
            target_type="trend",
            target_identifier="trend-1",
            intent={"payload": {"name": "Trend 1"}},
        )
    assert missing_idem.value.status_code == 400

    with pytest.raises(HTTPException) as missing_revision:
        await write_contract_module.start_privileged_write(
            route_session=object(),
            request=_request_with_headers(
                headers={write_contract_module.IDEMPOTENCY_HEADER: "idem-key"}
            ),
            action="trends.update",
            target_type="trend",
            target_identifier="trend-1",
            intent={"payload": {"name": "Trend 1"}},
            require_revision=True,
        )
    assert missing_revision.value.status_code == 428
    assert rejection.await_count == 2


@pytest.mark.asyncio
async def test_start_privileged_write_reraises_integrity_when_duplicate_row_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_duplicate(*_args, **_kwargs):
        raise IntegrityError("insert", {}, Exception("duplicate"))

    monkeypatch.setattr(write_contract_module, "_insert_audit_row", _raise_duplicate)
    monkeypatch.setattr(write_contract_module, "_load_audit_row", AsyncMock(return_value=None))

    with pytest.raises(IntegrityError):
        await write_contract_module.start_privileged_write(
            route_session=object(),
            request=_request_with_headers(
                headers={write_contract_module.IDEMPOTENCY_HEADER: "idem-key"}
            ),
            action="trends.update",
            target_type="trend",
            target_identifier="trend-1",
            intent={"payload": {"name": "Trend 1"}},
        )
