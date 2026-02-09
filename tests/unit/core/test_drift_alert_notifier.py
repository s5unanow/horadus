from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from src.core.drift_alert_notifier import DriftAlertWebhookNotifier

pytestmark = pytest.mark.unit


def _build_alerts() -> list[dict[str, object]]:
    return [
        {
            "alert_type": "mean_brier_drift",
            "severity": "warning",
            "metric_name": "mean_brier_score",
            "metric_value": 0.22,
            "threshold": 0.2,
            "sample_size": 34,
            "message": "Threshold exceeded.",
        }
    ]


@pytest.mark.asyncio
async def test_notify_posts_payload_when_configured() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["event_type"] == "calibration_drift_alerts"
        assert payload["alert_count"] == 1
        return httpx.Response(200, json={"ok": True})

    notifier = DriftAlertWebhookNotifier(
        webhook_url="https://example.test/drift-alerts",
        timeout_seconds=5.0,
        max_retries=2,
        backoff_seconds=0.1,
        transport=httpx.MockTransport(handler),
    )

    delivered = await notifier.notify(
        trend_scope="all_trends",
        generated_at=datetime(2026, 2, 9, 0, 0, tzinfo=UTC),
        alerts=_build_alerts(),
    )

    assert delivered is True
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_notify_retries_on_retryable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    attempt_counter = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_counter["count"] += 1
        if attempt_counter["count"] == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, request=request)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("src.core.drift_alert_notifier.asyncio.sleep", fake_sleep)

    notifier = DriftAlertWebhookNotifier(
        webhook_url="https://example.test/drift-alerts",
        timeout_seconds=5.0,
        max_retries=2,
        backoff_seconds=0.1,
        transport=httpx.MockTransport(handler),
    )

    delivered = await notifier.notify(
        trend_scope="all_trends",
        generated_at=datetime(2026, 2, 9, 0, 0, tzinfo=UTC),
        alerts=_build_alerts(),
    )

    assert delivered is True
    assert attempt_counter["count"] == 2
    assert delays == [0.1]


@pytest.mark.asyncio
async def test_notify_stops_on_non_retryable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    attempt_counter = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_counter["count"] += 1
        return httpx.Response(400, request=request)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("src.core.drift_alert_notifier.asyncio.sleep", fake_sleep)

    notifier = DriftAlertWebhookNotifier(
        webhook_url="https://example.test/drift-alerts",
        timeout_seconds=5.0,
        max_retries=3,
        backoff_seconds=0.1,
        transport=httpx.MockTransport(handler),
    )

    delivered = await notifier.notify(
        trend_scope="all_trends",
        generated_at=datetime(2026, 2, 9, 0, 0, tzinfo=UTC),
        alerts=_build_alerts(),
    )

    assert delivered is False
    assert attempt_counter["count"] == 1
    assert delays == []


@pytest.mark.asyncio
async def test_notify_retries_network_errors_until_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_counter = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_counter["count"] += 1
        raise httpx.ConnectError("network_down", request=request)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("src.core.drift_alert_notifier.asyncio.sleep", fake_sleep)

    notifier = DriftAlertWebhookNotifier(
        webhook_url="https://example.test/drift-alerts",
        timeout_seconds=5.0,
        max_retries=2,
        backoff_seconds=0.25,
        transport=httpx.MockTransport(handler),
    )

    delivered = await notifier.notify(
        trend_scope="all_trends",
        generated_at=datetime(2026, 2, 9, 0, 0, tzinfo=UTC),
        alerts=_build_alerts(),
    )

    assert delivered is False
    assert attempt_counter["count"] == 3
    assert delays == [0.25, 0.5]
