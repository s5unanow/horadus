from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.core.config import settings
from src.eval import benchmark as benchmark_module
from src.processing.tier1_classifier import Tier1ItemResult, Tier1Usage, TrendRelevanceScore
from src.processing.tier2_classifier import Tier2EventResult, Tier2Usage

pytestmark = pytest.mark.unit

_STATIC_SOURCE_CONTROL = {
    "git": {
        "available": True,
        "repo_root": "/repo",
        "commit_sha": "abc123",
        "worktree_dirty": False,
        "branch": "main",
    }
}


def _write_gold_set(path: Path) -> None:
    rows = [
        {
            "item_id": "eval-0001",
            "title": "EU-Russia troop movement update",
            "content": "Troop deployment near border expanded with artillery support.",
            "label_verification": "human_verified",
            "expected": {
                "tier1": {
                    "trend_scores": {"eu-russia": 9, "us-china": 2, "middle-east": 1},
                    "max_relevance": 9,
                },
                "tier2": {
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.82,
                    "confidence": 0.91,
                },
            },
        },
        {
            "item_id": "eval-0002",
            "title": "Market recap and weather",
            "content": "General market and weather bulletin with no geopolitical signal.",
            "label_verification": "llm_seeded",
            "expected": {
                "tier1": {
                    "trend_scores": {"eu-russia": 1, "us-china": 1, "middle-east": 1},
                    "max_relevance": 1,
                },
                "tier2": None,
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_sparse_gold_set(path: Path) -> None:
    rows = [
        {
            "item_id": "eval-0001",
            "title": "EU-Russia troop movement update",
            "content": "Troop deployment near border expanded with artillery support.",
            "label_verification": "human_verified",
            "expected": {
                "tier1": {
                    "trend_scores": {"eu-russia": 9, "us-china": 2},
                    "max_relevance": 9,
                },
                "tier2": {
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.82,
                    "confidence": 0.91,
                },
            },
        },
        {
            "item_id": "eval-0002",
            "title": "Market recap and weather",
            "content": "General market and weather bulletin with no geopolitical signal.",
            "label_verification": "llm_seeded",
            "expected": {
                "tier1": {
                    "trend_scores": {"eu-russia": 1},
                    "max_relevance": 1,
                },
                "tier2": None,
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_trend_configs(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    configs = {
        "eu-russia.yaml": {
            "id": "eu-russia",
            "name": "EU-Russia",
            "baseline_probability": 0.2,
            "indicators": {
                "military_movement": {"weight": 0.04, "direction": "escalatory"},
                "diplomatic_breakdown": {"weight": 0.03, "direction": "escalatory"},
            },
        },
        "us-china.yaml": {
            "id": "us-china",
            "name": "US-China",
            "baseline_probability": 0.2,
            "indicators": {
                "diplomatic_engagement": {"weight": 0.03, "direction": "de_escalatory"},
                "trade_restriction": {"weight": 0.03, "direction": "escalatory"},
            },
        },
        "middle-east.yaml": {
            "id": "middle-east",
            "name": "Middle East",
            "baseline_probability": 0.2,
            "indicators": {
                "energy_disruption": {"weight": 0.03, "direction": "escalatory"},
                "ceasefire": {"weight": 0.02, "direction": "de_escalatory"},
            },
        },
    }
    for file_name, payload in configs.items():
        (config_dir / file_name).write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture(autouse=True)
def _stub_source_control_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        benchmark_module.provenance,
        "build_source_control_provenance",
        lambda: _STATIC_SOURCE_CONTROL,
    )


def test_available_configs_include_gpt5_reasoning_candidates() -> None:
    configs = benchmark_module.available_configs()

    assert "tier1-gpt5-nano-minimal" in configs
    assert configs["tier1-gpt5-nano-minimal"].tier1_reasoning_effort == "minimal"
    assert configs["tier1-gpt5-nano-minimal"].tier1_request_overrides is None
    assert "tier1-gpt5-nano-low" in configs
    assert configs["tier1-gpt5-nano-low"].tier1_reasoning_effort == "low"
    assert configs["tier1-gpt5-nano-low"].tier1_request_overrides is None
    assert "tier2-gpt5-mini-low" in configs
    assert configs["tier2-gpt5-mini-low"].tier2_reasoning_effort == "low"
    assert configs["tier2-gpt5-mini-low"].tier2_request_overrides is None
    assert "tier2-gpt5-mini-medium" in configs
    assert configs["tier2-gpt5-mini-medium"].tier2_reasoning_effort == "medium"
    assert configs["tier2-gpt5-mini-medium"].tier2_request_overrides is None


def test_default_configs_exclude_explicit_gpt5_candidates() -> None:
    default_names = benchmark_module.default_config_names()
    resolved = benchmark_module._resolve_configs(None)

    assert default_names == ("baseline", "alternative")
    assert [config.name for config in resolved] == list(default_names)
    assert all("gpt5" not in config.name for config in resolved)


def test_resolve_configs_keeps_explicit_gpt5_candidates_available() -> None:
    resolved = benchmark_module._resolve_configs(
        ["baseline", "tier1-gpt5-nano-minimal", "tier2-gpt5-mini-low"]
    )

    assert [config.name for config in resolved] == [
        "baseline",
        "tier1-gpt5-nano-minimal",
        "tier2-gpt5-mini-low",
    ]


class _FakeTier1Classifier:
    def __init__(
        self,
        *,
        session,
        client,
        model,
        batch_size,
        prompt_path,
        cost_tracker,
        reasoning_effort=None,
        request_overrides=None,
        secondary_client=None,
        semantic_cache=None,
    ) -> None:
        _ = (
            session,
            client,
            model,
            batch_size,
            prompt_path,
            cost_tracker,
            reasoning_effort,
            request_overrides,
            secondary_client,
            semantic_cache,
        )

    async def classify_items(self, items, trends):
        trend_ids = [trend.definition["id"] for trend in trends]
        results: list[Tier1ItemResult] = []
        for item in items:
            is_eu = "eu-russia" in (item.title or "").lower()
            score_map = {
                trend_ids[0]: 9 if is_eu else 1,
                trend_ids[1]: 2 if is_eu else 1,
                trend_ids[2]: 1,
            }
            trend_scores = [
                TrendRelevanceScore(trend_id=trend_id, relevance_score=score)
                for trend_id, score in score_map.items()
            ]
            max_relevance = max(score_map.values())
            results.append(
                Tier1ItemResult(
                    item_id=UUID(str(item.id)),
                    max_relevance=max_relevance,
                    should_queue_tier2=max_relevance >= 6,
                    trend_scores=trend_scores,
                )
            )
        usage = Tier1Usage(
            prompt_tokens=100,
            completion_tokens=10,
            api_calls=1,
            estimated_cost_usd=0.00002,
        )
        return (results, usage)


class _FakeTier2Classifier:
    def __init__(
        self,
        *,
        session,
        client,
        model,
        prompt_path,
        cost_tracker,
        reasoning_effort=None,
        request_overrides=None,
        secondary_client=None,
        semantic_cache=None,
    ) -> None:
        _ = (
            session,
            client,
            model,
            prompt_path,
            cost_tracker,
            reasoning_effort,
            request_overrides,
            secondary_client,
            semantic_cache,
        )

    async def classify_event(self, *, event, trends, context_chunks):
        _ = context_chunks
        event.extracted_claims = {
            "trend_impacts": [
                {
                    "trend_id": trends[0].definition["id"],
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.82,
                    "confidence": 0.91,
                }
            ]
        }
        usage = Tier2Usage(
            prompt_tokens=80,
            completion_tokens=30,
            api_calls=1,
            estimated_cost_usd=0.00003,
        )
        return (
            Tier2EventResult(
                event_id=event.id,
                categories_count=0,
                trend_impacts_count=1,
            ),
            usage,
        )


class _FailingTier1Classifier(_FakeTier1Classifier):
    async def classify_items(self, items, trends):
        if items and "troop movement" in (items[0].title or "").lower():
            self._benchmark_last_raw_output = json.dumps(
                {"items": [{"item_id": str(items[0].id), "trend_scores": []}]}
            )
            msg = "Tier 1 response trend ids mismatch for item"
            raise ValueError(msg)
        return await super().classify_items(items, trends)


class _FailingTier2Classifier(_FakeTier2Classifier):
    async def classify_event(self, *, event, trends, context_chunks):
        _ = (event, trends, context_chunks)
        self._benchmark_last_raw_output = json.dumps(
            {"trend_impacts": [{"trend_id": trends[0].definition["id"]}]}
        )
        msg = "Tier 2 response duplicated trend id eu-russia"
        raise ValueError(msg)


class _MissingTier2PredictionClassifier(_FakeTier2Classifier):
    async def classify_event(self, *, event, trends, context_chunks):
        _ = (trends, context_chunks)
        event.extracted_claims = {}
        self._benchmark_last_raw_output = json.dumps({"trend_impacts": []})
        usage = Tier2Usage(
            prompt_tokens=50,
            completion_tokens=20,
            api_calls=1,
            estimated_cost_usd=0.00002,
        )
        return (
            Tier2EventResult(
                event_id=event.id,
                categories_count=0,
                trend_impacts_count=0,
            ),
            usage,
        )


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_writes_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FakeTier1Classifier)
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
    )

    assert result_path.exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["items_evaluated"] == 2
    assert payload["trend_config_dir"] == str(trend_config_dir)
    assert payload["require_human_verified"] is False
    assert payload["label_verification_counts"] == {"human_verified": 1, "llm_seeded": 1}
    assert payload["dataset_scope"] == {
        "max_items": 2,
        "require_human_verified": False,
        "tier1_label_mode": "sparse_allowed",
    }
    assert payload["execution_mode"] == {
        "dispatch_mode": "realtime",
        "request_priority": "realtime",
        "tier1_batch_size": 1,
        "tier1_batch_policy": "safe_single_item_default",
    }
    assert payload["source_control"] == _STATIC_SOURCE_CONTROL
    assert payload["prompt_provenance"]["tier1"]["path"] == "ai/prompts/tier1_filter.md"
    assert len(payload["prompt_provenance"]["tier1"]["sha256"]) == 64
    assert payload["prompt_provenance"]["tier2"]["path"] == "ai/prompts/tier2_classify.md"
    assert len(payload["prompt_provenance"]["tier2"]["sha256"]) == 64
    assert payload["trend_config_provenance"]["path"] == str(trend_config_dir)
    assert payload["trend_config_provenance"]["file_count"] >= 1
    assert len(payload["trend_config_provenance"]["fingerprint_sha256"]) == 64
    assert isinstance(payload["gold_set_fingerprint_sha256"], str)
    assert len(payload["gold_set_fingerprint_sha256"]) == 64
    assert isinstance(payload["gold_set_item_ids_sha256"], str)
    assert len(payload["gold_set_item_ids_sha256"]) == 64
    assert len(payload["configs"]) == 1
    assert payload["configs"][0]["name"] == "baseline"
    assert payload["configs"][0]["tier1_api_mode"] == "chat_completions"
    assert payload["configs"][0]["tier2_api_mode"] == "chat_completions"
    assert payload["configs"][0]["tier1_reasoning_effort"] is None
    assert payload["configs"][0]["tier2_reasoning_effort"] is None
    assert payload["configs"][0]["tier1_request_overrides"] is None
    assert payload["configs"][0]["tier2_request_overrides"] is None
    assert payload["configs"][0]["elapsed_seconds"] >= 0
    assert payload["configs"][0]["tier1_metrics"]["queue_threshold"] == 5
    assert payload["configs"][0]["tier1_metrics"]["queue_accuracy"] == 1.0
    item_results = payload["configs"][0]["item_results"]
    assert len(item_results) == 2
    assert item_results[0]["item_id"] == "eval-0001"
    assert item_results[0]["tier1"]["status"] == "success"
    assert item_results[0]["tier1"]["predicted"]["max_relevance"] == 9
    assert item_results[0]["tier1"]["predicted"]["trend_scores"]["eu-russia"] == 9
    assert item_results[0]["tier2"]["status"] == "success"
    assert item_results[0]["tier2"]["predicted"]["signal_type"] == "military_movement"
    assert item_results[1]["tier2"] == {"status": "skipped", "reason": "no_tier2_gold_label"}


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_uses_loader_scoped_checkout_stable_trend_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    left_gold_set_path = left_root / "gold_set.jsonl"
    right_gold_set_path = right_root / "gold_set.jsonl"
    left_output_dir = left_root / "results"
    right_output_dir = right_root / "results"
    left_trend_dir = left_root / "trends"
    right_trend_dir = right_root / "trends"

    left_root.mkdir()
    right_root.mkdir()
    _write_gold_set(left_gold_set_path)
    _write_gold_set(right_gold_set_path)
    _write_trend_configs(left_trend_dir)
    _write_trend_configs(right_trend_dir)
    for trend_dir in (left_trend_dir, right_trend_dir):
        nested_dir = trend_dir / "nested"
        nested_dir.mkdir()
        (nested_dir / "ignored.yaml").write_text(
            '{"id":"ignored","name":"Ignored"}', encoding="utf-8"
        )

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FakeTier1Classifier)
    monkeypatch.setattr(benchmark_module, "Tier2Classifier", _FakeTier2Classifier)
    monkeypatch.setattr(
        benchmark_module,
        "_build_openai_client",
        lambda *, api_key, base_url: SimpleNamespace(api_key=api_key, base_url=base_url),
    )

    left_result = await benchmark_module.run_gold_set_benchmark(
        gold_set_path=str(left_gold_set_path),
        output_dir=str(left_output_dir),
        api_key="dummy",  # pragma: allowlist secret
        trend_config_dir=str(left_trend_dir),
        max_items=2,
        config_names=["baseline"],
    )
    right_result = await benchmark_module.run_gold_set_benchmark(
        gold_set_path=str(right_gold_set_path),
        output_dir=str(right_output_dir),
        api_key="dummy",  # pragma: allowlist secret
        trend_config_dir=str(right_trend_dir),
        max_items=2,
        config_names=["baseline"],
    )

    left_payload = json.loads(left_result.read_text(encoding="utf-8"))
    right_payload = json.loads(right_result.read_text(encoding="utf-8"))

    assert left_payload["trend_config_provenance"]["file_count"] == 3
    assert right_payload["trend_config_provenance"]["file_count"] == 3
    assert [item["path"] for item in left_payload["trend_config_provenance"]["files"]] == [
        "eu-russia.yaml",
        "middle-east.yaml",
        "us-china.yaml",
    ]
    assert [item["path"] for item in right_payload["trend_config_provenance"]["files"]] == [
        "eu-russia.yaml",
        "middle-east.yaml",
        "us-china.yaml",
    ]
    assert (
        left_payload["trend_config_provenance"]["fingerprint_sha256"]
        == right_payload["trend_config_provenance"]["fingerprint_sha256"]
    )


def test_load_gold_set_rejects_invalid_rows(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.jsonl"
    invalid_path.write_text('{"item_id":"x"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid gold-set row"):
        benchmark_module.load_gold_set(invalid_path)


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_filters_human_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FakeTier1Classifier)
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
        max_items=10,
        config_names=["baseline"],
        require_human_verified=True,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["items_evaluated"] == 1
    assert payload["require_human_verified"] is True
    assert payload["label_verification_counts"] == {"human_verified": 1}
    assert payload["dataset_scope"] == {
        "max_items": 10,
        "require_human_verified": True,
        "tier1_label_mode": "sparse_allowed",
    }


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_records_stage_specific_request_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FakeTier1Classifier)
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
        max_items=1,
        config_names=["tier1-gpt5-nano-minimal", "tier2-gpt5-mini-medium"],
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    config_payloads = {entry["name"]: entry for entry in payload["configs"]}

    assert config_payloads["tier1-gpt5-nano-minimal"]["tier1_reasoning_effort"] == "minimal"
    assert config_payloads["tier1-gpt5-nano-minimal"]["tier1_request_overrides"] is None
    assert config_payloads["tier1-gpt5-nano-minimal"]["tier2_request_overrides"] is None
    assert config_payloads["tier1-gpt5-nano-minimal"]["elapsed_seconds"] >= 0
    assert config_payloads["tier2-gpt5-mini-medium"]["tier1_reasoning_effort"] is None
    assert config_payloads["tier2-gpt5-mini-medium"]["tier2_reasoning_effort"] == "medium"
    assert config_payloads["tier2-gpt5-mini-medium"]["tier1_request_overrides"] is None
    assert config_payloads["tier2-gpt5-mini-medium"]["tier2_request_overrides"] is None
    assert config_payloads["tier2-gpt5-mini-medium"]["elapsed_seconds"] >= 0


def test_load_gold_set_requires_human_verified_rows(tmp_path: Path) -> None:
    path = tmp_path / "gold_set.jsonl"
    path.write_text(
        json.dumps(
            {
                "item_id": "eval-0002",
                "title": "Market recap and weather",
                "content": "General market and weather bulletin with no geopolitical signal.",
                "label_verification": "llm_seeded",
                "expected": {
                    "tier1": {
                        "trend_scores": {"eu-russia": 1, "us-china": 1, "middle-east": 1},
                        "max_relevance": 1,
                    },
                    "tier2": None,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no human-verified items"):
        benchmark_module.load_gold_set(path, require_human_verified=True)


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_records_tier1_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FailingTier1Classifier)
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
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    tier1_metrics = payload["configs"][0]["tier1_metrics"]
    assert tier1_metrics["items_total"] == 2
    assert tier1_metrics["failures"] == 1
    item_results = payload["configs"][0]["item_results"]
    failed_row = next(row for row in item_results if row["item_id"] == "eval-0001")
    assert failed_row["tier1"]["status"] == "failure"
    assert failed_row["tier1"]["error_category"] == "ValueError"
    assert "trend ids mismatch" in failed_row["tier1"]["error_message"]
    assert '"trend_scores": []' in failed_row["tier1"]["raw_model_output"]


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_records_tier2_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FakeTier1Classifier)
    monkeypatch.setattr(benchmark_module, "Tier2Classifier", _FailingTier2Classifier)
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
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    tier2_metrics = payload["configs"][0]["tier2_metrics"]
    usage = payload["configs"][0]["usage"]
    assert tier2_metrics["items_total"] == 1
    assert tier2_metrics["failures"] == 1
    assert usage["tier2_api_calls"] == 0
    item_results = payload["configs"][0]["item_results"]
    failed_row = next(row for row in item_results if row["item_id"] == "eval-0001")
    assert failed_row["tier2"]["status"] == "failure"
    assert failed_row["tier2"]["error_category"] == "ValueError"
    assert "duplicated trend id" in failed_row["tier2"]["error_message"]
    assert '"trend_id": "eu-russia"' in failed_row["tier2"]["raw_model_output"]


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_records_missing_tier2_prediction_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FakeTier1Classifier)
    monkeypatch.setattr(benchmark_module, "Tier2Classifier", _MissingTier2PredictionClassifier)
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
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    failed_row = next(
        row for row in payload["configs"][0]["item_results"] if row["item_id"] == "eval-0001"
    )
    assert failed_row["tier2"]["status"] == "failure"
    assert failed_row["tier2"]["error_category"] == "MissingPrediction"
    assert "no trend impact prediction" in failed_row["tier2"]["error_message"]
    assert failed_row["tier2"]["raw_model_output"] == '{"trend_impacts": []}'


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_applies_batch_and_flex_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)
    captured: dict[str, object] = {}

    class _CapturingTier1Classifier(_FakeTier1Classifier):
        def __init__(
            self,
            *,
            session,
            client,
            model,
            batch_size,
            prompt_path,
            cost_tracker,
            reasoning_effort=None,
            request_overrides=None,
            secondary_client=None,
            semantic_cache=None,
        ) -> None:
            captured["tier1_batch_size"] = batch_size
            captured["tier1_reasoning_effort"] = reasoning_effort
            captured["tier1_prompt_path"] = prompt_path
            captured["tier1_request_overrides"] = request_overrides
            captured["tier1_secondary_client"] = secondary_client
            super().__init__(
                session=session,
                client=client,
                model=model,
                batch_size=batch_size,
                prompt_path=prompt_path,
                cost_tracker=cost_tracker,
                reasoning_effort=reasoning_effort,
                request_overrides=request_overrides,
                secondary_client=secondary_client,
                semantic_cache=semantic_cache,
            )

    class _CapturingTier2Classifier(_FakeTier2Classifier):
        def __init__(
            self,
            *,
            session,
            client,
            model,
            prompt_path,
            cost_tracker,
            reasoning_effort=None,
            request_overrides=None,
            secondary_client=None,
            semantic_cache=None,
        ) -> None:
            captured["tier2_reasoning_effort"] = reasoning_effort
            captured["tier2_prompt_path"] = prompt_path
            captured["tier2_request_overrides"] = request_overrides
            captured["tier2_secondary_client"] = secondary_client
            super().__init__(
                session=session,
                client=client,
                model=model,
                prompt_path=prompt_path,
                cost_tracker=cost_tracker,
                reasoning_effort=reasoning_effort,
                request_overrides=request_overrides,
                secondary_client=secondary_client,
                semantic_cache=semantic_cache,
            )

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _CapturingTier1Classifier)
    monkeypatch.setattr(benchmark_module, "Tier2Classifier", _CapturingTier2Classifier)
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
        dispatch_mode="batch",
        request_priority="flex",
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["execution_mode"] == {
        "dispatch_mode": "batch",
        "request_priority": "flex",
        "tier1_batch_size": 10,
        "tier1_batch_policy": "diagnostic_multi_item_batch",
    }
    assert captured["tier1_batch_size"] == 10
    assert captured["tier1_reasoning_effort"] is None
    assert captured["tier2_reasoning_effort"] is None
    assert captured["tier1_prompt_path"] == "ai/prompts/tier1_filter.md"
    assert captured["tier2_prompt_path"] == "ai/prompts/tier2_classify.md"
    assert captured["tier1_request_overrides"] == {"service_tier": "flex"}
    assert captured["tier2_request_overrides"] == {"service_tier": "flex"}


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_wraps_secondary_clients_for_response_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)
    captured: dict[str, object] = {}

    class _CapturingTier1Classifier(_FakeTier1Classifier):
        def __init__(
            self,
            *,
            session,
            client,
            model,
            batch_size,
            prompt_path,
            cost_tracker,
            reasoning_effort=None,
            request_overrides=None,
            secondary_client=None,
            semantic_cache=None,
        ) -> None:
            captured["tier1_secondary_client"] = secondary_client
            super().__init__(
                session=session,
                client=client,
                model=model,
                batch_size=batch_size,
                prompt_path=prompt_path,
                cost_tracker=cost_tracker,
                reasoning_effort=reasoning_effort,
                request_overrides=request_overrides,
                secondary_client=secondary_client,
                semantic_cache=semantic_cache,
            )

    class _CapturingTier2Classifier(_FakeTier2Classifier):
        def __init__(
            self,
            *,
            session,
            client,
            model,
            prompt_path,
            cost_tracker,
            reasoning_effort=None,
            request_overrides=None,
            secondary_client=None,
            semantic_cache=None,
        ) -> None:
            captured["tier2_secondary_client"] = secondary_client
            super().__init__(
                session=session,
                client=client,
                model=model,
                prompt_path=prompt_path,
                cost_tracker=cost_tracker,
                reasoning_effort=reasoning_effort,
                request_overrides=request_overrides,
                secondary_client=secondary_client,
                semantic_cache=semantic_cache,
            )

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _CapturingTier1Classifier)
    monkeypatch.setattr(benchmark_module, "Tier2Classifier", _CapturingTier2Classifier)
    monkeypatch.setattr(settings, "LLM_TIER1_SECONDARY_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(settings, "LLM_TIER2_SECONDARY_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(settings, "LLM_SECONDARY_API_KEY", "dummy-secondary")
    monkeypatch.setattr(settings, "LLM_SECONDARY_BASE_URL", "https://secondary.example/v1")
    monkeypatch.setattr(
        benchmark_module,
        "_build_openai_client",
        lambda *, api_key, base_url: SimpleNamespace(
            api_key=api_key,
            base_url=base_url,
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: kwargs)),
        ),
    )

    await benchmark_module.run_gold_set_benchmark(
        gold_set_path=str(gold_set_path),
        output_dir=str(output_dir),
        api_key="dummy",  # pragma: allowlist secret
        trend_config_dir=str(trend_config_dir),
        max_items=2,
        config_names=["baseline"],
    )

    assert captured["tier1_secondary_client"] is not None
    assert captured["tier2_secondary_client"] is not None


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_rejects_invalid_dispatch_mode(tmp_path: Path) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    _write_gold_set(gold_set_path)
    _write_trend_configs(tmp_path / "trends")

    with pytest.raises(ValueError, match="Unsupported dispatch mode"):
        await benchmark_module.run_gold_set_benchmark(
            gold_set_path=str(gold_set_path),
            output_dir=str(output_dir),
            api_key="dummy",  # pragma: allowlist secret
            trend_config_dir=str(tmp_path / "trends"),
            dispatch_mode="invalid",
        )


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_fails_fast_on_taxonomy_mismatch(tmp_path: Path) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    payload = json.loads(gold_set_path.read_text(encoding="utf-8").splitlines()[0])
    payload["expected"]["tier1"]["trend_scores"]["nonexistent-trend"] = 4
    lines = gold_set_path.read_text(encoding="utf-8").splitlines()
    lines[0] = json.dumps(payload)
    gold_set_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Benchmark taxonomy preflight failed"):
        await benchmark_module.run_gold_set_benchmark(
            gold_set_path=str(gold_set_path),
            output_dir=str(output_dir),
            api_key="dummy",  # pragma: allowlist secret
            trend_config_dir=str(trend_config_dir),
            max_items=2,
            config_names=["baseline"],
        )


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_accepts_sparse_tier1_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_sparse_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", _FakeTier1Classifier)
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
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["items_evaluated"] == 2
    assert payload["configs"][0]["tier1_metrics"]["failures"] == 0
