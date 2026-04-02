"""
API authentication middleware using API keys.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.api_key_manager import APIKeyManager, get_api_key_manager
from src.core.config import settings

logger = structlog.get_logger(__name__)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate API keys and apply per-key rate limits."""

    def __init__(
        self,
        app: Any,
        *,
        manager: APIKeyManager | None = None,
        exempt_prefixes: tuple[str, ...] = (
            "/health/live",
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


def audit_privileged_action(
    *,
    request: Request,
    action: str,
    outcome: str,
    detail: str | None = None,
    **extra: Any,
) -> None:
    """Emit a structured audit log for privileged-route authorization."""
    client_host = request.client.host if request.client is not None else None
    logger.info(
        "Privileged API action",
        action=action,
        outcome=outcome,
        actor_api_key_id=getattr(request.state, "api_key_id", None),
        actor_api_key_name=getattr(request.state, "api_key_name", None),
        client_ip=client_host,
        request_method=request.method,
        request_path=request.url.path,
        detail=detail,
        **extra,
    )


def verify_privileged_access(request: Request) -> None:
    """Require the configured admin header in addition to baseline API-key auth."""
    configured_admin_key = (settings.API_ADMIN_KEY or "").strip()
    if not configured_admin_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key is not configured",
        )

    header_value = request.headers.get("X-Admin-API-Key", "").strip()
    if secrets.compare_digest(header_value, configured_admin_key):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin API key required",
    )


def require_privileged_access(action: str) -> Callable[[Request], None]:
    """Create a route dependency that enforces privileged-route access."""

    def _dependency(request: Request) -> None:
        try:
            verify_privileged_access(request)
        except HTTPException as exc:
            audit_privileged_action(
                request=request,
                action=action,
                outcome="denied",
                detail=str(exc.detail),
            )
            raise

        audit_privileged_action(
            request=request,
            action=action,
            outcome="authorized",
        )

    _dependency.__name__ = f"require_privileged_access_{action.replace('.', '_')}"
    return _dependency


def require_production_privileged_access(action: str) -> Callable[[Request], None]:
    """Require privileged access outside development environments."""
    privileged_dependency = require_privileged_access(action)

    def _dependency(request: Request) -> None:
        if settings.is_development:
            return
        privileged_dependency(request)

    _dependency.__name__ = f"require_production_privileged_access_{action.replace('.', '_')}"
    return _dependency
