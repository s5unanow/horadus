from __future__ import annotations

from collections.abc import Callable
from typing import Any


def agent_smoke_checks(
    *,
    base_url: str,
    timeout_seconds: float,
    api_key: str | None,
    http_get: Callable[..., int],
    http_get_json: Callable[..., tuple[int, dict[str, object] | None]],
    ok_exit_code: int,
    validation_error_exit_code: int,
) -> tuple[int, list[str], dict[str, Any]]:
    normalized_base_url = base_url.rstrip("/")
    lines: list[str] = []

    health_status = http_get(f"{normalized_base_url}/health", timeout_seconds=timeout_seconds)
    if 200 <= health_status < 300:
        lines.append(f"PASS /health {health_status}")
    else:
        lines.append(f"FAIL /health {health_status or 'connection_error'}")
        return (validation_error_exit_code, lines, {"health_status": health_status})

    openapi_status, openapi_payload = http_get_json(
        f"{normalized_base_url}/openapi.json",
        timeout_seconds=timeout_seconds,
    )
    if 200 <= openapi_status < 300:
        lines.append(f"PASS /openapi.json {openapi_status}")
    else:
        lines.append(f"FAIL /openapi.json {openapi_status or 'connection_error'}")
        return (
            validation_error_exit_code,
            lines,
            {"health_status": health_status, "openapi_status": openapi_status},
        )

    trend_headers = {"X-API-Key": api_key} if api_key else None
    trend_status = http_get(
        f"{normalized_base_url}/api/v1/trends",
        timeout_seconds=timeout_seconds,
        headers=trend_headers,
    )
    if 200 <= trend_status < 300:
        lines.append(f"PASS /api/v1/trends {trend_status}")
        return (
            ok_exit_code,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
            },
        )

    if trend_status in {401, 403} and not api_key:
        auth_hint = "unknown"
        if openapi_payload is not None:
            auth_hint = "openapi_security_present"
        lines.append(f"PASS /api/v1/trends {trend_status} auth_enforced_without_key ({auth_hint})")
        return (
            ok_exit_code,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
                "auth_hint": auth_hint,
            },
        )

    if trend_status in {401, 403} and api_key:
        lines.append(f"FAIL /api/v1/trends {trend_status} api_key_rejected")
        return (
            validation_error_exit_code,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
            },
        )

    lines.append(f"FAIL /api/v1/trends {trend_status or 'connection_error'}")
    return (
        validation_error_exit_code,
        lines,
        {
            "health_status": health_status,
            "openapi_status": openapi_status,
            "trend_status": trend_status,
        },
    )
