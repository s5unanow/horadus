from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response
from fastapi.testclient import TestClient

import src.api.middleware.auth as auth_middleware_module
import src.api.routes.auth as auth_module
import src.api.routes.feedback as feedback_routes
import src.api.routes.sources as sources_routes
import src.api.routes.trends as trends_routes
from src.api.middleware.auth import APIKeyAuthMiddleware
from src.core.api_key_manager import APIKeyManager
from src.storage.database import get_session

pytestmark = pytest.mark.unit


def _build_manager(
    *,
    auth_enabled: bool = True,
    rate_limit_per_minute: int = 5,
) -> tuple[APIKeyManager, str]:
    manager = APIKeyManager(
        auth_enabled=auth_enabled,
        legacy_api_key=None,
        static_api_keys=[],
        default_rate_limit_per_minute=rate_limit_per_minute,
    )
    _record, raw_credential = manager.create_key(name="test-client")
    return (manager, raw_credential)


def _build_app(manager: APIKeyManager) -> FastAPI:
    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware, manager=manager)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/protected")
    async def protected() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/v1/admin-protected",
        dependencies=[Depends(auth_middleware_module.require_privileged_access("test.admin"))],
    )
    async def admin_protected() -> dict[str, str]:
        return {"status": "admin-ok"}

    app.include_router(auth_module.router, prefix="/api/v1/auth", tags=["Auth"])
    return app


def _build_api_app(manager: APIKeyManager, session: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware, manager=manager)
    app.include_router(sources_routes.router, prefix="/api/v1/sources", tags=["Sources"])
    app.include_router(trends_routes.router, prefix="/api/v1/trends", tags=["Trends"])
    app.include_router(feedback_routes.router, prefix="/api/v1", tags=["Feedback"])

    async def _override_get_session():
        yield session

    app.dependency_overrides[get_session] = _override_get_session
    return app


def test_missing_api_key_returns_401() -> None:
    manager, _credential = _build_manager()
    client = TestClient(_build_app(manager))

    response = client.get("/api/v1/protected")

    assert response.status_code == 401
    assert response.json()["message"] == "Missing API key"


def test_valid_api_key_allows_request() -> None:
    manager, credential = _build_manager()
    client = TestClient(_build_app(manager))

    response = client.get(
        "/api/v1/protected",
        headers={"X-API-Key": credential},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_non_admin_key_is_denied_on_privileged_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_middleware_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_middleware_module, "logger", audit_logger)
    client = TestClient(_build_app(manager))

    response = client.post(
        "/api/v1/admin-protected",
        headers={"X-API-Key": credential},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin API key required"
    last_log = audit_logger.info.call_args_list[-1]
    assert last_log.kwargs["action"] == "test.admin"
    assert last_log.kwargs["outcome"] == "denied"


def test_privileged_route_allows_admin_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_middleware_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_middleware_module, "logger", audit_logger)
    client = TestClient(_build_app(manager))

    response = client.post(
        "/api/v1/admin-protected",
        headers={
            "X-API-Key": credential,
            "X-Admin-API-Key": "admin-secret",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "admin-ok"}
    last_log = audit_logger.info.call_args_list[-1]
    assert last_log.kwargs["action"] == "test.admin"
    assert last_log.kwargs["outcome"] == "authorized"


def test_health_route_bypasses_auth() -> None:
    manager, _credential = _build_manager()
    client = TestClient(_build_app(manager))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_auth_disabled_bypasses_protected_route() -> None:
    middleware = APIKeyAuthMiddleware(FastAPI(), manager=SimpleNamespace(auth_required=False))

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/protected",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )

    async def call_next(_request: Request) -> Response:
        return Response(status_code=204)

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 204


def test_invalid_api_key_returns_401() -> None:
    manager, _credential = _build_manager()
    client = TestClient(_build_app(manager))

    response = client.get("/api/v1/protected", headers={"X-API-Key": "invalid"})

    assert response.status_code == 401
    assert response.json()["message"] == "Invalid API key"


def test_rate_limit_returns_429() -> None:
    manager, credential = _build_manager(rate_limit_per_minute=1)
    client = TestClient(_build_app(manager))
    headers = {"X-API-Key": credential}

    first = client.get("/api/v1/protected", headers=headers)
    second = client.get("/api/v1/protected", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second.headers


def test_rate_limit_without_retry_after_omits_header(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, credential = _build_manager()
    client = TestClient(_build_app(manager))
    record = manager.authenticate(credential)
    assert record is not None
    monkeypatch.setattr(manager, "check_rate_limit", lambda _record_id: (False, None))

    response = client.get("/api/v1/protected", headers={"X-API-Key": credential})

    assert response.status_code == 429
    assert "Retry-After" not in response.headers
    assert response.json()["message"] == "Rate limit exceeded"


def test_auth_key_management_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_module, "get_api_key_manager", lambda: manager)
    monkeypatch.setattr(auth_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_module, "logger", audit_logger)
    client = TestClient(_build_app(manager))
    headers = {
        "X-API-Key": credential,
        "X-Admin-API-Key": "admin-secret",
    }

    listed = client.get("/api/v1/auth/keys", headers=headers)
    created = client.post(
        "/api/v1/auth/keys",
        headers=headers,
        json={"name": "dashboard", "rate_limit_per_minute": 50},
    )

    assert listed.status_code == 200
    assert created.status_code == 201
    created_payload = created.json()
    created_id = created_payload["key"]["id"]
    original_raw_key = created_payload["api_key"]
    assert created_payload["api_key"]
    assert created_payload["key"]["name"] == "dashboard"

    rotated = client.post(f"/api/v1/auth/keys/{created_id}/rotate", headers=headers)
    assert rotated.status_code == 200
    rotated_payload = rotated.json()
    assert rotated_payload["api_key"]
    assert rotated_payload["api_key"] != original_raw_key
    assert manager.authenticate(original_raw_key) is None
    assert manager.authenticate(rotated_payload["api_key"]) is not None

    revoked = client.delete(f"/api/v1/auth/keys/{created_id}", headers=headers)
    assert revoked.status_code == 404

    revoked_rotated = client.delete(
        f"/api/v1/auth/keys/{rotated_payload['key']['id']}", headers=headers
    )
    assert revoked_rotated.status_code == 204
    logged_actions = [call.kwargs.get("action") for call in audit_logger.info.call_args_list]
    assert "list_keys" in logged_actions
    assert "create_key" in logged_actions
    assert "rotate_key" in logged_actions
    assert "revoke_key" in logged_actions


def test_admin_denied_attempt_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_module, "get_api_key_manager", lambda: manager)
    monkeypatch.setattr(auth_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_module, "logger", audit_logger)
    client = TestClient(_build_app(manager))

    response = client.get(
        "/api/v1/auth/keys",
        headers={"X-API-Key": credential},
    )

    assert response.status_code == 403
    assert audit_logger.info.call_count >= 1
    last_log = audit_logger.info.call_args_list[-1]
    assert last_log.kwargs["action"] == "list_keys"
    assert last_log.kwargs["outcome"] == "denied"


def test_source_create_requires_admin_header(
    mock_db_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_middleware_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_middleware_module, "logger", audit_logger)
    client = TestClient(_build_api_app(manager, mock_db_session))

    response = client.post(
        "/api/v1/sources",
        headers={"X-API-Key": credential},
        json={
            "type": "rss",
            "name": "Denied Source",
            "url": "https://example.com/feed.xml",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin API key required"
    mock_db_session.add.assert_not_called()
    last_log = audit_logger.info.call_args_list[-1]
    assert last_log.kwargs["action"] == "sources.create"
    assert last_log.kwargs["outcome"] == "denied"


def test_source_create_allows_admin_header(
    mock_db_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_middleware_module.settings, "API_ADMIN_KEY", "admin-secret")
    client = TestClient(_build_api_app(manager, mock_db_session))

    async def flush_side_effect() -> None:
        source_record = mock_db_session.add.call_args.args[0]
        source_record.id = uuid4()

    mock_db_session.flush.side_effect = flush_side_effect

    response = client.post(
        "/api/v1/sources",
        headers={
            "X-API-Key": credential,
            "X-Admin-API-Key": "admin-secret",
        },
        json={
            "type": "rss",
            "name": "Allowed Source",
            "url": "https://example.com/feed.xml",
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Allowed Source"
    mock_db_session.add.assert_called_once()


def test_trend_sync_query_flag_is_rejected_on_list_route(
    mock_db_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    sync_mock = AsyncMock()
    monkeypatch.setattr(trends_routes, "load_trends_from_config", sync_mock)
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)
    client = TestClient(_build_api_app(manager, mock_db_session))

    baseline = client.get("/api/v1/trends", headers={"X-API-Key": credential})
    sync_attempt = client.get(
        "/api/v1/trends?sync_from_config=true",
        headers={"X-API-Key": credential},
    )

    assert baseline.status_code == 200
    assert baseline.json() == []
    assert sync_attempt.status_code == 400
    assert sync_attempt.json()["detail"] == trends_routes.SYNC_FROM_CONFIG_QUERY_REJECTED_DETAIL
    sync_mock.assert_not_awaited()


def test_trend_sync_config_requires_admin_header(
    mock_db_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_middleware_module.settings, "API_ADMIN_KEY", "admin-secret")
    sync_mock = AsyncMock()
    monkeypatch.setattr(trends_routes, "load_trends_from_config", sync_mock)
    client = TestClient(_build_api_app(manager, mock_db_session))

    response = client.post(
        "/api/v1/trends/sync-config",
        headers={"X-API-Key": credential},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin API key required"
    sync_mock.assert_not_awaited()


def test_feedback_override_requires_admin_header(
    mock_db_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_middleware_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_middleware_module, "logger", audit_logger)
    client = TestClient(_build_api_app(manager, mock_db_session))

    response = client.post(
        f"/api/v1/trends/{uuid4()}/override",
        headers={"X-API-Key": credential},
        json={"delta_log_odds": -0.1},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin API key required"
    mock_db_session.get.assert_not_awaited()
    last_log = audit_logger.info.call_args_list[-1]
    assert last_log.kwargs["action"] == "feedback.trend_override"
    assert last_log.kwargs["outcome"] == "denied"


def test_create_key_denied_attempt_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_module, "get_api_key_manager", lambda: manager)
    monkeypatch.setattr(auth_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_module, "logger", audit_logger)
    client = TestClient(_build_app(manager))

    response = client.post(
        "/api/v1/auth/keys",
        headers={"X-API-Key": credential},
        json={"name": "dashboard", "rate_limit_per_minute": 50},
    )

    assert response.status_code == 403
    last_log = audit_logger.info.call_args_list[-1]
    assert last_log.kwargs["action"] == "create_key"
    assert last_log.kwargs["outcome"] == "denied"
    assert last_log.kwargs["requested_name"] == "dashboard"
    assert last_log.kwargs["requested_rate_limit"] == 50


def test_revoke_and_rotate_missing_keys_are_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_module, "get_api_key_manager", lambda: manager)
    monkeypatch.setattr(auth_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_module, "logger", audit_logger)
    client = TestClient(_build_app(manager))
    headers = {
        "X-API-Key": credential,
        "X-Admin-API-Key": "admin-secret",
    }

    revoked = client.delete("/api/v1/auth/keys/missing-key", headers=headers)
    rotated = client.post("/api/v1/auth/keys/missing-key/rotate", headers=headers)

    assert revoked.status_code == 404
    assert rotated.status_code == 404
    actions = [
        (call.kwargs["action"], call.kwargs["outcome"]) for call in audit_logger.info.call_args_list
    ]
    assert ("revoke_key", "not_found") in actions
    assert ("rotate_key", "not_found") in actions


def test_revoke_and_rotate_denied_attempts_are_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_module, "get_api_key_manager", lambda: manager)
    monkeypatch.setattr(auth_module.settings, "API_ADMIN_KEY", "admin-secret")
    audit_logger = MagicMock()
    monkeypatch.setattr(auth_module, "logger", audit_logger)
    client = TestClient(_build_app(manager))

    revoked = client.delete("/api/v1/auth/keys/missing-key", headers={"X-API-Key": credential})
    rotated = client.post("/api/v1/auth/keys/missing-key/rotate", headers={"X-API-Key": credential})

    assert revoked.status_code == 403
    assert rotated.status_code == 403
    actions = [
        (call.kwargs["action"], call.kwargs["outcome"]) for call in audit_logger.info.call_args_list
    ]
    assert ("revoke_key", "denied") in actions
    assert ("rotate_key", "denied") in actions


def test_key_management_rejects_invalid_admin_header_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_module, "get_api_key_manager", lambda: manager)
    monkeypatch.setattr(auth_module.settings, "API_ADMIN_KEY", "admin-secret")
    client = TestClient(_build_app(manager))

    response = client.get(
        "/api/v1/auth/keys",
        headers={
            "X-API-Key": credential,
            "X-Admin-API-Key": "wrong-admin-secret",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin API key required"


def test_key_management_requires_explicit_admin_key_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, credential = _build_manager()
    monkeypatch.setattr(auth_module, "get_api_key_manager", lambda: manager)
    monkeypatch.setattr(auth_module.settings, "API_ADMIN_KEY", None)
    client = TestClient(_build_app(manager))

    response = client.get(
        "/api/v1/auth/keys",
        headers={"X-API-Key": credential},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin API key is not configured"
