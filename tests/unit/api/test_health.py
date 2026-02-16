from __future__ import annotations

import json

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

    async def fake_migration(_session):
        return {
            "status": "healthy",
            "current_revision": "0008_vector_index_profile",
            "expected_head": "0008_vector_index_profile",
        }

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)

    result = await health_module.health_check(session=mock_db_session)

    assert result.status == "healthy"
    assert result.checks["worker"]["status"] == "healthy"
    assert result.checks["worker"]["last_task"] == "workers.collect_rss"
    assert result.checks["migrations"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_degrades_when_worker_unhealthy(mock_db_session, monkeypatch) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {"status": "unhealthy", "message": "heartbeat stale"}

    async def fake_migration(_session):
        return {"status": "healthy"}

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)

    result = await health_module.health_check(session=mock_db_session)

    assert result.status == "degraded"
    assert result.checks["worker"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_check_degrades_when_migrations_drift(mock_db_session, monkeypatch) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 1.0}

    async def fake_migration(_session):
        return {
            "status": "unhealthy",
            "message": "Database schema revision drift detected",
            "expected_head": "0008_vector_index_profile",
            "current_revision": "0007_evidence_decay_fields",
        }

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)

    result = await health_module.health_check(session=mock_db_session)

    assert result.status == "degraded"
    assert result.checks["migrations"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_readiness_check_returns_ready_payload_on_success(mock_db_session) -> None:
    result = await health_module.readiness_check(session=mock_db_session)

    assert result == {"status": "ready"}


@pytest.mark.asyncio
async def test_readiness_check_returns_503_payload_on_failure(mock_db_session, monkeypatch) -> None:
    async def fail_execute(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(mock_db_session, "execute", fail_execute)

    result = await health_module.readiness_check(session=mock_db_session)

    assert result.status_code == 503
    assert json.loads(result.body.decode("utf-8")) == {
        "status": "not_ready",
        "reason": "database unavailable",
    }
