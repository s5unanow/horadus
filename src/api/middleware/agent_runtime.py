"""
Agent runtime middleware for deterministic local smoke/debug flows.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

AGENT_UNHANDLED_EXCEPTION_FLAG = "_agent_unhandled_exception"


def trigger_agent_runtime_shutdown(
    app: Any,
    *,
    exit_code: int,
    reason: str,
) -> None:
    """
    Trigger runtime shutdown callback once while preserving highest exit code.
    """
    existing_exit_code = int(getattr(app.state, "agent_runtime_exit_code", 0))
    app.state.agent_runtime_exit_code = max(existing_exit_code, exit_code)

    already_triggered = bool(getattr(app.state, "agent_runtime_shutdown_triggered", False))
    if already_triggered:
        return

    app.state.agent_runtime_shutdown_triggered = True
    callback = getattr(app.state, "agent_runtime_shutdown_callback", None)
    if callable(callback):
        callback(exit_code, reason)


class AgentRuntimeMiddleware(BaseHTTPMiddleware):
    """
    Support deterministic agent runs: shutdown on request threshold or unhandled error.
    """

    def __init__(
        self,
        app: Any,
        *,
        exit_after_requests: int = 1,
        shutdown_on_error: bool = True,
    ) -> None:
        super().__init__(app)
        self._exit_after_requests = max(1, int(exit_after_requests))
        self._shutdown_on_error = shutdown_on_error
        self._request_count = 0

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        if self._shutdown_on_error and getattr(
            request.state, AGENT_UNHANDLED_EXCEPTION_FLAG, False
        ):
            trigger_agent_runtime_shutdown(
                request.app,
                exit_code=1,
                reason="unhandled_exception",
            )
            return response

        self._request_count += 1
        if self._request_count >= self._exit_after_requests:
            trigger_agent_runtime_shutdown(
                request.app,
                exit_code=0,
                reason="request_limit_reached",
            )

        return response
