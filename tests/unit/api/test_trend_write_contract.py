from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError

import src.api.routes._privileged_write_contract as write_contract_module
import src.api.routes.trends as trends_module
from src.api.routes.trends import TrendUpdate, delete_trend, update_trend
from src.core.trend_engine import prob_to_logodds
from src.storage.models import PrivilegedWriteAudit, Trend

pytestmark = pytest.mark.unit


def _request_with_headers(
    *,
    method: str,
    path: str,
    headers: dict[str, str],
) -> Request:
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in headers.items()
            ],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request.state.api_key_id = "test-api-key-id"  # pragma: allowlist secret
    request.state.api_key_name = "test-client"  # pragma: allowlist secret
    return request


def _build_trend() -> Trend:
    now = datetime.now(tz=UTC)
    return Trend(
        id=uuid4(),
        name="Test Trend",
        description="Trend description",
        runtime_trend_id="test-trend",
        definition={"id": "test-trend"},
        baseline_log_odds=prob_to_logodds(0.1),
        current_log_odds=prob_to_logodds(0.2),
        indicators={"signal": {"direction": "escalatory", "weight": 0.04}},
        decay_half_life_days=30,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_update_trend_rejects_stale_revision_and_records_audit(mock_db_session) -> None:
    trend = _build_trend()
    mock_db_session.get.side_effect = [trend, None]

    with pytest.raises(HTTPException) as exc_info:
        await update_trend(
            trend_id=trend.id,
            trend=TrendUpdate(name="Stale Update"),
            request=_request_with_headers(
                method="PATCH",
                path=f"/api/v1/trends/{trend.id}",
                headers={
                    "X-Idempotency-Key": "trend-stale-key",
                    "If-Match": "stale-token",
                },
            ),
            session=mock_db_session,
        )

    assert exc_info.value.status_code == 412
    audit_rows = [
        call.args[0]
        for call in mock_db_session.add.call_args_list
        if isinstance(call.args[0], PrivilegedWriteAudit)
    ]
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "trends.update"
    assert audit_rows[0].target_identifier == str(trend.id)
    assert audit_rows[0].idempotency_key == "trend-stale-key"


@pytest.mark.asyncio
async def test_update_trend_rejects_duplicate_idempotency_key(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend
    existing = PrivilegedWriteAudit(
        id=uuid4(),
        actor_key="test-api-key-id",
        action="trends.update",
        request_method="PATCH",
        request_path=f"/api/v1/trends/{trend.id}",
        target_type="trend",
        target_identifier=str(trend.id),
        idempotency_key="trend-dup-key",
        request_fingerprint="same-fingerprint",
        request_intent={},
        outcome="applied",
    )

    async def _raise_duplicate(*_args, **_kwargs):
        raise IntegrityError("insert", {}, Exception("duplicate"))

    async def _load_existing(*_args, **_kwargs):
        return existing

    async def _noop_update(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(write_contract_module, "_insert_audit_row", _raise_duplicate)
    monkeypatch.setattr(write_contract_module, "_load_audit_row", _load_existing)
    monkeypatch.setattr(write_contract_module, "_update_audit_row", _noop_update)
    monkeypatch.setattr(
        write_contract_module, "request_fingerprint", lambda _intent: "same-fingerprint"
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_trend(
            trend_id=trend.id,
            trend=TrendUpdate(name="Duplicate Update"),
            request=_request_with_headers(
                method="PATCH",
                path=f"/api/v1/trends/{trend.id}",
                headers={
                    "X-Idempotency-Key": "trend-dup-key",
                    "If-Match": write_contract_module.trend_revision_token(trend),
                },
            ),
            session=mock_db_session,
        )

    assert exc_info.value.status_code == 409
    assert "Duplicate privileged write rejected" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_update_trend_rejects_direct_probability_override_and_records_audit(
    mock_db_session,
) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend

    with pytest.raises(HTTPException) as exc_info:
        await update_trend(
            trend_id=trend.id,
            trend=TrendUpdate(current_probability=0.35),
            request=_request_with_headers(
                method="PATCH",
                path=f"/api/v1/trends/{trend.id}",
                headers={
                    "X-Idempotency-Key": "trend-probability-rewrite",
                    "If-Match": write_contract_module.trend_revision_token(trend),
                },
            ),
            session=mock_db_session,
        )

    assert exc_info.value.status_code == 409
    assert "cannot modify current_probability directly" in str(exc_info.value.detail)
    audit_rows = [
        call.args[0]
        for call in mock_db_session.add.call_args_list
        if isinstance(call.args[0], PrivilegedWriteAudit)
    ]
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "trends.update"
    assert float(audit_rows[0].request_intent["payload"]["current_probability"]) == pytest.approx(
        0.35
    )


@pytest.mark.asyncio
async def test_update_trend_preserves_noop_probability_field_in_request_intent(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend
    mock_db_session.scalar.return_value = None

    async def _fake_to_response(*_args, **_kwargs):
        return type(
            "TrendResponseStub",
            (),
            {
                "id": trend.id,
                "revision_token": write_contract_module.trend_revision_token(trend),
                "current_probability": 0.2,
            },
        )()

    monkeypatch.setattr(trends_module, "_to_response", _fake_to_response)

    await update_trend(
        trend_id=trend.id,
        trend=TrendUpdate(description="Updated description", current_probability=0.2),
        request=_request_with_headers(
            method="PATCH",
            path=f"/api/v1/trends/{trend.id}",
            headers={
                "X-Idempotency-Key": "trend-noop-probability",
                "If-Match": write_contract_module.trend_revision_token(trend),
            },
        ),
        session=mock_db_session,
    )

    audit_rows = [
        call.args[0]
        for call in mock_db_session.add.call_args_list
        if isinstance(call.args[0], PrivilegedWriteAudit)
    ]
    assert len(audit_rows) == 1
    assert audit_rows[0].request_intent["payload"] == {
        "description": "Updated description",
        "current_probability": "0.2",
    }


@pytest.mark.asyncio
async def test_update_trend_validates_contract_before_missing_trend_404(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await update_trend(
            trend_id=uuid4(),
            trend=TrendUpdate(name="Missing Trend"),
            request=_request_with_headers(
                method="PATCH",
                path="/api/v1/trends/missing",
                headers={},
            ),
            session=mock_db_session,
        )

    assert exc_info.value.status_code == 400
    audit_rows = [
        call.args[0]
        for call in mock_db_session.add.call_args_list
        if isinstance(call.args[0], PrivilegedWriteAudit)
    ]
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "trends.update"
    assert audit_rows[0].outcome == "missing_idempotency_key"


@pytest.mark.asyncio
async def test_delete_trend_records_missing_trend_rejection_after_header_validation(
    mock_db_session,
) -> None:
    trend_id = uuid4()
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await delete_trend(
            trend_id=trend_id,
            request=_request_with_headers(
                method="DELETE",
                path=f"/api/v1/trends/{trend_id}",
                headers={
                    "X-Idempotency-Key": "delete-missing-key",
                    "If-Match": "expected-revision",
                },
            ),
            session=mock_db_session,
        )

    assert exc_info.value.status_code == 404
    audit_rows = [
        call.args[0]
        for call in mock_db_session.add.call_args_list
        if isinstance(call.args[0], PrivilegedWriteAudit)
    ]
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "trends.delete"
    assert audit_rows[0].outcome == "not_found"
    assert audit_rows[0].expected_revision_token == "expected-revision"


@pytest.mark.asyncio
async def test_update_trend_missing_revision_beats_missing_trend_404(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await update_trend(
            trend_id=uuid4(),
            trend=TrendUpdate(name="Missing Revision"),
            request=_request_with_headers(
                method="PATCH",
                path="/api/v1/trends/missing",
                headers={"X-Idempotency-Key": "missing-revision-key"},
            ),
            session=mock_db_session,
        )

    assert exc_info.value.status_code == 428
    audit_rows = [
        call.args[0]
        for call in mock_db_session.add.call_args_list
        if isinstance(call.args[0], PrivilegedWriteAudit)
    ]
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "trends.update"
    assert audit_rows[0].outcome == "missing_revision_token"
