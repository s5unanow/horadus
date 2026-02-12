from __future__ import annotations

import pytest

import src.api.routes.health as health_module

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_health_check_includes_worker_component(mock_db_session, monkeypatch) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 5.0, "last_task": "workers.collect_rss"}

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)

    result = await health_module.health_check(session=mock_db_session)

    assert result.status == "healthy"
    assert result.checks["worker"]["status"] == "healthy"
    assert result.checks["worker"]["last_task"] == "workers.collect_rss"


@pytest.mark.asyncio
async def test_health_check_degrades_when_worker_unhealthy(mock_db_session, monkeypatch) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {"status": "unhealthy", "message": "heartbeat stale"}

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)

    result = await health_module.health_check(session=mock_db_session)

    assert result.status == "degraded"
    assert result.checks["worker"]["status"] == "unhealthy"
