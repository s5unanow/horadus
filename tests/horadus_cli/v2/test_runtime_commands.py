from __future__ import annotations

import asyncio
import os

import pytest

import tools.horadus.python.horadus_app_cli_runtime as runtime_module
import tools.horadus.python.horadus_cli.ops_commands as ops_module

pytestmark = pytest.mark.unit


def _run_doctor(*, timeout_seconds: float) -> int:
    _data, lines, exit_code = runtime_module._collect_doctor(timeout_seconds)
    for line in lines:
        print(line)
    return int(exit_code)


def test_run_agent_smoke_passes_when_server_enforces_auth_and_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 401,
    }

    def fake_http_get(url: str, *, timeout_seconds: float, headers=None) -> int:
        _ = timeout_seconds
        _ = headers
        return statuses[url]

    def fake_http_get_json(
        url: str,
        *,
        timeout_seconds: float,
        headers=None,
    ) -> tuple[int, dict[str, object] | None]:
        _ = timeout_seconds
        _ = headers
        assert url == "http://127.0.0.1:8000/openapi.json"
        return (200, {"openapi": "3.1.0"})

    monkeypatch.setattr(ops_module, "_http_get", fake_http_get)
    monkeypatch.setattr(ops_module, "_http_get_json", fake_http_get_json)

    result = ops_module._run_agent_smoke(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=5.0,
        api_key=None,
    )

    assert result == 0


def test_run_agent_smoke_fails_when_api_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 403,
    }

    def fake_http_get(url: str, *, timeout_seconds: float, headers=None) -> int:
        _ = timeout_seconds
        assert headers == {"X-API-Key": "invalid-token"} or headers is None
        return statuses[url]

    def fake_http_get_json(
        url: str,
        *,
        timeout_seconds: float,
        headers=None,
    ) -> tuple[int, dict[str, object] | None]:
        _ = timeout_seconds
        _ = headers
        assert url == "http://127.0.0.1:8000/openapi.json"
        return (200, {"openapi": "3.1.0"})

    monkeypatch.setattr(ops_module, "_http_get", fake_http_get)
    monkeypatch.setattr(ops_module, "_http_get_json", fake_http_get_json)

    result = ops_module._run_agent_smoke(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=5.0,
        api_key="invalid-token",  # pragma: allowlist secret
    )

    assert result == 2


def test_run_agent_smoke_passes_when_auth_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 200,
    }

    def fake_http_get(url: str, *, timeout_seconds: float, headers=None) -> int:
        _ = timeout_seconds
        _ = headers
        return statuses[url]

    def fake_http_get_json(
        url: str,
        *,
        timeout_seconds: float,
        headers=None,
    ) -> tuple[int, dict[str, object] | None]:
        _ = url
        _ = timeout_seconds
        _ = headers
        return (200, {"openapi": "3.1.0"})

    monkeypatch.setattr(ops_module, "_http_get", fake_http_get)
    monkeypatch.setattr(ops_module, "_http_get_json", fake_http_get_json)

    result = ops_module._run_agent_smoke(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=5.0,
        api_key=None,
    )

    assert result == 0


def test_run_agent_smoke_fails_when_server_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_http_get(url: str, *, timeout_seconds: float, headers=None) -> int:
        _ = url
        _ = timeout_seconds
        _ = headers
        return 0

    def fake_http_get_json(
        url: str,
        *,
        timeout_seconds: float,
        headers=None,
    ) -> tuple[int, dict[str, object] | None]:
        _ = url
        _ = timeout_seconds
        _ = headers
        return (0, None)

    monkeypatch.setattr(ops_module, "_http_get", fake_http_get)
    monkeypatch.setattr(ops_module, "_http_get_json", fake_http_get_json)

    result = ops_module._run_agent_smoke(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=5.0,
        api_key=None,
    )

    assert result == 2


def test_run_doctor_fails_when_required_hooks_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "pre-commit").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    os.chmod(hooks_dir / "pre-commit", 0o755)

    result = _run_doctor(timeout_seconds=0.2)

    assert result == 2


def test_run_doctor_passes_when_required_hooks_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime_module.settings, "DATABASE_URL", "")
    monkeypatch.setattr(runtime_module.settings, "REDIS_URL", "")
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)

    for hook_name in ("pre-commit", "pre-push", "commit-msg"):
        path = hooks_dir / hook_name
        path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        os.chmod(path, 0o755)

    result = _run_doctor(timeout_seconds=0.2)

    assert result == 0


def test_doctor_check_database_skips_when_database_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_module.settings, "DATABASE_URL", "")
    status, message = asyncio.run(runtime_module._doctor_check_database(0.2))
    assert status == "SKIP"
    assert "DATABASE_URL" in message


def test_doctor_check_redis_skips_when_redis_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_module.settings, "REDIS_URL", "")
    status, message = asyncio.run(runtime_module._doctor_check_redis(0.2))
    assert status == "SKIP"
    assert "REDIS_URL" in message


def test_run_doctor_returns_failure_on_safety_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(runtime_module.settings, "RUNTIME_PROFILE", "agent")
    monkeypatch.setattr(runtime_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(runtime_module.settings, "AGENT_ALLOW_NON_LOOPBACK", False)
    monkeypatch.setattr(runtime_module.settings, "API_HOST", "0.0.0.0")
    monkeypatch.setattr(runtime_module.settings, "API_AUTH_ENABLED", True)

    async def fake_doctor_check_database(_timeout_seconds: float) -> tuple[str, str]:
        return ("PASS", "ok")

    async def fake_doctor_check_redis(_timeout_seconds: float) -> tuple[str, str]:
        return ("PASS", "ok")

    monkeypatch.setattr(runtime_module, "_doctor_check_database", fake_doctor_check_database)
    monkeypatch.setattr(runtime_module, "_doctor_check_redis", fake_doctor_check_redis)

    result = _run_doctor(timeout_seconds=0.2)
    assert result == 2
