"""
Database connection and session management.

This module provides:
- Async SQLAlchemy engine configuration
- Session factory for dependency injection
- Connection pool management
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


# =============================================================================
# Engine Configuration
# =============================================================================

def create_engine() -> AsyncEngine:
    """
    Create async SQLAlchemy engine.
    
    Uses connection pooling in production, NullPool in development
    for easier debugging.
    """
    pool_class = NullPool if settings.is_development else None
    
    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.is_development,  # Log SQL in development
        pool_size=settings.DATABASE_POOL_SIZE if not settings.is_development else 5,
        max_overflow=settings.DATABASE_MAX_OVERFLOW if not settings.is_development else 0,
        poolclass=pool_class,
        # Connection health check
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
        except Exception:
            await session.rollback()
            raise


# =============================================================================
# Utility Functions
# =============================================================================

async def init_db() -> None:
    """
    Initialize database tables.
    
    Note: In production, use Alembic migrations instead.
    This is useful for testing or quick setup.
    """
    from src.storage.models import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """
    Drop all database tables.
    
    WARNING: This will delete all data. Use only in testing.
    """
    from src.storage.models import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
