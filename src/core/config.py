"""
Application configuration using Pydantic Settings.

Loads configuration from environment variables and .env files.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    All settings can be overridden via environment variables.
    For example, DATABASE_URL env var sets the database_url field.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # Database
    # =========================================================================
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres@localhost:5432/geoint",
        description="Async PostgreSQL connection string",
    )
    DATABASE_URL_SYNC: str = Field(
        default="",
        description="Sync PostgreSQL connection string (for Alembic); derived if empty",
    )
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)

    @model_validator(mode="after")
    def _derive_database_url_sync(self) -> Settings:
        if self.DATABASE_URL.startswith("postgresql://"):
            # Runtime engines use asyncpg; normalize common sync-style URLs.
            self.DATABASE_URL = self.DATABASE_URL.replace(
                "postgresql://",
                "postgresql+asyncpg://",
                1,
            )
        if not self.DATABASE_URL_SYNC.strip():
            self.DATABASE_URL_SYNC = self.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        return self

    # =========================================================================
    # Redis
    # =========================================================================
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # =========================================================================
    # API
    # =========================================================================
    API_HOST: str = Field(default="0.0.0.0")  # nosec B104
    API_PORT: int = Field(default=8000, ge=1, le=65535)
    API_RELOAD: bool = Field(default=True)

    # =========================================================================
    # Security
    # =========================================================================
    SECRET_KEY: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for signing tokens",
    )
    API_KEY: str | None = Field(
        default=None,
        description="Optional API key for authentication",
    )
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return list(v) if v else []

    # =========================================================================
    # OpenAI Configuration
    # =========================================================================
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key",
    )
    LLM_TIER1_MODEL: str = Field(
        default="gpt-4.1-nano",
        description="Model for Tier 1 (fast) classification",
    )
    LLM_TIER2_MODEL: str = Field(
        default="gpt-4o-mini",
        description="Model for Tier 2 (thorough) classification",
    )
    LLM_TIER1_RPM: int = Field(default=500, description="Tier 1 rate limit (req/min)")
    LLM_TIER2_RPM: int = Field(default=500, description="Tier 2 rate limit (req/min)")
    LLM_TIER1_BATCH_SIZE: int = Field(
        default=10,
        ge=1,
        le=256,
        description="Maximum raw items per Tier 1 classification API request",
    )
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-small",
        description="Model for text embedding generation",
    )
    EMBEDDING_DIMENSIONS: int = Field(
        default=1536,
        ge=1,
        description="Expected embedding vector dimensions",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=32,
        ge=1,
        le=2048,
        description="Maximum texts per embedding API request",
    )

    # =========================================================================
    # Telegram
    # =========================================================================
    TELEGRAM_API_ID: int | None = Field(default=None)
    TELEGRAM_API_HASH: str | None = Field(default=None)
    TELEGRAM_SESSION_NAME: str = Field(default="geoint_session")

    # =========================================================================
    # Celery
    # =========================================================================
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")

    # =========================================================================
    # Feature Flags
    # =========================================================================
    ENABLE_RSS_INGESTION: bool = Field(default=True)
    ENABLE_GDELT_INGESTION: bool = Field(default=True)
    ENABLE_TELEGRAM_INGESTION: bool = Field(default=False)

    # =========================================================================
    # Application
    # =========================================================================
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment: development, staging, production",
    )
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json", description="json or console")

    # =========================================================================
    # Processing
    # =========================================================================
    TIER1_RELEVANCE_THRESHOLD: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Minimum Tier 1 score to proceed to Tier 2",
    )
    DEDUP_SIMILARITY_THRESHOLD: float = Field(
        default=0.92,
        ge=0,
        le=1,
        description="Cosine similarity threshold for deduplication",
    )
    CLUSTER_SIMILARITY_THRESHOLD: float = Field(
        default=0.88,
        ge=0,
        le=1,
        description="Cosine similarity threshold for event clustering",
    )
    CLUSTER_TIME_WINDOW_HOURS: int = Field(
        default=48,
        ge=1,
        description="Time window for event clustering",
    )

    # =========================================================================
    # Trend Engine
    # =========================================================================
    DEFAULT_DECAY_HALF_LIFE_DAYS: int = Field(default=30, ge=1)
    TREND_SNAPSHOT_INTERVAL_MINUTES: int = Field(default=60, ge=1)

    # =========================================================================
    # Cost Protection (Kill Switch)
    # =========================================================================
    TIER1_MAX_DAILY_CALLS: int = Field(
        default=1000,
        ge=0,
        description="Max Tier 1 LLM calls per day (0 = unlimited)",
    )
    TIER2_MAX_DAILY_CALLS: int = Field(
        default=200,
        ge=0,
        description="Max Tier 2 LLM calls per day (0 = unlimited)",
    )
    EMBEDDING_MAX_DAILY_CALLS: int = Field(
        default=500,
        ge=0,
        description="Max embedding calls per day (0 = unlimited)",
    )
    DAILY_COST_LIMIT_USD: float = Field(
        default=5.0,
        ge=0,
        description="Hard daily cost limit in USD (0 = unlimited)",
    )
    COST_ALERT_THRESHOLD_PCT: int = Field(
        default=80,
        ge=0,
        le=100,
        description="Alert when this % of daily budget is reached",
    )

    # =========================================================================
    # Collection
    # =========================================================================
    RSS_COLLECTION_INTERVAL: int = Field(default=30, description="Minutes")
    GDELT_COLLECTION_INTERVAL: int = Field(default=60, description="Minutes")
    MAX_ITEMS_PER_COLLECTION: int = Field(default=100, ge=1)

    # =========================================================================
    # Computed Properties
    # =========================================================================

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Convenience instance
settings = get_settings()
