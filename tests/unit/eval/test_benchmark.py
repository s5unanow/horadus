from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.eval import benchmark as benchmark_module
from src.processing.tier1_classifier import Tier1ItemResult, Tier1Usage, TrendRelevanceScore
from src.processing.tier2_classifier import Tier2EventResult, Tier2Usage

pytestmark = pytest.mark.unit


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


class _FakeTier1Classifier:
    def __init__(
        self,
        *,
        session,
        client,
        model,
        batch_size,
        cost_tracker,
        request_overrides=None,
    ) -> None:
        _ = (session, client, model, batch_size, cost_tracker, request_overrides)

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
        cost_tracker,
        request_overrides=None,
    ) -> None:
        _ = (session, client, model, cost_tracker, request_overrides)

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
            msg = "Tier 1 response trend ids mismatch for item"
            raise ValueError(msg)
        return await super().classify_items(items, trends)


class _FailingTier2Classifier(_FakeTier2Classifier):
    async def classify_event(self, *, event, trends, context_chunks):
        _ = (event, trends, context_chunks)
        msg = "Tier 2 response duplicated trend id eu-russia"
        raise ValueError(msg)


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_writes_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    _write_gold_set(gold_set_path)

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
        max_items=2,
        config_names=["baseline"],
    )

    assert result_path.exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["items_evaluated"] == 2
    assert payload["require_human_verified"] is False
    assert payload["label_verification_counts"] == {"human_verified": 1, "llm_seeded": 1}
    assert payload["dataset_scope"] == {"max_items": 2, "require_human_verified": False}
    assert isinstance(payload["gold_set_fingerprint_sha256"], str)
    assert len(payload["gold_set_fingerprint_sha256"]) == 64
    assert isinstance(payload["gold_set_item_ids_sha256"], str)
    assert len(payload["gold_set_item_ids_sha256"]) == 64
    assert len(payload["configs"]) == 1
    assert payload["configs"][0]["name"] == "baseline"
    assert payload["configs"][0]["tier1_metrics"]["queue_threshold"] == 5
    assert payload["configs"][0]["tier1_metrics"]["queue_accuracy"] == 1.0


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
    _write_gold_set(gold_set_path)

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
        max_items=10,
        config_names=["baseline"],
        require_human_verified=True,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["items_evaluated"] == 1
    assert payload["require_human_verified"] is True
    assert payload["label_verification_counts"] == {"human_verified": 1}
    assert payload["dataset_scope"] == {"max_items": 10, "require_human_verified": True}


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
    _write_gold_set(gold_set_path)

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
        max_items=2,
        config_names=["baseline"],
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    tier1_metrics = payload["configs"][0]["tier1_metrics"]
    assert tier1_metrics["items_total"] == 2
    assert tier1_metrics["failures"] == 1


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_records_tier2_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    _write_gold_set(gold_set_path)

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
        max_items=2,
        config_names=["baseline"],
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    tier2_metrics = payload["configs"][0]["tier2_metrics"]
    usage = payload["configs"][0]["usage"]
    assert tier2_metrics["items_total"] == 1
    assert tier2_metrics["failures"] == 1
    assert usage["tier2_api_calls"] == 0


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_applies_batch_and_flex_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    _write_gold_set(gold_set_path)
    captured: dict[str, object] = {}

    class _CapturingTier1Classifier(_FakeTier1Classifier):
        def __init__(
            self,
            *,
            session,
            client,
            model,
            batch_size,
            cost_tracker,
            request_overrides=None,
        ) -> None:
            captured["tier1_batch_size"] = batch_size
            captured["tier1_request_overrides"] = request_overrides
            super().__init__(
                session=session,
                client=client,
                model=model,
                batch_size=batch_size,
                cost_tracker=cost_tracker,
                request_overrides=request_overrides,
            )

    class _CapturingTier2Classifier(_FakeTier2Classifier):
        def __init__(
            self,
            *,
            session,
            client,
            model,
            cost_tracker,
            request_overrides=None,
        ) -> None:
            captured["tier2_request_overrides"] = request_overrides
            super().__init__(
                session=session,
                client=client,
                model=model,
                cost_tracker=cost_tracker,
                request_overrides=request_overrides,
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
        max_items=2,
        config_names=["baseline"],
        dispatch_mode="batch",
        request_priority="flex",
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["execution_mode"] == {"dispatch_mode": "batch", "request_priority": "flex"}
    assert captured["tier1_batch_size"] == 10
    assert captured["tier1_request_overrides"] == {"service_tier": "flex"}
    assert captured["tier2_request_overrides"] == {"service_tier": "flex"}


@pytest.mark.asyncio
async def test_run_gold_set_benchmark_rejects_invalid_dispatch_mode(tmp_path: Path) -> None:
    gold_set_path = tmp_path / "gold_set.jsonl"
    output_dir = tmp_path / "results"
    _write_gold_set(gold_set_path)

    with pytest.raises(ValueError, match="Unsupported dispatch mode"):
        await benchmark_module.run_gold_set_benchmark(
            gold_set_path=str(gold_set_path),
            output_dir=str(output_dir),
            api_key="dummy",  # pragma: allowlist secret
            dispatch_mode="invalid",
        )
