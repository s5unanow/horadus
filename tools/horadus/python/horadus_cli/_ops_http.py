from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def http_get(
    url: str,
    *,
    timeout_seconds: float,
    headers: dict[str, str] | None,
    request_factory: Callable[..., Any],
    urlopen: Callable[..., Any],
    http_error_type: type[Any],
    url_error_type: type[Any],
) -> int:
    request = request_factory(url=url, method="GET", headers=headers or {})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            return int(response.status)
    except http_error_type as exc:
        return int(exc.code)
    except url_error_type:
        return 0


def http_get_json(
    url: str,
    *,
    timeout_seconds: float,
    headers: dict[str, str] | None,
    request_factory: Callable[..., Any],
    urlopen: Callable[..., Any],
    http_error_type: type[Any],
    url_error_type: type[Any],
) -> tuple[int, dict[str, object] | None]:
    request = request_factory(url=url, method="GET", headers=headers or {})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            status = int(response.status)
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                return status, payload
            return status, None
    except http_error_type as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return int(exc.code), payload
        return int(exc.code), None
    except (url_error_type, TimeoutError, json.JSONDecodeError):
        return 0, None
