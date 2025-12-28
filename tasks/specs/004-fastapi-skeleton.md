# TASK-004: FastAPI Skeleton

## Overview

Create the basic FastAPI application structure with health endpoint, database connection, and middleware configuration.

## Context

This establishes the API foundation that all subsequent endpoints will build on. It needs to handle async database connections, CORS, error handling, and configuration from environment variables.

## Requirements

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (DB + Redis) |
| GET | `/` | Root redirect to /docs |

### Features

- Async database connection pool (asyncpg)
- Database session dependency injection
- CORS middleware (configurable origins)
- Error handling middleware
- Request ID tracking
- Structured logging
- Settings from environment variables

## Implementation

### Step 1: Configuration

Create `src/core/config.py`:

```python
from functools import lru_cache
from typing import List

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    api_prefix: str = "/api/v1"

    # CORS
    cors_origins: List[str] = Field(default=["*"])

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/geoint"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")

    # LLM
    openai_api_key: str = ""

    # Optional: Telegram
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_session_name: str = "geoint_session"

    @property
    def async_database_url(self) -> str:
        """Ensure we're using asyncpg driver."""
        url = str(self.database_url)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Step 2: Database Connection

Create `src/storage/database.py`:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.async_database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    echo=settings.debug,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions (for use outside of FastAPI)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Step 3: Dependencies

Create `src/api/deps.py`:

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_db

# Type alias for database session dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]
```

### Step 4: Health Endpoint

Create `src/api/routes/health.py`:

```python
from datetime import datetime

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import DBSession
from src.core.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    checks: dict[str, str]


async def check_database(db: AsyncSession) -> str:
    """Check database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return "healthy"
    except Exception as e:
        return f"unhealthy: {str(e)}"


async def check_redis(settings: Settings) -> str:
    """Check Redis connectivity."""
    try:
        client = redis.from_url(str(settings.redis_url))
        await client.ping()
        await client.close()
        return "healthy"
    except Exception as e:
        return f"unhealthy: {str(e)}"


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: DBSession,
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """
    Health check endpoint.

    Returns the health status of the API and its dependencies.
    """
    db_status = await check_database(db)
    redis_status = await check_redis(settings)

    checks = {
        "database": db_status,
        "redis": redis_status,
    }

    overall_status = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version="0.1.0",
        checks=checks,
    )


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Kubernetes liveness probe - just checks if the app is running."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(
    db: DBSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Kubernetes readiness probe - checks if dependencies are available."""
    db_status = await check_database(db)
    redis_status = await check_redis(settings)

    if db_status == "healthy" and redis_status == "healthy":
        return {"status": "ready"}

    # Return 503 if not ready (FastAPI will handle this based on status code)
    from fastapi import HTTPException
    raise HTTPException(status_code=503, detail="Service not ready")
```

### Step 5: Main Application

Create `src/api/main.py`:

```python
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from src.api.routes import health
from src.core.config import get_settings
from src.storage.database import engine

settings = get_settings()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if not settings.debug else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting application", version="0.1.0")
    yield
    logger.info("Shutting down application")
    await engine.dispose()


app = FastAPI(
    title="Geopolitical Intelligence API",
    description="API for tracking geopolitical trends and events",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Root redirect
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


# Include routers
app.include_router(health.router)

# Future routers will be added here:
# app.include_router(sources.router, prefix=settings.api_prefix)
# app.include_router(events.router, prefix=settings.api_prefix)
# app.include_router(trends.router, prefix=settings.api_prefix)
# app.include_router(reports.router, prefix=settings.api_prefix)
```

### Step 6: Package Initialization

Create/update `src/api/__init__.py`:

```python
"""API module."""
```

Create/update `src/api/routes/__init__.py`:

```python
"""API routes."""
```

## Verification

```bash
# Ensure Docker services are running
docker-compose up -d

# Ensure migrations are applied
alembic upgrade head

# Start the API server
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Test health endpoint
curl http://localhost:8000/health | jq

# Expected response:
# {
#   "status": "healthy",
#   "timestamp": "2024-01-XX...",
#   "version": "0.1.0",
#   "checks": {
#     "database": "healthy",
#     "redis": "healthy"
#   }
# }

# Test liveness
curl http://localhost:8000/health/live

# Test readiness
curl http://localhost:8000/health/ready

# Check OpenAPI docs
open http://localhost:8000/docs
```

## Files Created

```
src/
├── api/
│   ├── __init__.py
│   ├── main.py          # FastAPI app
│   ├── deps.py          # Dependencies
│   └── routes/
│       ├── __init__.py
│       └── health.py    # Health endpoints
├── core/
│   ├── __init__.py
│   └── config.py        # Settings
└── storage/
    ├── __init__.py
    ├── database.py      # DB connection
    └── models.py        # (from TASK-003)
```

## Acceptance Checklist

- [ ] `src/core/config.py` created with Settings class
- [ ] `src/storage/database.py` created with async engine
- [ ] `src/api/deps.py` created with DBSession dependency
- [ ] `src/api/routes/health.py` created with health endpoints
- [ ] `src/api/main.py` created with FastAPI app
- [ ] All `__init__.py` files in place
- [ ] `uvicorn src.api.main:app` starts without errors
- [ ] `GET /health` returns healthy status
- [ ] `GET /health/live` returns alive
- [ ] `GET /health/ready` returns ready
- [ ] `GET /` redirects to `/docs`
- [ ] OpenAPI docs accessible at `/docs`
- [ ] Request ID header present in responses
- [ ] CORS headers present
