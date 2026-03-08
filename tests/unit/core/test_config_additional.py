from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core import config as config_module
from src.core.config import (
    Settings,
    _coerce_pricing_rate_pair,
    _normalize_pricing_key,
    get_settings,
    resolve_llm_token_pricing,
)

pytestmark = pytest.mark.unit


def test_pricing_helpers_cover_validation_and_prefix_matching() -> None:
    assert _normalize_pricing_key(" OpenAI : GPT-5-mini ") == ("openai", "gpt-5-mini")

    with pytest.raises(ValueError, match="provider:model"):
        _normalize_pricing_key("gpt-5-mini")

    assert _coerce_pricing_rate_pair({"input": 1, "output": 2}, key="openai:model") == (1.0, 2.0)
    assert _coerce_pricing_rate_pair([0.1, 0.2], key="openai:model") == (0.1, 0.2)

    with pytest.raises(ValueError, match="input/output"):
        _coerce_pricing_rate_pair("bad", key="openai:model")

    with pytest.raises(ValueError, match="numeric"):
        _coerce_pricing_rate_pair({"input": "x", "output": 1}, key="openai:model")

    with pytest.raises(ValueError, match=">= 0"):
        _coerce_pricing_rate_pair({"input": -1, "output": 1}, key="openai:model")

    with pytest.raises(ValueError, match="finite"):
        _coerce_pricing_rate_pair({"input": math.inf, "output": 1}, key="openai:model")

    table = {
        "openai:gpt-5-mini": (0.25, 2.0),
        "openai:gpt-5": (1.0, 8.0),
    }
    assert resolve_llm_token_pricing(pricing_table=table, provider="OpenAI", model="gpt-5-mini")
    assert resolve_llm_token_pricing(
        pricing_table=table,
        provider="openai",
        model="gpt-5-mini-2026-02-01",
    ) == (0.25, 2.0)
    assert resolve_llm_token_pricing(pricing_table=table, provider="", model="gpt-5-mini") is None
    assert (
        resolve_llm_token_pricing(
            pricing_table=table,
            provider="anthropic",
            model="claude-sonnet",
        )
        is None
    )


def test_settings_parse_collection_and_optional_value_helpers(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        API_HOST="127.0.0.1",
        CORS_ORIGINS=" https://a.example , https://b.example ",
        API_KEYS=" alpha, , beta ",
        DEDUP_URL_TRACKING_PARAM_PREFIXES=("UTM_", "utm_", "clk"),
        DEDUP_URL_TRACKING_PARAMS=123,
        LANGUAGE_POLICY_SUPPORTED_LANGUAGES=[" EN ", "ukrainian", ""],
        CALIBRATION_DRIFT_WEBHOOK_URL=123,
        LLM_PRIMARY_BASE_URL=456,
        OTEL_EXPORTER_OTLP_ENDPOINT=789,
        OTEL_EXPORTER_OTLP_HEADERS="  ",
        AGENT_MODE=True,
        AGENT_DEFAULT_LOG_LEVEL="warning",
    )

    assert settings.CORS_ORIGINS == ["https://a.example", "https://b.example"]
    assert settings.API_KEYS == ["alpha", "beta"]
    assert settings.DEDUP_URL_TRACKING_PARAM_PREFIXES == ["utm_", "clk"]
    assert settings.DEDUP_URL_TRACKING_PARAMS == ["123"]
    assert settings.LANGUAGE_POLICY_SUPPORTED_LANGUAGES == ["en", "uk"]
    assert settings.CALIBRATION_DRIFT_WEBHOOK_URL == "123"
    assert settings.LLM_PRIMARY_BASE_URL == "456"
    assert settings.OTEL_EXPORTER_OTLP_ENDPOINT == "789"
    assert settings.OTEL_EXPORTER_OTLP_HEADERS is None
    assert settings.is_agent_profile is True
    assert settings.effective_log_level == "WARNING"

    defaults = Settings(_env_file=None, LOG_LEVEL="ERROR")
    assert defaults.effective_log_level == "ERROR"

    secret_path = tmp_path / "api_keys.txt"
    secret_path.write_text("alpha, ,beta\n\n", encoding="utf-8")
    file_loaded = Settings(_env_file=None, API_KEYS_FILE=str(secret_path))
    assert file_loaded.API_KEYS == ["alpha", "beta"]


def test_settings_cover_calibration_threshold_and_pricing_parser_edges() -> None:
    settings = Settings(
        _env_file=None,
        CALIBRATION_DRIFT_BRIER_WARN_THRESHOLD=0.1,
        CALIBRATION_DRIFT_BRIER_CRITICAL_THRESHOLD=0.1,
        CALIBRATION_DRIFT_BUCKET_ERROR_WARN_THRESHOLD=0.2,
        CALIBRATION_DRIFT_BUCKET_ERROR_CRITICAL_THRESHOLD=0.2,
        LLM_TOKEN_PRICING_USD_PER_1M="",
    )
    assert pytest.approx(0.1) == settings.CALIBRATION_DRIFT_BRIER_WARN_THRESHOLD
    assert "openai:gpt-4.1-nano" in settings.LLM_TOKEN_PRICING_USD_PER_1M

    with pytest.raises(ValidationError, match="BRIER_WARN_THRESHOLD"):
        Settings(
            _env_file=None,
            CALIBRATION_DRIFT_BRIER_WARN_THRESHOLD=0.2,
            CALIBRATION_DRIFT_BRIER_CRITICAL_THRESHOLD=0.1,
        )

    with pytest.raises(ValidationError, match="BUCKET_ERROR_WARN_THRESHOLD"):
        Settings(
            _env_file=None,
            CALIBRATION_DRIFT_BUCKET_ERROR_WARN_THRESHOLD=0.3,
            CALIBRATION_DRIFT_BUCKET_ERROR_CRITICAL_THRESHOLD=0.2,
        )

    with pytest.raises(ValidationError, match="must be valid JSON"):
        Settings(_env_file=None, LLM_TOKEN_PRICING_USD_PER_1M="{bad")

    with pytest.raises(ValidationError, match="must decode to an object"):
        Settings(_env_file=None, LLM_TOKEN_PRICING_USD_PER_1M="[]")

    with pytest.raises(ValidationError, match="must define at least one provider:model"):
        Settings(_env_file=None, LLM_TOKEN_PRICING_USD_PER_1M="{}")


def test_config_validator_helpers_cover_remaining_branch_residue(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/geoint",
        DATABASE_URL_SYNC="postgresql://postgres@localhost:5432/geoint",
        API_KEYS=123,
        AGENT_DEFAULT_LOG_LEVEL="   ",
        DEDUP_URL_TRACKING_PARAM_PREFIXES=None,
        LANGUAGE_POLICY_SUPPORTED_LANGUAGES=1,
        CALIBRATION_DRIFT_WEBHOOK_URL="   ",
        LLM_PRIMARY_BASE_URL="   ",
        OTEL_EXPORTER_OTLP_ENDPOINT="  ",
        LLM_TIER1_REASONING_EFFORT="   ",
    )
    assert settings.DATABASE_URL_SYNC == "postgresql://postgres@localhost:5432/geoint"
    assert settings.API_KEYS == []
    assert settings.AGENT_DEFAULT_LOG_LEVEL is None
    assert settings.DEDUP_URL_TRACKING_PARAM_PREFIXES == []
    assert settings.LANGUAGE_POLICY_SUPPORTED_LANGUAGES == ["1"]
    assert settings.CALIBRATION_DRIFT_WEBHOOK_URL is None
    assert settings.LLM_PRIMARY_BASE_URL is None
    assert settings.OTEL_EXPORTER_OTLP_ENDPOINT is None
    assert settings.LLM_TIER1_REASONING_EFFORT is None

    assert Settings.parse_llm_token_pricing_table(None) != {}
    assert Settings.parse_dedup_url_param_sets("utm_, fbclid") == ["utm_", "fbclid"]
    assert Settings.parse_supported_languages(None) == ["en", "uk", "ru"]
    assert Settings.parse_supported_languages(["EN", "en"]) == ["en"]


def test_get_settings_returns_cached_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_settings() -> Settings:
        calls.append("called")
        return Settings(_env_file=None)

    get_settings.cache_clear()
    monkeypatch.setattr(config_module, "Settings", fake_settings)

    first = get_settings()
    second = get_settings()

    assert first is second
    assert calls == ["called"]

    get_settings.cache_clear()
