from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.config import Settings

pytestmark = pytest.mark.unit

TEST_BOOTSTRAP_KEY = "bootstrap-key"  # pragma: allowlist secret
TEST_ADMIN_KEY = "admin-key"  # pragma: allowlist secret


def _write_secret(path: Path, value: str) -> str:
    path.write_text(value, encoding="utf-8")
    return str(path)


def test_settings_loads_openai_key_from_file(tmp_path: Path) -> None:
    secret_path = _write_secret(
        tmp_path / "openai_key.txt",
        "openai-token-from-file\n",  # pragma: allowlist secret
    )

    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY_FILE=secret_path,
    )

    assert settings.OPENAI_API_KEY == "openai-token-from-file"  # pragma: allowlist secret


def test_settings_loads_api_keys_from_file(tmp_path: Path) -> None:
    keys_path = _write_secret(tmp_path / "api_keys.txt", "alpha, beta\ngamma\n")

    settings = Settings(
        _env_file=None,
        API_KEYS_FILE=keys_path,
    )

    assert settings.API_KEYS == ["alpha", "beta", "gamma"]


def test_settings_raises_for_empty_secret_file(tmp_path: Path) -> None:
    secret_path = _write_secret(tmp_path / "empty_secret.txt", "\n")

    with pytest.raises(ValidationError, match="Secret file"):
        Settings(
            _env_file=None,
            OPENAI_API_KEY_FILE=secret_path,
        )


def test_settings_raises_for_missing_secret_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing_secret.txt"

    with pytest.raises(ValidationError, match="Could not read secret file"):
        Settings(
            _env_file=None,
            OPENAI_API_KEY_FILE=str(missing_path),
        )


def test_settings_derives_sync_url_after_file_load(tmp_path: Path) -> None:
    db_url_path = _write_secret(
        tmp_path / "database_url.txt",
        "postgresql://geoint@postgres:5432/geoint\n",
    )

    settings = Settings(
        _env_file=None,
        DATABASE_URL_FILE=db_url_path,
    )

    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert settings.DATABASE_URL_SYNC.startswith("postgresql://")


def test_settings_rejects_invalid_report_api_mode() -> None:
    with pytest.raises(ValidationError, match="LLM_REPORT_API_MODE"):
        Settings(
            _env_file=None,
            LLM_REPORT_API_MODE="invalid_mode",
        )


def test_settings_normalizes_optional_otel_fields() -> None:
    settings = Settings(
        _env_file=None,
        OTEL_EXPORTER_OTLP_ENDPOINT="  ",
        OTEL_EXPORTER_OTLP_HEADERS="  ",
    )

    assert settings.OTEL_EXPORTER_OTLP_ENDPOINT is None
    assert settings.OTEL_EXPORTER_OTLP_HEADERS is None


def test_settings_rejects_invalid_trace_sampler_ratio() -> None:
    with pytest.raises(ValidationError, match="OTEL_TRACES_SAMPLER_RATIO"):
        Settings(
            _env_file=None,
            OTEL_TRACES_SAMPLER_RATIO=1.5,
        )


def test_settings_normalizes_rate_limit_strategy() -> None:
    settings = Settings(
        _env_file=None,
        API_RATE_LIMIT_STRATEGY=" Sliding_Window ",
    )

    assert settings.API_RATE_LIMIT_STRATEGY == "sliding_window"


def test_settings_rejects_invalid_rate_limit_strategy() -> None:
    with pytest.raises(ValidationError, match="API_RATE_LIMIT_STRATEGY"):
        Settings(
            _env_file=None,
            API_RATE_LIMIT_STRATEGY="token_bucket",
        )


def test_settings_normalizes_supported_languages() -> None:
    settings = Settings(
        _env_file=None,
        LANGUAGE_POLICY_SUPPORTED_LANGUAGES="EN, ukrainian, RU",
    )

    assert settings.LANGUAGE_POLICY_SUPPORTED_LANGUAGES == ["en", "uk", "ru"]


def test_settings_rejects_invalid_unsupported_language_mode() -> None:
    with pytest.raises(ValidationError, match="LANGUAGE_POLICY_UNSUPPORTED_MODE"):
        Settings(
            _env_file=None,
            LANGUAGE_POLICY_UNSUPPORTED_MODE="translate",
        )


def test_settings_rejects_production_default_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY must be explicitly configured"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            API_AUTH_ENABLED=True,
            API_KEY=TEST_BOOTSTRAP_KEY,
            API_ADMIN_KEY=TEST_ADMIN_KEY,
        )


def test_settings_rejects_production_short_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY is too short for production"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="short-secret",  # pragma: allowlist secret
            API_AUTH_ENABLED=True,
            API_KEY=TEST_BOOTSTRAP_KEY,
            API_ADMIN_KEY=TEST_ADMIN_KEY,
        )


def test_settings_rejects_production_known_weak_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY uses a known weak value"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="changeme",  # pragma: allowlist secret
            API_AUTH_ENABLED=True,
            API_KEY=TEST_BOOTSTRAP_KEY,
            API_ADMIN_KEY=TEST_ADMIN_KEY,
        )


def test_settings_rejects_production_without_auth_enabled() -> None:
    with pytest.raises(ValidationError, match="API_AUTH_ENABLED must be true in production"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="x" * 48,
            API_AUTH_ENABLED=False,
            API_KEY=TEST_BOOTSTRAP_KEY,
            API_ADMIN_KEY=TEST_ADMIN_KEY,
        )


def test_settings_rejects_production_without_admin_key() -> None:
    with pytest.raises(
        ValidationError,
        match="API_ADMIN_KEY must be configured in production",
    ):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="x" * 48,
            API_AUTH_ENABLED=True,
            API_KEY=TEST_BOOTSTRAP_KEY,
            API_ADMIN_KEY=None,
        )


def test_settings_rejects_production_without_bootstrap_key_or_persist_store() -> None:
    with pytest.raises(
        ValidationError,
        match="Production auth requires at least one bootstrap key",
    ):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="x" * 48,
            API_AUTH_ENABLED=True,
            API_ADMIN_KEY=TEST_ADMIN_KEY,
            API_KEY=None,
            API_KEYS=[],
            API_KEYS_PERSIST_PATH=None,
        )


def test_settings_accepts_production_guardrail_compliant_config() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="x" * 48,
        API_AUTH_ENABLED=True,
        API_KEY=TEST_BOOTSTRAP_KEY,
        API_ADMIN_KEY=TEST_ADMIN_KEY,
    )

    assert settings.is_production is True
    assert settings.API_AUTH_ENABLED is True


def test_settings_accepts_production_with_persisted_key_store_bootstrap() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="x" * 48,
        API_AUTH_ENABLED=True,
        API_ADMIN_KEY=TEST_ADMIN_KEY,
        API_KEY=None,
        API_KEYS=[],
        API_KEYS_PERSIST_PATH="/var/lib/horadus/api_keys.json",
    )

    assert settings.is_production is True
    assert settings.API_AUTH_ENABLED is True
