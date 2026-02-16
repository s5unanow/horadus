"""
Application configuration using Pydantic Settings.

Loads configuration from environment variables and .env files.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret_file(path: str) -> str:
    try:
        content = Path(path).expanduser().read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"Could not read secret file '{path}'"
        raise ValueError(msg) from exc
    if not content:
        msg = f"Secret file '{path}' is empty"
        raise ValueError(msg)
    return content


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
    DATABASE_URL_FILE: str | None = Field(
        default=None,
        description="Path to file containing DATABASE_URL",
    )
    DATABASE_URL_SYNC: str = Field(
        default="",
        description="Sync PostgreSQL connection string (for Alembic); derived if empty",
    )
    DATABASE_URL_SYNC_FILE: str | None = Field(
        default=None,
        description="Path to file containing DATABASE_URL_SYNC",
    )
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DATABASE_POOL_TIMEOUT_SECONDS: int = Field(
        default=30,
        ge=1,
        le=600,
        description="Seconds to wait for a DB connection from pool before timing out",
    )
    MIGRATION_PARITY_CHECK_ENABLED: bool = Field(
        default=True,
        description="Enable migration parity checks in runtime health/startup paths",
    )
    MIGRATION_PARITY_STRICT_STARTUP: bool = Field(
        default=False,
        description="Fail API startup when migration parity check is unhealthy",
    )

    @model_validator(mode="after")
    def _load_secret_file_values(self) -> Settings:
        secret_mappings = {
            "DATABASE_URL": self.DATABASE_URL_FILE,
            "DATABASE_URL_SYNC": self.DATABASE_URL_SYNC_FILE,
            "REDIS_URL": self.REDIS_URL_FILE,
            "SECRET_KEY": self.SECRET_KEY_FILE,
            "API_KEY": self.API_KEY_FILE,
            "API_ADMIN_KEY": self.API_ADMIN_KEY_FILE,
            "OPENAI_API_KEY": self.OPENAI_API_KEY_FILE,
            "LLM_SECONDARY_API_KEY": self.LLM_SECONDARY_API_KEY_FILE,
            "CELERY_BROKER_URL": self.CELERY_BROKER_URL_FILE,
            "CELERY_RESULT_BACKEND": self.CELERY_RESULT_BACKEND_FILE,
        }
        for target_field, file_path in secret_mappings.items():
            if not file_path:
                continue
            setattr(self, target_field, _read_secret_file(file_path))

        if self.API_KEYS_FILE:
            raw_keys = _read_secret_file(self.API_KEYS_FILE)
            parsed_keys: list[str] = []
            for line in raw_keys.splitlines():
                for item in line.split(","):
                    key = item.strip()
                    if key:
                        parsed_keys.append(key)
            self.API_KEYS = parsed_keys

        return self

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

    @model_validator(mode="after")
    def _validate_calibration_thresholds(self) -> Settings:
        if (
            self.CALIBRATION_DRIFT_BRIER_WARN_THRESHOLD
            > self.CALIBRATION_DRIFT_BRIER_CRITICAL_THRESHOLD
        ):
            msg = "CALIBRATION_DRIFT_BRIER_WARN_THRESHOLD must be <= CRITICAL threshold"
            raise ValueError(msg)
        if (
            self.CALIBRATION_DRIFT_BUCKET_ERROR_WARN_THRESHOLD
            > self.CALIBRATION_DRIFT_BUCKET_ERROR_CRITICAL_THRESHOLD
        ):
            msg = "CALIBRATION_DRIFT_BUCKET_ERROR_WARN_THRESHOLD must be <= CRITICAL threshold"
            raise ValueError(msg)
        return self

    # =========================================================================
    # Redis
    # =========================================================================
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    REDIS_URL_FILE: str | None = Field(
        default=None,
        description="Path to file containing REDIS_URL",
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
    SECRET_KEY_FILE: str | None = Field(
        default=None,
        description="Path to file containing SECRET_KEY",
    )
    API_KEY: str | None = Field(
        default=None,
        description="Optional API key for authentication",
    )
    API_KEY_FILE: str | None = Field(
        default=None,
        description="Path to file containing API_KEY",
    )
    API_AUTH_ENABLED: bool = Field(
        default=False,
        description="Enforce API key auth when true",
    )
    API_KEYS: list[str] = Field(
        default_factory=list,
        description="Additional API keys (comma-separated env value supported)",
    )
    API_ADMIN_KEY: str | None = Field(
        default=None,
        description="Admin key for API key management endpoints",
    )
    API_ADMIN_KEY_FILE: str | None = Field(
        default=None,
        description="Path to file containing API_ADMIN_KEY",
    )
    API_KEYS_FILE: str | None = Field(
        default=None,
        description="Path to file containing API_KEYS values (newline or comma separated)",
    )
    API_RATE_LIMIT_PER_MINUTE: int = Field(
        default=120,
        ge=1,
        description="Default per-key API request limit per minute",
    )
    API_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="Rolling window size for API rate limiting in seconds",
    )
    API_RATE_LIMIT_REDIS_PREFIX: str = Field(
        default="horadus:api_rate_limit",
        description="Redis key prefix used for distributed API rate limiting buckets",
    )
    API_KEYS_PERSIST_PATH: str | None = Field(
        default=None,
        description="Optional JSON file path for persisting runtime API key metadata",
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

    @field_validator("API_KEYS", mode="before")
    @classmethod
    def parse_api_keys(cls, v: Any) -> list[str]:
        """Parse API keys from comma-separated string or list."""
        if isinstance(v, str):
            return [key.strip() for key in v.split(",") if key.strip()]
        if isinstance(v, list):
            return [str(key).strip() for key in v if str(key).strip()]
        return []

    @field_validator("CALIBRATION_DRIFT_WEBHOOK_URL", mode="before")
    @classmethod
    def parse_optional_webhook_url(cls, value: Any) -> str | None:
        """Normalize optional webhook URL values."""
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return str(value).strip() or None

    @field_validator("LLM_PRIMARY_BASE_URL", "LLM_SECONDARY_BASE_URL", mode="before")
    @classmethod
    def parse_optional_llm_base_urls(cls, value: Any) -> str | None:
        """Normalize optional LLM base URL values."""
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return str(value).strip() or None

    # =========================================================================
    # OpenAI Configuration
    # =========================================================================
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key",
    )
    OPENAI_API_KEY_FILE: str | None = Field(
        default=None,
        description="Path to file containing OPENAI_API_KEY",
    )
    LLM_PRIMARY_PROVIDER: str = Field(
        default="openai",
        description="Primary LLM provider identifier for logging/routing",
    )
    LLM_PRIMARY_BASE_URL: str | None = Field(
        default=None,
        description="Optional base URL for OpenAI-compatible primary provider endpoints",
    )
    LLM_SECONDARY_PROVIDER: str | None = Field(
        default=None,
        description="Secondary LLM provider identifier for failover routing/logging",
    )
    LLM_SECONDARY_BASE_URL: str | None = Field(
        default=None,
        description="Optional base URL for OpenAI-compatible secondary provider endpoints",
    )
    LLM_SECONDARY_API_KEY: str | None = Field(
        default=None,
        description="Optional API key override for secondary provider",
    )
    LLM_SECONDARY_API_KEY_FILE: str | None = Field(
        default=None,
        description="Path to file containing LLM_SECONDARY_API_KEY",
    )
    LLM_TIER1_MODEL: str = Field(
        default="gpt-4.1-nano",
        description="Model for Tier 1 (fast) classification",
    )
    LLM_TIER2_MODEL: str = Field(
        default="gpt-4.1-mini",
        description="Model for Tier 2 (thorough) classification",
    )
    LLM_TIER1_SECONDARY_MODEL: str | None = Field(
        default=None,
        description="Optional secondary model for Tier 1 failover",
    )
    LLM_TIER2_SECONDARY_MODEL: str | None = Field(
        default=None,
        description="Optional secondary model for Tier 2 failover",
    )
    LLM_REPORT_MODEL: str = Field(
        default="gpt-4.1-mini",
        description="Model for weekly report narrative generation",
    )
    LLM_RETROSPECTIVE_MODEL: str = Field(
        default="gpt-4.1-mini",
        description="Model for retrospective analysis narrative generation",
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
    EMBEDDING_CACHE_MAX_SIZE: int = Field(
        default=2048,
        ge=1,
        description="Maximum in-memory embedding cache entries before LRU eviction",
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
    CELERY_BROKER_URL_FILE: str | None = Field(
        default=None,
        description="Path to file containing CELERY_BROKER_URL",
    )
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")
    CELERY_RESULT_BACKEND_FILE: str | None = Field(
        default=None,
        description="Path to file containing CELERY_RESULT_BACKEND",
    )
    WORKER_HEARTBEAT_REDIS_KEY: str = Field(
        default="horadus:worker:last_activity",
        description="Redis key storing the latest worker activity heartbeat payload",
    )
    WORKER_HEARTBEAT_STALE_SECONDS: int = Field(
        default=900,
        ge=30,
        description="Worker heartbeat age threshold before health reports stale worker activity",
    )
    WORKER_HEARTBEAT_TTL_SECONDS: int = Field(
        default=3600,
        ge=60,
        description="Redis TTL for worker heartbeat payload key",
    )

    # =========================================================================
    # Feature Flags
    # =========================================================================
    ENABLE_RSS_INGESTION: bool = Field(default=True)
    ENABLE_GDELT_INGESTION: bool = Field(default=True)
    ENABLE_TELEGRAM_INGESTION: bool = Field(default=False)
    ENABLE_PROCESSING_PIPELINE: bool = Field(default=True)

    # =========================================================================
    # Application
    # =========================================================================
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment: development, staging, production",
    )
    SQL_ECHO: bool = Field(
        default=False,
        description="Log SQL statements from SQLAlchemy engine",
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
    PROCESSING_PIPELINE_BATCH_SIZE: int = Field(
        default=50,
        ge=1,
        description="Max pending items processed per pipeline task run",
    )
    PROCESSING_STALE_TIMEOUT_MINUTES: int = Field(
        default=30,
        ge=1,
        description="Age threshold in minutes for resetting stale processing items",
    )
    PROCESSING_REAPER_INTERVAL_MINUTES: int = Field(
        default=15,
        ge=1,
        description="Interval in minutes for stale-processing reaper task schedule",
    )
    PROCESS_PENDING_INTERVAL_MINUTES: int = Field(
        default=5,
        ge=1,
        description="Interval in minutes for periodic workers.process_pending_items schedule",
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
    # Calibration Drift Alerting
    # =========================================================================
    CALIBRATION_DRIFT_MIN_RESOLVED_OUTCOMES: int = Field(
        default=20,
        ge=0,
        description="Minimum resolved outcomes before calibration drift alerts are emitted",
    )
    CALIBRATION_DRIFT_BRIER_WARN_THRESHOLD: float = Field(
        default=0.20,
        ge=0,
        description="Warning threshold for mean Brier score drift alerts",
    )
    CALIBRATION_DRIFT_BRIER_CRITICAL_THRESHOLD: float = Field(
        default=0.30,
        ge=0,
        description="Critical threshold for mean Brier score drift alerts",
    )
    CALIBRATION_DRIFT_BUCKET_ERROR_WARN_THRESHOLD: float = Field(
        default=0.15,
        ge=0,
        description="Warning threshold for max bucket calibration error alerts",
    )
    CALIBRATION_DRIFT_BUCKET_ERROR_CRITICAL_THRESHOLD: float = Field(
        default=0.25,
        ge=0,
        description="Critical threshold for max bucket calibration error alerts",
    )
    CALIBRATION_DRIFT_WEBHOOK_URL: str | None = Field(
        default=None,
        description="Optional webhook endpoint for calibration drift alert delivery",
    )
    CALIBRATION_DRIFT_WEBHOOK_TIMEOUT_SECONDS: float = Field(
        default=5.0,
        gt=0,
        description="HTTP timeout for calibration drift webhook calls",
    )
    CALIBRATION_DRIFT_WEBHOOK_MAX_RETRIES: int = Field(
        default=3,
        ge=0,
        description="Maximum retries for transient calibration drift webhook failures",
    )
    CALIBRATION_DRIFT_WEBHOOK_BACKOFF_SECONDS: float = Field(
        default=1.0,
        ge=0,
        description="Initial backoff delay (seconds) for webhook retry attempts",
    )
    CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND: int = Field(
        default=5,
        ge=0,
        description="Minimum resolved outcomes per trend in window before coverage is considered sufficient",
    )
    CALIBRATION_COVERAGE_MIN_RESOLVED_RATIO: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Minimum resolved/total ratio required for calibration coverage sufficiency",
    )

    # =========================================================================
    # Collection
    # =========================================================================
    RSS_COLLECTION_INTERVAL: int = Field(default=30, description="Minutes")
    GDELT_COLLECTION_INTERVAL: int = Field(default=60, description="Minutes")
    MAX_ITEMS_PER_COLLECTION: int = Field(default=100, ge=1)
    WEEKLY_REPORT_DAY_OF_WEEK: int = Field(
        default=1,
        ge=0,
        le=6,
        description="UTC day of week for weekly report task (0=Sun..6=Sat)",
    )
    WEEKLY_REPORT_HOUR_UTC: int = Field(
        default=7,
        ge=0,
        le=23,
        description="UTC hour for weekly report task",
    )
    WEEKLY_REPORT_MINUTE_UTC: int = Field(
        default=0,
        ge=0,
        le=59,
        description="UTC minute for weekly report task",
    )
    MONTHLY_REPORT_DAY_OF_MONTH: int = Field(
        default=1,
        ge=1,
        le=28,
        description="UTC day of month for monthly report task",
    )
    MONTHLY_REPORT_HOUR_UTC: int = Field(
        default=8,
        ge=0,
        le=23,
        description="UTC hour for monthly report task",
    )
    MONTHLY_REPORT_MINUTE_UTC: int = Field(
        default=0,
        ge=0,
        le=59,
        description="UTC minute for monthly report task",
    )

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
