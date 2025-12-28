"""
Health check endpoints.

Provides endpoints for monitoring application health,
including database and Redis connectivity checks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class HealthStatus(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    version: str
    checks: dict[str, Any]


class ComponentHealth(BaseModel):
    """Individual component health."""

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

    return HealthStatus(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat(),
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


@router.get("/health/ready")
async def readiness_check(
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """
    Kubernetes readiness probe.

    Checks if the application is ready to receive traffic.
    Includes database connectivity check.
    """
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.warning("Readiness check failed", error=str(e))
        return {"status": "not_ready", "reason": str(e)}


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

        from src.core.config import settings

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
