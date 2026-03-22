from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

import src.api.deps as deps_module
import src.api.main as main_module
from src.api.deps import DBSession
from src.api.middleware.agent_runtime import AgentRuntimeMiddleware
from src.api.middleware.auth import APIKeyAuthMiddleware

pytestmark = pytest.mark.unit


def test_dbsession_alias_wraps_async_session_dependency() -> None:
    assert DBSession.__origin__ is AsyncSession
    dependency = DBSession.__metadata__[0]
    assert dependency.dependency is deps_module.get_session


def test_create_app_registers_core_middleware_routes_and_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_logging = MagicMock()
    configure_tracing = MagicMock()
    monkeypatch.setattr(main_module, "configure_logging", configure_logging)
    monkeypatch.setattr(main_module, "configure_tracing", configure_tracing)
    monkeypatch.setattr(main_module.settings, "RUNTIME_PROFILE", "server")
    monkeypatch.setattr(main_module.settings, "AGENT_MODE", False)

    app = main_module.create_app()

    configure_logging.assert_called_once_with()
    configure_tracing.assert_called_once_with(fastapi_app=app)
    middleware_classes = {middleware.cls for middleware in app.user_middleware}
    assert APIKeyAuthMiddleware in middleware_classes
    assert AgentRuntimeMiddleware not in middleware_classes
    auth_middleware = next(
        middleware for middleware in app.user_middleware if middleware.cls is APIKeyAuthMiddleware
    )
    assert auth_middleware.kwargs["exempt_prefixes"] == (
        "/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    )
    route_paths = {route.path for route in app.routes}
    assert "/health" in route_paths
    assert "/metrics" in route_paths
    assert "/api/v1/trends" in route_paths
    assert "/api/v1/events" in route_paths


def test_create_app_hides_docs_routes_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "configure_logging", MagicMock())
    monkeypatch.setattr(main_module, "configure_tracing", MagicMock())
    monkeypatch.setattr(main_module.settings, "RUNTIME_PROFILE", "server")
    monkeypatch.setattr(main_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(main_module.settings, "ENVIRONMENT", "staging")

    app = main_module.create_app()

    auth_middleware = next(
        middleware for middleware in app.user_middleware if middleware.cls is APIKeyAuthMiddleware
    )
    assert auth_middleware.kwargs["exempt_prefixes"] == ("/health", "/metrics")
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_create_app_enables_agent_runtime_middleware_for_agent_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "configure_logging", MagicMock())
    monkeypatch.setattr(main_module, "configure_tracing", MagicMock())
    monkeypatch.setattr(main_module.settings, "RUNTIME_PROFILE", "agent")
    monkeypatch.setattr(main_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(main_module.settings, "AGENT_EXIT_AFTER_REQUESTS", 7)
    monkeypatch.setattr(main_module.settings, "AGENT_SHUTDOWN_ON_ERROR", True)

    app = main_module.create_app()

    middleware_entries = [
        entry for entry in app.user_middleware if entry.cls is AgentRuntimeMiddleware
    ]
    assert len(middleware_entries) == 1
    assert middleware_entries[0].kwargs["exit_after_requests"] == 7
    assert middleware_entries[0].kwargs["shutdown_on_error"] is True
    assert app.state.agent_runtime_exit_code == 0
    assert app.state.agent_runtime_shutdown_triggered is False


@pytest.mark.asyncio
async def test_generic_exception_handler_returns_500_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    monkeypatch.setattr(main_module.settings, "RUNTIME_PROFILE", "server")
    monkeypatch.setattr(main_module.settings, "AGENT_MODE", False)
    main_module.register_exception_handlers(app)

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/boom",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "app": app,
        }
    )
    response = await app.exception_handlers[Exception](request, RuntimeError("boom"))

    assert response.status_code == 500
    assert (
        response.body
        == b'{"error":"internal_server_error","message":"An unexpected error occurred"}'
    )


@pytest.mark.asyncio
async def test_generic_exception_handler_triggers_agent_shutdown_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    shutdown = MagicMock()
    monkeypatch.setattr(main_module.settings, "RUNTIME_PROFILE", "agent")
    monkeypatch.setattr(main_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(main_module.settings, "AGENT_SHUTDOWN_ON_ERROR", True)
    monkeypatch.setattr(main_module, "trigger_agent_runtime_shutdown", shutdown)
    main_module.register_exception_handlers(app)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/agent-error",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "app": app,
        }
    )
    response = await app.exception_handlers[Exception](request, RuntimeError("boom"))

    assert response.status_code == 500
    assert getattr(request.state, main_module.AGENT_UNHANDLED_EXCEPTION_FLAG) is True
    shutdown.assert_called_once_with(app, exit_code=1, reason="unhandled_exception")


class _HealthySession:
    async def execute(self, _query: object) -> None:
        return None


class _HealthySessionContext:
    async def __aenter__(self) -> _HealthySession:
        return _HealthySession()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _healthy_session_maker() -> _HealthySessionContext:
    return _HealthySessionContext()


@pytest.mark.asyncio
async def test_lifespan_logs_when_migration_check_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()
    dispose = AsyncMock()
    monkeypatch.setattr(main_module, "logger", logger)
    monkeypatch.setattr(main_module, "async_session_maker", _healthy_session_maker)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", False)
    monkeypatch.setattr(main_module, "engine", SimpleNamespace(dispose=dispose))

    async with main_module.lifespan(main_module.app):
        pass

    logger.info.assert_any_call("Migration parity check disabled by configuration")
    logger.info.assert_any_call("Database connection verified")
    dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_logs_healthy_migration_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()
    dispose = AsyncMock()

    async def fake_check(_session: object) -> dict[str, str]:
        return {"status": "healthy", "current_revision": "abc", "expected_head": "abc"}

    monkeypatch.setattr(main_module, "logger", logger)
    monkeypatch.setattr(main_module, "async_session_maker", _healthy_session_maker)
    monkeypatch.setattr(main_module, "check_migration_parity", fake_check)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_STRICT_STARTUP", False)
    monkeypatch.setattr(main_module, "engine", SimpleNamespace(dispose=dispose))

    async with main_module.lifespan(main_module.app):
        pass

    logger.info.assert_any_call(
        "Migration parity verified",
        current_revision="abc",
        expected_head="abc",
    )
    dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_logs_unhealthy_migration_parity_without_strict_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()
    dispose = AsyncMock()

    async def fake_check(_session: object) -> dict[str, str]:
        return {"status": "drifted", "message": "head mismatch"}

    monkeypatch.setattr(main_module, "logger", logger)
    monkeypatch.setattr(main_module, "async_session_maker", _healthy_session_maker)
    monkeypatch.setattr(main_module, "check_migration_parity", fake_check)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_STRICT_STARTUP", False)
    monkeypatch.setattr(main_module, "engine", SimpleNamespace(dispose=dispose))

    async with main_module.lifespan(main_module.app):
        pass

    logger.warning.assert_any_call(
        "Migration parity check failed",
        details={"status": "drifted", "message": "head mismatch"},
    )
    dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_raises_on_unhealthy_migration_parity_in_strict_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()

    async def fake_check(_session: object) -> dict[str, str]:
        return {"status": "drifted", "message": "head mismatch"}

    monkeypatch.setattr(main_module, "logger", logger)
    monkeypatch.setattr(main_module, "async_session_maker", _healthy_session_maker)
    monkeypatch.setattr(main_module, "check_migration_parity", fake_check)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_STRICT_STARTUP", True)

    with pytest.raises(RuntimeError, match="Migration parity check failed: head mismatch"):
        async with main_module.lifespan(main_module.app):
            pass

    logger.warning.assert_any_call(
        "Migration parity check failed",
        details={"status": "drifted", "message": "head mismatch"},
    )


class _FailingSessionContext:
    async def __aenter__(self) -> _HealthySession:
        raise RuntimeError("db unavailable")

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _failing_session_maker() -> _FailingSessionContext:
    return _FailingSessionContext()


@pytest.mark.asyncio
async def test_lifespan_logs_and_raises_when_database_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()
    monkeypatch.setattr(main_module, "logger", logger)
    monkeypatch.setattr(main_module, "async_session_maker", _failing_session_maker)

    with pytest.raises(RuntimeError, match="db unavailable"):
        async with main_module.lifespan(main_module.app):
            pass

    logger.error.assert_called_once_with("Database connection failed", error="db unavailable")


def test_main_module_runs_uvicorn_for_non_agent_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_mock = MagicMock()
    fake_uvicorn = types.SimpleNamespace(run=run_mock)

    monkeypatch.setattr(main_module.settings, "RUNTIME_PROFILE", "server")
    monkeypatch.setattr(main_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(main_module.settings, "API_HOST", "127.0.0.1")
    monkeypatch.setattr(main_module.settings, "API_PORT", 9999)
    monkeypatch.setattr(main_module.settings, "API_RELOAD", False)
    monkeypatch.setattr(main_module.settings, "LOG_LEVEL", "INFO")

    main_module.run_development_server(uvicorn_module=fake_uvicorn)

    run_mock.assert_called_once_with(
        "src.api.main:app",
        host="127.0.0.1",
        port=9999,
        reload=False,
        log_level="info",
    )


def test_main_module_uses_agent_server_shutdown_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_mock = MagicMock(return_value="config")
    app = FastAPI()
    app.state.agent_runtime_exit_code = 0

    class _FakeServer:
        def __init__(self, config: object) -> None:
            assert config == "config"
            self.should_exit = False

        def run(self) -> None:
            callback = app.state.agent_runtime_shutdown_callback
            callback(exit_code=2, reason="test")

    fake_uvicorn = types.SimpleNamespace(Config=config_mock, Server=_FakeServer)

    monkeypatch.setattr(main_module.settings, "RUNTIME_PROFILE", "agent")
    monkeypatch.setattr(main_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(main_module.settings, "API_HOST", "127.0.0.1")
    monkeypatch.setattr(main_module.settings, "API_PORT", 8001)
    monkeypatch.setattr(main_module.settings, "API_RELOAD", False)
    monkeypatch.setattr(main_module.settings, "AGENT_DEFAULT_LOG_LEVEL", "WARNING")
    monkeypatch.setattr(main_module, "app", app)

    with pytest.raises(SystemExit) as exc_info:
        main_module.run_development_server(uvicorn_module=fake_uvicorn)

    assert exc_info.value.code == 2
    config_mock.assert_called_once_with(
        "src.api.main:app",
        host="127.0.0.1",
        port=8001,
        reload=False,
        log_level="warning",
        access_log=False,
    )


def test_main_script_entrypoint_invokes_development_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_mock = MagicMock()
    fake_uvicorn = types.SimpleNamespace(run=run_mock)

    monkeypatch.setattr(main_module.settings, "RUNTIME_PROFILE", "server")
    monkeypatch.setattr(main_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(main_module.settings, "API_HOST", "127.0.0.1")
    monkeypatch.setattr(main_module.settings, "API_PORT", 9000)
    monkeypatch.setattr(main_module.settings, "API_RELOAD", False)
    monkeypatch.setattr(main_module.settings, "LOG_LEVEL", "INFO")
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    runpy.run_path(str(Path(main_module.__file__)), run_name="__main__")

    run_mock.assert_called_once_with(
        "src.api.main:app",
        host="127.0.0.1",
        port=9000,
        reload=False,
        log_level="info",
    )
