from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.eval import benchmark as benchmark_module
from src.processing.tier1_classifier import Tier1ItemResult, Tier1Usage, TrendRelevanceScore
from src.processing.tier2_classifier import Tier2Usage
from src.storage.models import Event

pytestmark = pytest.mark.unit


def _gold_item(*, item_id: str = "eval-1", label_verification: str = "human_verified"):
    return benchmark_module.GoldSetItem(
        item_id=item_id,
        title="Title",
        content="Content",
        label_verification=label_verification,
        tier1=benchmark_module.Tier1GoldLabel(
            trend_scores={"eu-russia": 8},
            max_relevance=8,
        ),
        tier2=benchmark_module.Tier2GoldLabel(
            trend_id="eu-russia",
            signal_type="military_movement",
            direction="escalatory",
            severity=0.8,
            confidence=0.9,
        ),
    )


def _write_gold_set(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "item_id": "eval-0001",
                "title": "EU-Russia troop movement update",
                "content": "Troop deployment near border expanded with artillery support.",
                "label_verification": "human_verified",
                "expected": {
                    "tier1": {"trend_scores": {"eu-russia": 9}, "max_relevance": 9},
                    "tier2": {
                        "trend_id": "eu-russia",
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                        "severity": 0.82,
                        "confidence": 0.91,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_trend_configs(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "eu-russia.yaml").write_text(
        json.dumps(
            {
                "id": "eu-russia",
                "name": "EU-Russia",
                "baseline_probability": 0.2,
                "indicators": {"military_movement": {"weight": 0.04, "direction": "escalatory"}},
            }
        ),
        encoding="utf-8",
    )


def test_benchmark_helper_functions_cover_normalization_and_serialization() -> None:
    assert benchmark_module._normalize_dispatch_mode(" Realtime ") == "realtime"
    assert benchmark_module._normalize_request_priority(" FLEX ") == "flex"
    assert benchmark_module._request_overrides_for_priority("realtime") is None
    assert benchmark_module._request_overrides_for_priority("flex") == {"service_tier": "flex"}
    assert benchmark_module._merge_request_overrides(None, {"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
    assert benchmark_module._tier1_batch_settings_for_dispatch("realtime") == (
        1,
        "safe_single_item_default",
    )
    assert benchmark_module._tier1_batch_settings_for_dispatch("batch") == (
        10,
        "diagnostic_multi_item_batch",
    )
    assert benchmark_module._count_label_verification(
        [_gold_item(item_id="a", label_verification="llm_seeded"), _gold_item(item_id="b")]
    ) == {"human_verified": 1, "llm_seeded": 1}

    predicted = Tier1ItemResult(
        item_id=uuid4(),
        max_relevance=7,
        should_queue_tier2=True,
        trend_scores=[TrendRelevanceScore(trend_id="eu-russia", relevance_score=7)],
    )
    assert benchmark_module._serialize_tier1_prediction(predicted) == {
        "max_relevance": 7,
        "should_queue_tier2": True,
        "trend_scores": {"eu-russia": 7},
    }
    assert (
        benchmark_module._usage_to_dict(
            tier1_usage=Tier1Usage(estimated_cost_usd=1.0),
            tier2_usage=Tier2Usage(estimated_cost_usd=2.0),
            items_total=0,
        )["estimated_cost_per_item_usd"]
        == 0.0
    )

    failure = benchmark_module._stage_failure(
        error_category="ValueError",
        error_message="bad",
        raw_model_output=None,
    )
    success = benchmark_module._stage_success(predicted={"ok": True}, raw_model_output="{}")
    assert "raw_model_output" not in failure
    assert success["raw_model_output"] == "{}"

    tier2_pred = benchmark_module.Tier2GoldLabel(
        trend_id="eu-russia",
        signal_type="military_movement",
        direction="escalatory",
        severity=0.8,
        confidence=0.9,
    )
    assert benchmark_module._serialize_tier2_prediction(tier2_pred)["confidence"] == pytest.approx(
        0.9
    )


def test_benchmark_helper_functions_cover_wrappers_and_output_fallbacks() -> None:
    client = SimpleNamespace()
    recorder = benchmark_module._BenchmarkResponseRecorder()
    assert benchmark_module._wrap_client_with_recorder(client=client, recorder=recorder) is client

    recorder.capture_response(SimpleNamespace(choices=[]))
    assert recorder.last_raw_output is None
    recorder.capture_response(
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" "))])
    )
    assert recorder.last_raw_output is None
    recorder.capture_response(
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])
    )
    assert recorder.last_raw_output == '{"ok":true}'
    recorder.reset()
    recorder.capture_response(SimpleNamespace(choices=[SimpleNamespace(message=None)]))
    assert recorder.last_raw_output is None
    assert (
        benchmark_module._extract_stage_raw_output(
            recorder=recorder,
            subject=SimpleNamespace(_benchmark_last_raw_output="fallback"),
        )
        == "fallback"
    )
    assert (
        benchmark_module._extract_stage_raw_output(
            recorder=recorder,
            subject=SimpleNamespace(_benchmark_last_raw_output="   "),
        )
        is None
    )

    event = Event(id=uuid4(), extracted_claims={"trend_impacts": [{"trend_id": "a"}]})
    event.extracted_claims = None
    assert benchmark_module._extract_first_impact(event) is None
    event.extracted_claims = {"trend_impacts": ["bad"]}
    assert benchmark_module._extract_first_impact(event) is None
    event.extracted_claims = {"trend_impacts": [{"trend_id": "a"}]}
    assert benchmark_module._extract_first_impact(event) is None
    event.extracted_claims = {
        "trend_impacts": [
            {
                "trend_id": "a",
                "signal_type": "b",
                "direction": "c",
                "severity": "0.4",
                "confidence": "0.6",
            }
        ]
    }
    impact = benchmark_module._extract_first_impact(event)
    assert impact is not None
    assert impact.severity == pytest.approx(0.4)


def test_benchmark_load_gold_set_and_config_helpers_cover_error_paths(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    with pytest.raises(FileNotFoundError, match="Gold set file not found"):
        benchmark_module.load_gold_set(missing)

    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Gold set is empty"):
        benchmark_module.load_gold_set(empty)

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(
        json.dumps(
            {
                "item_id": "x",
                "title": "t",
                "content": "c",
                "expected": {"tier1": {"trend_scores": {"a": "bad"}, "max_relevance": 1}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid tier1 trend score"):
        benchmark_module.load_gold_set(invalid)

    invalid_tier2 = tmp_path / "invalid_tier2.jsonl"
    invalid_tier2.write_text(
        json.dumps(
            {
                "item_id": "x",
                "title": "t",
                "content": "c",
                "expected": {"tier1": {"trend_scores": {"a": 1}, "max_relevance": 1}, "tier2": []},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid tier2 labels"):
        benchmark_module.load_gold_set(invalid_tier2)

    missing_tier1 = tmp_path / "missing_tier1.jsonl"
    missing_tier1.write_text(
        json.dumps({"item_id": "x", "title": "t", "content": "c", "expected": {}}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Missing tier1 labels"):
        benchmark_module.load_gold_set(missing_tier1)

    invalid_tier2_fields = tmp_path / "invalid_tier2_fields.jsonl"
    invalid_tier2_fields.write_text(
        json.dumps(
            {
                "item_id": "x",
                "title": "t",
                "content": "c",
                "expected": {
                    "tier1": {"trend_scores": {"a": 1}, "max_relevance": 1},
                    "tier2": {"trend_id": "a"},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid tier2 labels"):
        benchmark_module.load_gold_set(invalid_tier2_fields)

    invalid_tier1_labels = tmp_path / "invalid_tier1_labels.jsonl"
    invalid_tier1_labels.write_text(
        json.dumps(
            {
                "item_id": "x",
                "title": "t",
                "content": "c",
                "expected": {"tier1": {"trend_scores": {"a": 1}, "max_relevance": "bad"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid tier1 labels"):
        benchmark_module.load_gold_set(invalid_tier1_labels)

    assert len(benchmark_module._resolve_configs(None)) >= 1
    assert benchmark_module._resolve_configs(["baseline"])[0].name == "baseline"
    with pytest.raises(ValueError, match="Unknown benchmark config"):
        benchmark_module._resolve_configs(["unknown"])
    with pytest.raises(ValueError, match="Unsupported request priority"):
        benchmark_module._normalize_request_priority("urgent")

    assert "alpha(4; sample=1, 2, 3, +1 more)" in benchmark_module._format_group_summary(
        {"alpha": ["1", "2", "3", "4"]}
    )
    assert "+1 more" in benchmark_module._format_group_summary(
        {"a": ["1"], "b": ["1"], "c": ["1"]},
        limit=2,
    )


def test_benchmark_taxonomy_alignment_and_secondary_client_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trends = [
        SimpleNamespace(
            definition={"id": "eu-russia"},
            indicators={"military_movement": {}, "sanctions": {}},
        )
    ]

    with pytest.raises(ValueError, match="unknown trend_id"):
        benchmark_module._assert_gold_set_taxonomy_alignment(
            items=[
                _gold_item(item_id="a"),
                _gold_item(item_id="b", label_verification="llm_seeded"),
            ],
            trends=[],
        )

    item = _gold_item()
    item.tier2 = benchmark_module.Tier2GoldLabel(
        trend_id="eu-russia",
        signal_type="unknown-signal",
        direction="escalatory",
        severity=0.8,
        confidence=0.9,
    )
    with pytest.raises(ValueError, match="unknown signal_type"):
        benchmark_module._assert_gold_set_taxonomy_alignment(items=[item], trends=trends)

    monkeypatch.setattr(
        benchmark_module,
        "_build_openai_client",
        lambda *, api_key, base_url: SimpleNamespace(
            api_key=api_key,
            base_url=base_url,
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    api_key=api_key,
                    create=lambda **kwargs: SimpleNamespace(kwargs=kwargs),
                )
            ),
        ),
    )
    monkeypatch.setattr(benchmark_module.settings, "LLM_SECONDARY_API_KEY", None)
    monkeypatch.setattr(benchmark_module.settings, "LLM_SECONDARY_BASE_URL", "https://secondary")
    primary_api_key = "benchmark-test-key"  # pragma: allowlist secret

    assert (
        benchmark_module._build_benchmark_secondary_client(
            primary_api_key=primary_api_key,
            secondary_model=None,
            recorder=benchmark_module._BenchmarkResponseRecorder(),
        )
        is None
    )

    client = benchmark_module._build_benchmark_secondary_client(
        primary_api_key=primary_api_key,
        secondary_model="gpt-4o-mini",
        recorder=benchmark_module._BenchmarkResponseRecorder(),
    )
    assert client.chat.completions._wrapped.api_key == primary_api_key


def test_build_openai_client_rejects_blank_key_and_item_result_includes_skip_reason() -> None:
    with pytest.raises(ValueError, match="API key is required"):
        benchmark_module._build_openai_client(api_key=" ", base_url=None)
    assert str(
        benchmark_module._build_openai_client(
            api_key="dummy",  # pragma: allowlist secret
            base_url=" https://api.example/v1 ",
        ).base_url
    ).startswith("https://api.example/v1")
    assert str(
        benchmark_module._build_openai_client(
            api_key="dummy",  # pragma: allowlist secret
            base_url="   ",
        ).base_url
    ).startswith("https://api.openai.com/v1")

    item = _gold_item()
    item.tier2 = None
    result = benchmark_module._build_item_result(item)
    assert result["tier2"] == {"status": "skipped", "reason": "no_tier2_gold_label"}


def test_metric_helpers_and_noop_classes_cover_remaining_paths() -> None:
    metrics = benchmark_module._Tier1Metrics(queue_threshold=5)
    gold = _gold_item()
    metrics.record(
        gold=gold,
        predicted=Tier1ItemResult(
            item_id=uuid4(),
            max_relevance=9,
            should_queue_tier2=False,
            trend_scores=[TrendRelevanceScore(trend_id="other", relevance_score=1)],
        ),
    )
    assert metrics.to_dict()["queue_accuracy"] == 0.0

    tier2_metrics = benchmark_module._Tier2Metrics()
    tier2_metrics.record(
        expected=gold.tier2,
        predicted=benchmark_module.Tier2GoldLabel(
            trend_id="other",
            signal_type="other",
            direction="de_escalatory",
            severity=0.1,
            confidence=0.2,
        ),
    )
    assert tier2_metrics.to_dict()["trend_match_accuracy"] == 0.0


@pytest.mark.asyncio
async def test_noop_classes_recording_wrapper_and_missing_prediction_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await benchmark_module._NoopSession().flush()
    await benchmark_module._NoopCostTracker().ensure_within_budget("tier1", provider="x", model="y")
    await benchmark_module._NoopCostTracker().record_usage(
        tier="tier1",
        input_tokens=1,
        output_tokens=1,
        provider="x",
        model="y",
    )

    class Wrapped:
        async def create(self, **kwargs):
            return SimpleNamespace(
                kwargs=kwargs,
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],
            )

    recorder = benchmark_module._BenchmarkResponseRecorder()
    response = await benchmark_module._RecordingChatCompletions(
        wrapped=Wrapped(),
        recorder=recorder,
    ).create(x=1)
    assert response.kwargs == {"x": 1}
    assert recorder.last_raw_output == '{"ok":true}'
    assert (
        benchmark_module._extract_stage_raw_output(
            recorder=benchmark_module._BenchmarkResponseRecorder(last_raw_output="cached"),
            subject=SimpleNamespace(),
        )
        == "cached"
    )

    gold_set_path = tmp_path / "gold.jsonl"
    output_dir = tmp_path / "results"
    trend_config_dir = tmp_path / "trends"
    _write_gold_set(gold_set_path)
    _write_trend_configs(trend_config_dir)

    class MissingTier1PredictionClassifier:
        def __init__(self, **kwargs) -> None:
            _ = kwargs

        async def classify_items(self, items, trends):
            _ = (items, trends)
            self._benchmark_last_raw_output = '{"items":[]}'
            return ([], Tier1Usage(prompt_tokens=1, completion_tokens=1, api_calls=1))

    class FakeTier2Classifier:
        def __init__(self, **kwargs) -> None:
            _ = kwargs

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
            return (SimpleNamespace(event_id=event.id), Tier2Usage(api_calls=1))

    monkeypatch.setattr(benchmark_module, "Tier1Classifier", MissingTier1PredictionClassifier)
    monkeypatch.setattr(benchmark_module, "Tier2Classifier", FakeTier2Classifier)
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
        config_names=["baseline"],
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert (
        payload["configs"][0]["item_results"][0]["tier1"]["error_category"] == "MissingPrediction"
    )
