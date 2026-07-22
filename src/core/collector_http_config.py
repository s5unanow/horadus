"""Validated environment settings for collector HTTP resource limits."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorHTTPSettings(BaseSettings):
    """Network and response limits shared by public-source collectors."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    COLLECTOR_HTTP_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=120)
    COLLECTOR_HTTP_READ_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=300)
    COLLECTOR_HTTP_MAX_CONNECTIONS: int = Field(default=20, ge=1, le=200)
    COLLECTOR_HTTP_MAX_KEEPALIVE_CONNECTIONS: int = Field(default=10, ge=0, le=100)
    COLLECTOR_HTTP_MAX_RESPONSE_BYTES: int = Field(default=10_000_000, ge=1024, le=50_000_000)
    COLLECTOR_HTTP_MAX_REDIRECTS: int = Field(default=5, ge=0, le=10)


collector_http_settings = CollectorHTTPSettings()
