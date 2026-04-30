from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.eval import benchmark as benchmark_module
from tests.unit.eval.test_benchmark import (
    _FakeTier1Classifier,
    _FakeTier2Classifier,
    _write_gold_set,
    _write_trend_configs,
)

pytestmark = pytest.mark.unit


class _UnexpectedTier1Classifier:
    def __init__(self, **kwargs) -> None:
        _ = kwargs
        raise AssertionError("Tier 1 classifier should not be constructed")


class _UnexpectedTier2Classifier:
    def __init__(self, **kwargs) -> None:
        _ = kwargs
        raise AssertionError("Tier 2 classifier should not be constructed")


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_tier1_scope_skips_tier2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FakeTier1Classifier)
    monkeypatch.setattr(benchmark_module, "Tier2Classifier", _UnexpectedTier2Classifier)
    monkeypatch.setattr(
        benchmark_module,
        "_build_openai_client",
        lambda *, api_key, base_url: SimpleNamespace(api_key=api_key, base_url=base_url),
    )

    result_path = await benchmark_module.run_gold_set_benchmark(
        gold_set_path=str(gold_set_path),
        output_dir=str(output_dir),
        api_key="dummy",  # pragma: allowlist secret
        trend_config_dir=str(trend_config_dir),
        max_items=2,
        config_names=["baseline"],
        tier_scope="tier1",
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    config_payload = payload["configs"][0]
    assert payload["items_evaluated"] == 2
    assert payload["dataset_scope"]["tier_scope"] == "tier1"
    assert payload["dataset_scope"]["tier2_label_mode"] == "skipped"
    assert config_payload["tier1_api_mode"] == "chat_completions"
    assert config_payload["tier2_api_mode"] == "skipped"
    assert config_payload["tier1_metrics"]["items_total"] == 2
    assert config_payload["tier2_metrics"]["items_total"] == 0
    assert config_payload["usage"]["tier2_api_calls"] == 0
    assert {row["tier2"]["reason"] for row in config_payload["item_results"]} == {
        "tier_scope_tier1"
    }


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_tier2_scope_skips_tier1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _UnexpectedTier1Classifier)
    monkeypatch.setattr(benchmark_module, "Tier2Classifier", _FakeTier2Classifier)
    monkeypatch.setattr(
        benchmark_module,
        "_build_openai_client",
        lambda *, api_key, base_url: SimpleNamespace(api_key=api_key, base_url=base_url),
    )

    result_path = await benchmark_module.run_gold_set_benchmark(
        gold_set_path=str(gold_set_path),
        output_dir=str(output_dir),
        api_key="dummy",  # pragma: allowlist secret
        trend_config_dir=str(trend_config_dir),
        max_items=2,
        config_names=["baseline"],
        tier_scope="tier2",
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    config_payload = payload["configs"][0]
    assert payload["items_evaluated"] == 1
    assert payload["dataset_scope"]["tier_scope"] == "tier2"
    assert payload["dataset_scope"]["tier2_label_mode"] == "required"
    assert config_payload["tier1_api_mode"] == "skipped"
    assert config_payload["tier2_api_mode"] == "chat_completions"
    assert config_payload["tier1_metrics"]["items_total"] == 0
    assert config_payload["tier2_metrics"]["items_total"] == 1
    assert config_payload["usage"]["tier1_api_calls"] == 0
    item_result = config_payload["item_results"][0]
    assert item_result["item_id"] == "eval-0001"
    assert item_result["tier1"] == {"status": "skipped", "reason": "tier_scope_tier2"}
    assert item_result["tier2"]["status"] == "success"
