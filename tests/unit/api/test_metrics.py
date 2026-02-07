from __future__ import annotations

import pytest

from src.api.routes.metrics import get_metrics

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_payload() -> None:
    response = await get_metrics()
    body = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "text/plain" in response.media_type
    assert "ingestion_items_total" in body
    assert "llm_api_calls_total" in body
    assert "worker_errors_total" in body
