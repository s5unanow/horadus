from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.auth as auth_module
from src.api.middleware.auth import APIKeyAuthMiddleware
from src.core.api_key_manager import APIKeyManager

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

    app.include_router(auth_module.router, prefix="/api/v1/auth", tags=["Auth"])
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


def test_health_route_bypasses_auth() -> None:
    manager, _credential = _build_manager()
    client = TestClient(_build_app(manager))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rate_limit_returns_429() -> None:
    manager, credential = _build_manager(rate_limit_per_minute=1)
    client = TestClient(_build_app(manager))
    headers = {"X-API-Key": credential}

    first = client.get("/api/v1/protected", headers=headers)
    second = client.get("/api/v1/protected", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second.headers


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
