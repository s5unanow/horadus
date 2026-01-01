"""
FastAPI Application for Geopolitical Intelligence Platform.

This module creates and configures the FastAPI application,
including middleware, error handlers, and route registration.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI, Request
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import events, health, reports, sources, trends
from src.core.config import settings
from src.storage.database import async_session_maker, engine

logger = structlog.get_logger(__name__)


# =============================================================================
# Lifespan Management
# =============================================================================


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application lifespan events.

    Startup:
    - Initialize database connection pool
    - Validate configuration
    - Log startup info

    Shutdown:
    - Close database connections
    - Clean up resources
    """
    # Startup
    logger.info(
        "Starting Geopolitical Intelligence Platform",
        environment=settings.ENVIRONMENT,
        api_version="1.0.0",
    )

    # Verify database connection
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("Shutting down application")
    await engine.dispose()


# =============================================================================
# Application Factory
# =============================================================================


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Geopolitical Intelligence Platform",
        description=(
            "API for tracking geopolitical trends and analyzing news events. "
            "Collects news from multiple sources, classifies via LLM, and "
            "tracks trend probabilities over time."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Register routes
    register_routes(app)

    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers."""

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle uncaught exceptions."""
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred",
            },
        )


def register_routes(app: FastAPI) -> None:
    """Register API route handlers."""

    # Health check (no prefix)
    app.include_router(health.router, tags=["Health"])

    # API v1 routes
    api_v1_prefix = "/api/v1"

    app.include_router(
        sources.router,
        prefix=f"{api_v1_prefix}/sources",
        tags=["Sources"],
    )

    app.include_router(
        trends.router,
        prefix=f"{api_v1_prefix}/trends",
        tags=["Trends"],
    )

    app.include_router(
        events.router,
        prefix=f"{api_v1_prefix}/events",
        tags=["Events"],
    )

    app.include_router(
        reports.router,
        prefix=f"{api_v1_prefix}/reports",
        tags=["Reports"],
    )


# =============================================================================
# Application Instance
# =============================================================================

app = create_app()


# =============================================================================
# Development Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
    )
