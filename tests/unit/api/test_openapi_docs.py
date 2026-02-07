from __future__ import annotations

import pytest

from src.api.main import create_app

pytestmark = pytest.mark.unit


def test_docs_and_openapi_routes_are_exposed() -> None:
    app = create_app()

    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"


def test_openapi_includes_api_key_auth_scheme() -> None:
    app = create_app()
    openapi = app.openapi()

    security_schemes = openapi["components"]["securitySchemes"]
    assert "ApiKeyAuth" in security_schemes
    assert security_schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert security_schemes["ApiKeyAuth"]["in"] == "header"
    assert security_schemes["ApiKeyAuth"]["name"] == "X-API-Key"


def test_all_operations_have_documentation_text() -> None:
    app = create_app()
    openapi = app.openapi()

    for _path, methods in openapi["paths"].items():
        for method, operation in methods.items():
            assert method in {"get", "post", "patch", "delete"}
            assert operation.get("summary")
            assert operation.get("description")
            assert operation.get("security")


def test_openapi_contains_request_response_examples() -> None:
    app = create_app()
    openapi = app.openapi()
    schemas = openapi["components"]["schemas"]

    assert "example" in schemas["HealthStatus"]
    assert "example" in schemas["SourceCreate"]
    assert "example" in schemas["TrendCreate"]
    assert "example" in schemas["ReportResponse"]
