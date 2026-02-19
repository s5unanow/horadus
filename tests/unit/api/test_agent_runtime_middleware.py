from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.api.middleware.agent_runtime import (
    AgentRuntimeMiddleware,
    trigger_agent_runtime_shutdown,
)

pytestmark = pytest.mark.unit


def test_agent_runtime_middleware_triggers_shutdown_after_request_limit() -> None:
    app = FastAPI()
    shutdown_calls: list[tuple[int, str]] = []

    app.state.agent_runtime_exit_code = 0
    app.state.agent_runtime_shutdown_triggered = False
    app.state.agent_runtime_shutdown_callback = lambda exit_code, reason: shutdown_calls.append(
        (exit_code, reason)
    )
    app.add_middleware(AgentRuntimeMiddleware, exit_after_requests=2, shutdown_on_error=True)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    first = client.get("/ok")
    second = client.get("/ok")

    assert first.status_code == 200
    assert second.status_code == 200
    assert shutdown_calls == [(0, "request_limit_reached")]


def test_agent_runtime_middleware_triggers_error_shutdown_on_unhandled_exception() -> None:
    app = FastAPI()
    shutdown_calls: list[tuple[int, str]] = []

    app.state.agent_runtime_exit_code = 0
    app.state.agent_runtime_shutdown_triggered = False
    app.state.agent_runtime_shutdown_callback = lambda exit_code, reason: shutdown_calls.append(
        (exit_code, reason)
    )
    app.add_middleware(AgentRuntimeMiddleware, exit_after_requests=100, shutdown_on_error=True)

    @app.exception_handler(Exception)
    async def error_handler(request: Request, _exc: Exception) -> JSONResponse:
        trigger_agent_runtime_shutdown(
            request.app,
            exit_code=1,
            reason="unhandled_exception",
        )
        return JSONResponse(status_code=500, content={"error": "internal_server_error"})

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert shutdown_calls == [(1, "unhandled_exception")]


def test_trigger_agent_runtime_shutdown_preserves_highest_exit_code() -> None:
    app = FastAPI()
    shutdown_calls: list[tuple[int, str]] = []
    app.state.agent_runtime_exit_code = 0
    app.state.agent_runtime_shutdown_triggered = False
    app.state.agent_runtime_shutdown_callback = lambda exit_code, reason: shutdown_calls.append(
        (exit_code, reason)
    )

    trigger_agent_runtime_shutdown(app, exit_code=0, reason="request_limit_reached")
    trigger_agent_runtime_shutdown(app, exit_code=1, reason="unhandled_exception")

    assert app.state.agent_runtime_exit_code == 1
    assert shutdown_calls == [(0, "request_limit_reached")]
