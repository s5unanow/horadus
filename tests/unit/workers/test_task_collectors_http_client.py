from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import httpx
import pytest

from src.workers._task_collectors import _collector_http_client

pytestmark = pytest.mark.unit


def test_collector_http_client_uses_bounded_direct_connection_settings() -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def async_client_factory(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    deps = SimpleNamespace(
        httpx=SimpleNamespace(
            AsyncClient=async_client_factory,
            Limits=httpx.Limits,
            Timeout=httpx.Timeout,
        ),
        settings=SimpleNamespace(
            COLLECTOR_HTTP_CONNECT_TIMEOUT_SECONDS=7.0,
            COLLECTOR_HTTP_READ_TIMEOUT_SECONDS=23.0,
            COLLECTOR_HTTP_MAX_CONNECTIONS=8,
            COLLECTOR_HTTP_MAX_KEEPALIVE_CONNECTIONS=3,
        ),
    )

    assert _collector_http_client(deps=deps) is sentinel
    assert captured["follow_redirects"] is False
    assert captured["http2"] is False
    assert captured["trust_env"] is False
    timeout = cast("httpx.Timeout", captured["timeout"])
    limits = cast("httpx.Limits", captured["limits"])
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (7.0, 23.0, 7.0, 7.0)
    assert (limits.max_connections, limits.max_keepalive_connections) == (8, 3)
    assert limits.keepalive_expiry == 15.0
