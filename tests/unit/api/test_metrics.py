from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.middleware.auth as auth_middleware_module
import src.api.routes.metrics as metrics_module
from src.api.middleware.auth import APIKeyAuthMiddleware
from src.core.api_key_manager import APIKeyManager
from src.storage.database import get_session

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_payload() -> None:
    response = await metrics_module.get_metrics()
    body = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "text/plain" in response.media_type
    assert "ingestion_items_total" in body
    assert "llm_api_calls_total" in body
    assert "worker_errors_total" in body


def _build_manager() -> tuple[APIKeyManager, str]:
    manager = APIKeyManager(
        auth_enabled=True,
        legacy_api_key=None,
        static_api_keys=[],
        default_rate_limit_per_minute=5,
    )
    _record, raw_credential = manager.create_key(name="test-client")
    return (manager, raw_credential)


def _build_metrics_app(*, exempt_prefixes: tuple[str, ...]) -> tuple[TestClient, str]:
    manager, credential = _build_manager()
    app = FastAPI()
    app.add_middleware(
        APIKeyAuthMiddleware,
        manager=manager,
        exempt_prefixes=exempt_prefixes,
    )
    app.include_router(metrics_module.router)

    async def _override_get_session():
        yield None

    app.dependency_overrides[get_session] = _override_get_session
    return (TestClient(app), credential)


def test_metrics_route_requires_privileged_access_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, credential = _build_metrics_app(exempt_prefixes=("/health/live",))
    monkeypatch.setattr(auth_middleware_module.settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(auth_middleware_module.settings, "API_ADMIN_KEY", "admin-secret")

    no_auth_response = client.get("/metrics")
    api_key_only_response = client.get("/metrics", headers={"X-API-Key": credential})
    privileged_response = client.get(
        "/metrics",
        headers={
            "X-API-Key": credential,
            "X-Admin-API-Key": "admin-secret",
        },
    )

    assert no_auth_response.status_code == 401
    assert api_key_only_response.status_code == 403
    assert privileged_response.status_code == 200
    assert "ingestion_items_total" in privileged_response.text


def test_metrics_route_stays_open_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _credential = _build_metrics_app(exempt_prefixes=("/health", "/metrics"))
    monkeypatch.setattr(auth_middleware_module.settings, "ENVIRONMENT", "development")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "ingestion_items_total" in response.text
