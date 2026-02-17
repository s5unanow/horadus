"""
Health check endpoints.

Provides endpoints for monitoring application health,
including database and Redis connectivity checks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.migration_parity import check_migration_parity
from src.storage.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class HealthStatus(BaseModel):
    """Health check response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "timestamp": "2026-02-07T20:00:00Z",
                "version": "1.0.0",
                "checks": {
                    "database": {"status": "healthy", "latency_ms": 3.2},
                    "redis": {"status": "healthy", "latency_ms": 1.8},
                    "worker": {"status": "healthy", "age_seconds": 12.4},
                    "migrations": {
                        "status": "healthy",
                        "current_revision": "0008_vector_index_profile",
                        "expected_head": "0008_vector_index_profile",
                    },
                },
            }
        }
    )

    status: str
    timestamp: str
    version: str
    checks: dict[str, Any]


class ComponentHealth(BaseModel):
    """Individual component health."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "latency_ms": 2.4,
                "message": None,
            }
        }
    )

    status: str
    latency_ms: float | None = None
    message: str | None = None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/health", response_model=HealthStatus)
async def health_check(
    session: AsyncSession = Depends(get_session),
) -> HealthStatus:
    """
    Check application health.

    Returns status of all critical components:
    - Database connection
    - Redis connection
    - Overall status

    Returns:
        HealthStatus with component details
    """
    checks: dict[str, Any] = {}
    overall_status = "healthy"

    # Check database
    db_check = await check_database(session)
    checks["database"] = db_check
    if db_check["status"] != "healthy":
        overall_status = "unhealthy"

    # Check Redis (if available)
    redis_check = await check_redis()
    checks["redis"] = redis_check
    if redis_check["status"] != "healthy":
        overall_status = "degraded" if overall_status == "healthy" else overall_status

    worker_check = await check_worker_activity()
    checks["worker"] = worker_check
    if worker_check["status"] != "healthy":
        overall_status = "degraded" if overall_status == "healthy" else overall_status

    if settings.MIGRATION_PARITY_CHECK_ENABLED:
        migration_check = await check_migration_parity(session)
    else:
        migration_check = {
            "status": "skipped",
            "message": "Migration parity checks disabled by configuration",
        }
    checks["migrations"] = migration_check
    if migration_check["status"] != "healthy":
        overall_status = "degraded" if overall_status == "healthy" else overall_status

    return HealthStatus(
        status=overall_status,
        timestamp=datetime.now(UTC).isoformat(),
        version="1.0.0",
        checks=checks,
    )


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """
    Kubernetes liveness probe.

    Simple check that the application is running.
    Does not check dependencies.
    """
    return {"status": "alive"}


@router.get("/health/ready", response_model=None)
async def readiness_check(
    session: AsyncSession = Depends(get_session),
) -> dict[str, str] | JSONResponse:
    """
    Kubernetes readiness probe.

    Checks if the application is ready to receive traffic.
    Readiness requires all critical dependencies to report healthy.
    """
    try:
        checks: dict[str, Any] = {}
        db_check = await check_database(session)
        checks["database"] = db_check

        redis_check = await check_redis()
        checks["redis"] = redis_check

        worker_check = await check_worker_activity()
        checks["worker"] = worker_check

        if settings.MIGRATION_PARITY_CHECK_ENABLED:
            checks["migrations"] = await check_migration_parity(session)

        failing_checks = {
            name: payload for name, payload in checks.items() if payload.get("status") != "healthy"
        }
        if failing_checks:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "checks": failing_checks},
            )

        return {"status": "ready"}
    except Exception as e:
        logger.warning("Readiness check failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "reason": str(e)},
        )


# =============================================================================
# Health Check Functions
# =============================================================================


async def check_database(session: AsyncSession) -> dict[str, Any]:
    """Check database connectivity and latency."""
    import time

    try:
        start = time.perf_counter()
        await session.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000

        return {
            "status": "healthy",
            "latency_ms": round(latency, 2),
        }
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "message": str(e),
        }


async def check_redis() -> dict[str, Any]:
    """Check Redis connectivity."""
    import time

    try:
        import redis.asyncio as redis

        start = time.perf_counter()
        client = redis.from_url(settings.REDIS_URL)
        await client.ping()
        latency = (time.perf_counter() - start) * 1000
        await client.close()

        return {
            "status": "healthy",
            "latency_ms": round(latency, 2),
        }
    except ImportError:
        return {
            "status": "skipped",
            "message": "Redis client not installed",
        }
    except Exception as e:
        logger.warning("Redis health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "message": str(e),
        }


async def check_worker_activity() -> dict[str, Any]:
    """Check latest worker activity heartbeat from Redis."""
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        raw_payload = await client.get(settings.WORKER_HEARTBEAT_REDIS_KEY)
        await client.close()

        if not raw_payload:
            return {
                "status": "unhealthy",
                "message": "No worker heartbeat found",
            }

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return {
                "status": "unhealthy",
                "message": "Worker heartbeat payload is invalid JSON",
            }

        timestamp_raw = payload.get("timestamp")
        if not isinstance(timestamp_raw, str) or not timestamp_raw.strip():
            return {
                "status": "unhealthy",
                "message": "Worker heartbeat timestamp missing",
            }

        last_seen = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        age_seconds = max(0.0, (now - last_seen.astimezone(UTC)).total_seconds())
        stale_threshold = float(settings.WORKER_HEARTBEAT_STALE_SECONDS)
        if age_seconds > stale_threshold:
            return {
                "status": "unhealthy",
                "age_seconds": round(age_seconds, 2),
                "last_task": payload.get("task"),
                "last_status": payload.get("status"),
                "message": f"Worker heartbeat stale (>{settings.WORKER_HEARTBEAT_STALE_SECONDS}s)",
            }

        return {
            "status": "healthy",
            "age_seconds": round(age_seconds, 2),
            "last_task": payload.get("task"),
            "last_status": payload.get("status"),
        }
    except ImportError:
        return {
            "status": "skipped",
            "message": "Redis client not installed",
        }
    except Exception as e:
        logger.warning("Worker heartbeat check failed", error=str(e))
        return {
            "status": "unhealthy",
            "message": str(e),
        }
