from __future__ import annotations

import builtins
import json
import sys
import types
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.health as health_module
from src.api.middleware.auth import APIKeyAuthMiddleware
from src.core.api_key_manager import APIKeyManager
from src.storage.database import get_session

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


def _build_manager() -> tuple[APIKeyManager, str]:
    manager = APIKeyManager(
        auth_enabled=True,
        legacy_api_key=None,
        static_api_keys=[],
        default_rate_limit_per_minute=5,
    )
    _record, raw_credential = manager.create_key(name="test-client")
    return (manager, raw_credential)


def _build_health_app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    exempt_prefixes: tuple[str, ...],
) -> tuple[TestClient, str]:
    manager, credential = _build_manager()
    app = FastAPI()
    app.add_middleware(
        APIKeyAuthMiddleware,
        manager=manager,
        exempt_prefixes=exempt_prefixes,
    )
    app.include_router(health_module.router)

    async def _override_get_session():
        yield MagicMock()

    app.dependency_overrides[get_session] = _override_get_session

    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {
            "status": "healthy",
            "age_seconds": 5.0,
            "last_task": "workers.collect_rss",
        }

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
    return (TestClient(app), credential)


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
    assert result.docs_enabled is True
    assert result.checks["worker"]["status"] == "healthy"
    assert result.checks["worker"]["last_task"] == "workers.collect_rss"
    assert result.checks["migrations"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_reports_docs_disabled_outside_development(
    mock_db_session,
    monkeypatch,
) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 5.0}

    async def fake_migration(_session):
        return {"status": "healthy"}

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "staging")

    result = await health_module.health_check(session=mock_db_session)

    assert result.docs_enabled is False


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
async def test_liveness_check_returns_up() -> None:
    assert await health_module.liveness_check() == {"status": "up"}


def test_health_route_requires_privileged_access_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, credential = _build_health_app(
        monkeypatch,
        exempt_prefixes=("/health/live",),
    )
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(health_module.settings, "API_ADMIN_KEY", "admin-secret")

    no_auth_response = client.get("/health")
    api_key_only_response = client.get("/health", headers={"X-API-Key": credential})
    privileged_response = client.get(
        "/health",
        headers={
            "X-API-Key": credential,
            "X-Admin-API-Key": "admin-secret",
        },
    )

    assert no_auth_response.status_code == 401
    assert api_key_only_response.status_code == 403
    assert privileged_response.status_code == 200
    assert privileged_response.json()["checks"] == {
        "database": {"status": "healthy"},
        "redis": {"status": "healthy"},
        "worker": {"status": "healthy"},
        "migrations": {"status": "healthy"},
    }


def test_health_route_keeps_detailed_payload_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _credential = _build_health_app(
        monkeypatch,
        exempt_prefixes=("/health", "/metrics"),
    )
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "development")

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["checks"]["database"]["latency_ms"] == 1.0
    assert payload["checks"]["worker"]["last_task"] == "workers.collect_rss"


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
async def test_readiness_check_redacts_dependency_details_outside_development(
    mock_db_session,
    monkeypatch,
) -> None:
    async def fake_db(_session):
        return {"status": "healthy", "latency_ms": 1.0}

    async def fake_redis():
        return {"status": "unhealthy", "message": "redis unavailable", "latency_ms": 99.0}

    async def fake_worker():
        return {"status": "healthy", "age_seconds": 1.0}

    async def fake_migration(_session):
        return {"status": "healthy"}

    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module, "check_redis", fake_redis)
    monkeypatch.setattr(health_module, "check_worker_activity", fake_worker)
    monkeypatch.setattr(health_module, "check_migration_parity", fake_migration)
    monkeypatch.setattr(health_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "staging")

    result = await health_module.readiness_check(session=mock_db_session)

    assert result.status_code == 503
    assert json.loads(result.body.decode("utf-8")) == {
        "status": "not_ready",
        "checks": {
            "redis": {
                "status": "unhealthy",
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
async def test_readiness_check_redacts_exception_reason_outside_development(
    mock_db_session,
    monkeypatch,
) -> None:
    logger = MagicMock()

    async def fake_db(_session):
        raise RuntimeError("db blew up")

    monkeypatch.setattr(health_module, "logger", logger)
    monkeypatch.setattr(health_module, "check_database", fake_db)
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "production")

    result = await health_module.readiness_check(session=mock_db_session)

    assert result.status_code == 503
    assert json.loads(result.body.decode("utf-8")) == {
        "status": "not_ready",
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
