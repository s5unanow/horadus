"""
API authentication middleware using API keys.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.api_key_manager import APIKeyManager, get_api_key_manager


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate API keys and apply per-key rate limits."""

    def __init__(
        self,
        app: Any,
        *,
        manager: APIKeyManager | None = None,
        exempt_prefixes: tuple[str, ...] = (
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ),
    ) -> None:
        super().__init__(app)
        self._manager = manager if manager is not None else get_api_key_manager()
        self._exempt_prefixes = exempt_prefixes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self._exempt_prefixes):
            return await call_next(request)

        if not self._manager.auth_required:
            return await call_next(request)

        raw_key = request.headers.get("X-API-Key", "").strip()
        if not raw_key:
            return self._error_response(
                status_code=HTTPStatus.UNAUTHORIZED,
                message="Missing API key",
            )

        record = self._manager.authenticate(raw_key)
        if record is None:
            return self._error_response(
                status_code=HTTPStatus.UNAUTHORIZED,
                message="Invalid API key",
            )

        allowed, retry_after = self._manager.check_rate_limit(record.id)
        if not allowed:
            response = self._error_response(
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
                message="Rate limit exceeded",
            )
            if retry_after is not None:
                response.headers["Retry-After"] = str(retry_after)
            return response

        request.state.api_key_id = record.id
        request.state.api_key_name = record.name
        return await call_next(request)

    @staticmethod
    def _error_response(*, status_code: HTTPStatus, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=int(status_code),
            content={
                "error": status_code.phrase.lower().replace(" ", "_"),
                "message": message,
            },
        )
