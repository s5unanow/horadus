"""
Database connection and session management.

This module provides:
- Async SQLAlchemy engine configuration
- Session factory for dependency injection
- Connection pool management
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.storage.restatement_models import PrivilegedWriteAudit

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


# =============================================================================
# Engine Configuration
# =============================================================================


def create_engine() -> AsyncEngine:
    """
    Create async SQLAlchemy engine.

    Uses NullPool in development for easier debugging and pooled
    connections in staging/production.
    """
    if settings.is_development:
        return create_async_engine(
            settings.DATABASE_URL,
            echo=settings.SQL_ECHO,
            poolclass=NullPool,
            pool_pre_ping=True,
        )

    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.SQL_ECHO,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
        pool_pre_ping=True,
    )


# Create engine instance
engine = create_engine()

# Create session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

_PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY = "pending_privileged_write_successes"


def _drain_pending_privileged_write_successes(session: AsyncSession) -> list[Any]:
    pending = session.info.get(_PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY, [])
    return pending if isinstance(pending, list) else []


async def _update_privileged_write_audit(
    audit_session: AsyncSession,
    *,
    audit_id: Any,
    outcome: str,
    detail: str | None,
    observed_revision_token: str | None,
    result_links: dict[str, Any] | None = None,
) -> None:
    record = await audit_session.get(PrivilegedWriteAudit, audit_id)
    if record is None:
        return
    record.outcome = outcome
    record.detail = detail
    record.last_seen_at = datetime.now(tz=UTC)
    if observed_revision_token is not None:
        record.observed_revision_token = observed_revision_token
    if result_links is not None:
        record.result_links = result_links
    await audit_session.flush()


async def _finalize_pending_privileged_write_audits(
    session: AsyncSession,
    *,
    outcome: str,
    detail: str | None = None,
) -> None:
    pending = _drain_pending_privileged_write_successes(session)
    if not pending:
        return
    async with async_session_maker() as audit_session:
        try:
            for entry in pending:
                audit_id = getattr(entry, "audit_id", None)
                if audit_id is None:
                    continue
                await _update_privileged_write_audit(
                    audit_session,
                    audit_id=audit_id,
                    outcome=outcome,
                    detail=detail if outcome != "applied" else getattr(entry, "detail", None),
                    observed_revision_token=getattr(entry, "observed_revision_token", None),
                    result_links=(
                        cast("dict[str, Any] | None", getattr(entry, "result_links", None))
                        if outcome == "applied"
                        else None
                    ),
                )
            await audit_session.commit()
            pending.clear()
        except Exception:
            await audit_session.rollback()
            raise


# =============================================================================
# Session Dependency
# =============================================================================


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting database sessions.

    Usage:
        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Item))
            return result.scalars().all()

    Sessions are automatically committed on success and rolled back on error.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            await _finalize_pending_privileged_write_audits(
                session,
                outcome="rolled_back",
                detail=f"Route transaction rolled back before commit completed: {exc}",
            )
            raise
        await _finalize_pending_privileged_write_audits(session, outcome="applied")


# =============================================================================
# Utility Functions
# =============================================================================


async def init_db() -> None:
    """
    Initialize database tables.

    Note: In production, use Alembic migrations instead.
    This is useful for testing or quick setup.
    """
    from src.storage import models as _models  # noqa: F401
    from src.storage.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """
    Drop all database tables.

    WARNING: This will delete all data. Use only in testing.
    """
    from src.storage import models as _models  # noqa: F401
    from src.storage.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
