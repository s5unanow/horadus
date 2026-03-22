from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import src.api.main as main_module

pytestmark = pytest.mark.unit


def _app_for_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    environment: str,
) -> main_module.FastAPI:
    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(main_module, "lifespan", _noop_lifespan)
    monkeypatch.setattr(main_module.settings, "ENVIRONMENT", environment)
    return main_module.create_app()


def test_docs_and_openapi_routes_are_exposed_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_for_environment(monkeypatch, environment="development")

    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"

    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    assert openapi_response.json()["openapi"]


def test_docs_and_openapi_routes_are_hidden_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_for_environment(monkeypatch, environment="staging")

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None

    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_openapi_includes_api_key_auth_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_for_environment(monkeypatch, environment="development")
    openapi = app.openapi()

    security_schemes = openapi["components"]["securitySchemes"]
    assert "ApiKeyAuth" in security_schemes
    assert security_schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert security_schemes["ApiKeyAuth"]["in"] == "header"
    assert security_schemes["ApiKeyAuth"]["name"] == "X-API-Key"


def test_all_operations_have_documentation_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_for_environment(monkeypatch, environment="development")
    openapi = app.openapi()

    for _path, methods in openapi["paths"].items():
        for method, operation in methods.items():
            assert method in {"get", "post", "patch", "delete"}
            assert operation.get("summary")
            assert operation.get("description")
            assert operation.get("security")


def test_openapi_contains_request_response_examples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_for_environment(monkeypatch, environment="development")
    openapi = app.openapi()
    schemas = openapi["components"]["schemas"]

    assert "example" in schemas["HealthStatus"]
    assert "example" in schemas["SourceCreate"]
    assert "example" in schemas["TrendCreate"]
    assert "example" in schemas["ReportResponse"]
