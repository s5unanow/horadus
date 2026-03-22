from __future__ import annotations

import pytest

import tools.horadus.python.horadus_cli.ops_commands as ops_module
from tools.horadus.python.horadus_cli.result import ExitCode

pytestmark = pytest.mark.unit


def test_agent_smoke_helpers_cover_failure_and_auth_hint_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ops_module, "_http_get", lambda url, **_kwargs: 500 if url.endswith("/health") else 0
    )
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines == ["FAIL /health 500"]
    assert data == {"health_status": 500}

    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 401,
    }
    monkeypatch.setattr(ops_module, "_http_get", lambda url, **_kwargs: statuses[url])
    monkeypatch.setattr(ops_module, "_http_get_json", lambda _url, **_kwargs: (200, None))

    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )

    assert exit_code == ExitCode.OK
    assert lines[-1].endswith("auth_enforced_without_key (unknown)")
    assert data["auth_hint"] == "unknown"

    monkeypatch.setattr(ops_module, "_http_get", lambda _url, **_kwargs: 200)
    monkeypatch.setattr(ops_module, "_http_get_json", lambda _url, **_kwargs: (0, None))
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines[-1] == "FAIL /openapi.json connection_error"
    assert data == {"health_status": 200, "openapi_status": 0}

    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 401,
    }
    monkeypatch.setattr(ops_module, "_http_get", lambda url, **_kwargs: statuses[url])
    monkeypatch.setattr(ops_module, "_http_get_json", lambda _url, **_kwargs: (404, None))
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )
    assert exit_code == ExitCode.OK
    assert lines[1] == "PASS /openapi.json unavailable_by_policy 404"
    assert lines[-1].endswith("auth_enforced_without_key (openapi_restricted_or_disabled)")
    assert data["openapi_status"] == 404

    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 403,
    }
    monkeypatch.setattr(ops_module, "_http_get", lambda url, **_kwargs: statuses[url])
    monkeypatch.setattr(
        ops_module, "_http_get_json", lambda _url, **_kwargs: (200, {"openapi": True})
    )
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key="stub",  # pragma: allowlist secret
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines[-1] == "FAIL /api/v1/trends 403 api_key_rejected"
    assert data["trend_status"] == 403

    monkeypatch.setattr(ops_module, "_http_get", lambda url, **_kwargs: statuses[url])
    monkeypatch.setattr(ops_module, "_http_get_json", lambda _url, **_kwargs: (403, None))
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines[-1] == "FAIL /openapi.json 403"
    assert data == {"health_status": 200, "openapi_status": 403}

    statuses["http://127.0.0.1:8000/api/v1/trends"] = 0
    monkeypatch.setattr(
        ops_module, "_http_get_json", lambda _url, **_kwargs: (200, {"openapi": True})
    )
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key="stub",  # pragma: allowlist secret
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines[-1] == "FAIL /api/v1/trends connection_error"
    assert data["trend_status"] == 0
