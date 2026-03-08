from __future__ import annotations

import builtins
import json
import sys
import types
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

import src.api.routes.health as health_module

pytestmark = pytest.mark.unit


def _install_fake_redis(
    monkeypatch: pytest.MonkeyPatch,
    *,
    client: object,
) -> None:
    redis_asyncio = types.ModuleType("redis.asyncio")
    redis_asyncio.from_url = MagicMock(return_value=client)

    redis_package = types.ModuleType("redis")
    redis_package.asyncio = redis_asyncio

    monkeypatch.setitem(sys.modules, "redis", redis_package)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio)


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
async def test_health_check_degrades_when_redis_unhealthy(mock_db_session, monkeypatch) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "unhealthy", "message": "redis unavailable"}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 5.0}

    async def fake_migration(_session):
        return {"status": "healthy"}

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)

    result = await health_module.health_check(session=mock_db_session)

    assert result.status == "degraded"
    assert result.checks["redis"]["status"] == "unhealthy"


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
async def test_health_check_is_unhealthy_when_database_fails_and_migrations_disabled(
    mock_db_session,
    monkeypatch,
) -> None:
    async def fake_db(_session):
        return {"status": "unhealthy", "message": "db unavailable"}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 1.0}

    fake_migration = MagicMock()

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", False)

    result = await health_module.health_check(session=mock_db_session)

    assert result.status == "unhealthy"
    assert result.checks["migrations"] == {
        "status": "skipped",
        "message": "Migration parity checks disabled by configuration",
    }
    fake_migration.assert_not_called()


@pytest.mark.asyncio
async def test_liveness_check_returns_alive() -> None:
    assert await health_module.liveness_check() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readiness_check_returns_ready_payload_on_success(
    mock_db_session,
    monkeypatch,
) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 1.0}

    async def fake_migration(_session):
        return {"status": "healthy"}

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)

    result = await health_module.readiness_check(session=mock_db_session)

    assert result == {"status": "ready"}


@pytest.mark.asyncio
async def test_readiness_check_returns_503_payload_on_dependency_failure(
    mock_db_session,
    monkeypatch,
) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "unhealthy", "message": "redis unavailable"}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 1.0}

    async def fake_migration(_session):
        return {"status": "healthy"}

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)

    result = await health_module.readiness_check(session=mock_db_session)

    assert result.status_code == 503
    assert json.loads(result.body.decode("utf-8")) == {
        "status": "not_ready",
        "checks": {
            "redis": {
                "status": "unhealthy",
                "message": "redis unavailable",
            }
        },
    }


@pytest.mark.asyncio
async def test_readiness_check_returns_ready_when_migration_checks_disabled(
    mock_db_session,
    monkeypatch,
) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 1.0}

    fake_migration = MagicMock()

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", False)

    result = await health_module.readiness_check(session=mock_db_session)

    assert result == {"status": "ready"}
    fake_migration.assert_not_called()


@pytest.mark.asyncio
async def test_readiness_check_returns_503_payload_on_exception(
    mock_db_session,
    monkeypatch,
) -> None:
    logger = MagicMock()

    async def fake_db(_session):
        raise RuntimeError("db blew up")

    monkeypatch.setattr(health_module, "logger", logger)
    monkeypatch.setattr(health_module, "check_database", fake_db)

    result = await health_module.readiness_check(session=mock_db_session)

    assert result.status_code == 503
    assert json.loads(result.body.decode("utf-8")) == {
        "status": "not_ready",
        "reason": "db blew up",
    }
    logger.warning.assert_called_once_with("Readiness check failed", error="db blew up")


@pytest.mark.asyncio
async def test_check_database_returns_healthy_payload(mock_db_session) -> None:
    result = await health_module.check_database(mock_db_session)

    assert result["status"] == "healthy"
    assert isinstance(result["latency_ms"], float)


@pytest.mark.asyncio
async def test_check_database_returns_unhealthy_payload_on_error(monkeypatch) -> None:
    logger = MagicMock()

    class _FailingSession:
        async def execute(self, _query) -> None:
            raise RuntimeError("db down")

    monkeypatch.setattr(health_module, "logger", logger)

    result = await health_module.check_database(_FailingSession())

    assert result == {"status": "unhealthy", "message": "db down"}
    logger.error.assert_called_once_with("Database health check failed", error="db down")


@pytest.mark.asyncio
async def test_check_redis_returns_healthy_payload(monkeypatch) -> None:
    class _Client:
        async def ping(self) -> None:
            return None

        async def close(self) -> None:
            return None

    _install_fake_redis(monkeypatch, client=_Client())
    monkeypatch.setattr(health_module.settings, "REDIS_URL", "redis://localhost:6379/0")

    result = await health_module.check_redis()

    assert result["status"] == "healthy"
    assert isinstance(result["latency_ms"], float)


@pytest.mark.asyncio
async def test_check_redis_returns_skipped_when_client_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "redis.asyncio":
            raise ImportError("missing redis")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = await health_module.check_redis()

    assert result == {"status": "skipped", "message": "Redis client not installed"}


@pytest.mark.asyncio
async def test_check_redis_returns_unhealthy_payload_on_error(monkeypatch) -> None:
    logger = MagicMock()

    class _Client:
        async def ping(self) -> None:
            raise RuntimeError("redis down")

        async def close(self) -> None:
            return None

    _install_fake_redis(monkeypatch, client=_Client())
    monkeypatch.setattr(health_module, "logger", logger)
    monkeypatch.setattr(health_module.settings, "REDIS_URL", "redis://localhost:6379/0")

    result = await health_module.check_redis()

    assert result == {"status": "unhealthy", "message": "redis down"}
    logger.warning.assert_called_once_with("Redis health check failed", error="redis down")


@pytest.mark.asyncio
async def test_check_worker_activity_returns_skipped_when_client_missing(
    monkeypatch,
) -> None:
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "redis.asyncio":
            raise ImportError("missing redis")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = await health_module.check_worker_activity()

    assert result == {"status": "skipped", "message": "Redis client not installed"}


@pytest.mark.asyncio
async def test_check_worker_activity_returns_unhealthy_when_missing_payload(
    monkeypatch,
) -> None:
    class _Client:
        async def get(self, _key: str) -> None:
            return None

        async def close(self) -> None:
            return None

    _install_fake_redis(monkeypatch, client=_Client())
    monkeypatch.setattr(health_module.settings, "REDIS_URL", "redis://localhost:6379/0")

    result = await health_module.check_worker_activity()

    assert result == {"status": "unhealthy", "message": "No worker heartbeat found"}


@pytest.mark.asyncio
async def test_check_worker_activity_returns_unhealthy_for_invalid_json(
    monkeypatch,
) -> None:
    class _Client:
        async def get(self, _key: str) -> str:
            return "{not-json}"

        async def close(self) -> None:
            return None

    _install_fake_redis(monkeypatch, client=_Client())
    monkeypatch.setattr(health_module.settings, "REDIS_URL", "redis://localhost:6379/0")

    result = await health_module.check_worker_activity()

    assert result == {
        "status": "unhealthy",
        "message": "Worker heartbeat payload is invalid JSON",
    }


@pytest.mark.asyncio
async def test_check_worker_activity_returns_unhealthy_for_missing_timestamp(
    monkeypatch,
) -> None:
    class _Client:
        async def get(self, _key: str) -> str:
            return json.dumps({"task": "workers.collect_rss"})

        async def close(self) -> None:
            return None

    _install_fake_redis(monkeypatch, client=_Client())
    monkeypatch.setattr(health_module.settings, "REDIS_URL", "redis://localhost:6379/0")

    result = await health_module.check_worker_activity()

    assert result == {
        "status": "unhealthy",
        "message": "Worker heartbeat timestamp missing",
    }


@pytest.mark.asyncio
async def test_check_worker_activity_returns_unhealthy_for_stale_heartbeat(
    monkeypatch,
) -> None:
    class _Client:
        async def get(self, _key: str) -> str:
            return json.dumps(
                {
                    "timestamp": (datetime.now(UTC) - timedelta(seconds=120)).isoformat(),
                    "task": "workers.collect_rss",
                    "status": "ok",
                }
            )

        async def close(self) -> None:
            return None

    _install_fake_redis(monkeypatch, client=_Client())
    monkeypatch.setattr(health_module.settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(health_module.settings, "WORKER_HEARTBEAT_STALE_SECONDS", 60)

    result = await health_module.check_worker_activity()

    assert result["status"] == "unhealthy"
    assert result["last_task"] == "workers.collect_rss"
    assert result["last_status"] == "ok"
    assert result["message"] == "Worker heartbeat stale (>60s)"


@pytest.mark.asyncio
async def test_check_worker_activity_returns_healthy_for_recent_heartbeat(
    monkeypatch,
) -> None:
    class _Client:
        async def get(self, _key: str) -> str:
            return json.dumps(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "task": "workers.collect_rss",
                    "status": "ok",
                }
            )

        async def close(self) -> None:
            return None

    _install_fake_redis(monkeypatch, client=_Client())
    monkeypatch.setattr(health_module.settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(health_module.settings, "WORKER_HEARTBEAT_STALE_SECONDS", 60)

    result = await health_module.check_worker_activity()

    assert result["status"] == "healthy"
    assert result["last_task"] == "workers.collect_rss"
    assert result["last_status"] == "ok"
    assert result["age_seconds"] >= 0


@pytest.mark.asyncio
async def test_check_worker_activity_returns_unhealthy_on_runtime_error(
    monkeypatch,
) -> None:
    logger = MagicMock()

    class _Client:
        async def get(self, _key: str) -> str:
            raise RuntimeError("redis unavailable")

        async def close(self) -> None:
            return None

    _install_fake_redis(monkeypatch, client=_Client())
    monkeypatch.setattr(health_module, "logger", logger)
    monkeypatch.setattr(health_module.settings, "REDIS_URL", "redis://localhost:6379/0")

    result = await health_module.check_worker_activity()

    assert result == {"status": "unhealthy", "message": "redis unavailable"}
    logger.warning.assert_called_once_with(
        "Worker heartbeat check failed", error="redis unavailable"
    )
