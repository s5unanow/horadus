from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import src.processing.tier2_canary as canary_module
from src.eval.benchmark import GoldSetItem, Tier1GoldLabel, Tier2GoldLabel
from src.storage.models import Event

pytestmark = pytest.mark.unit


def _tier1_label() -> Tier1GoldLabel:
    return Tier1GoldLabel(trend_scores={"eu-russia": 4}, max_relevance=4)


def _tier2_label(
    *,
    trend_id: str = "eu-russia",
    signal_type: str = "military_movement",
    direction: str = "escalatory",
    severity: float = 0.7,
    confidence: float = 0.8,
) -> Tier2GoldLabel:
    return Tier2GoldLabel(
        trend_id=trend_id,
        signal_type=signal_type,
        direction=direction,
        severity=severity,
        confidence=confidence,
    )


def _gold_item(
    *,
    item_id: str,
    verification: str = canary_module.HUMAN_VERIFIED_LABEL,
    tier2: Tier2GoldLabel | None = None,
    content: str = "Border update",
) -> GoldSetItem:
    return GoldSetItem(
        item_id=item_id,
        title=f"Title {item_id}",
        content=content,
        label_verification=verification,
        tier1=_tier1_label(),
        tier2=tier2 if tier2 is not None else _tier2_label(),
    )


def _return_items(items: list[GoldSetItem]):
    def _loader(*_args, **_kwargs):
        return items

    return _loader


def _return_trends(*_args, **_kwargs) -> list[str]:
    return ["trend"]


@pytest.mark.asyncio
async def test_noop_helpers_return_none() -> None:
    assert await canary_module._NoopSession().flush() is None
    tracker = canary_module._NoopCostTracker()
    assert await tracker.ensure_within_budget("tier2") is None
    assert (
        await tracker.record_usage(
            tier="tier2",
            input_tokens=1,
            output_tokens=1,
        )
        is None
    )


def test_event_for_item_truncates_long_content_and_is_deterministic() -> None:
    item = _gold_item(item_id="item-1", content="x" * 500)

    event = canary_module._event_for_item(item)

    assert isinstance(event, Event)
    assert event.id == canary_module._event_for_item(item).id
    assert event.canonical_summary.endswith("...")
    assert len(event.canonical_summary.split(". ", 1)[1]) == 403


def test_extract_first_impact_handles_valid_and_invalid_payloads() -> None:
    event = Event(canonical_summary="Summary", source_count=1, unique_source_count=1)
    assert canary_module._extract_first_impact(event) is None

    event.extracted_claims = {"trend_impacts": []}
    assert canary_module._extract_first_impact(event) is None

    event.extracted_claims = {"trend_impacts": ["bad"]}
    assert canary_module._extract_first_impact(event) is None

    event.extracted_claims = {
        "trend_impacts": [
            {
                "trend_id": "eu-russia",
                "signal_type": "military_movement",
                "direction": "escalatory",
                "severity": "bad",
                "confidence": 0.8,
            }
        ]
    }
    assert canary_module._extract_first_impact(event) is None

    event.extracted_claims = {
        "trend_impacts": [
            {
                "trend_id": "eu-russia",
                "signal_type": "military_movement",
                "direction": "escalatory",
                "severity": 0.7,
                "confidence": 0.8,
            }
        ]
    }
    assert canary_module._extract_first_impact(event) == _tier2_label()


def test_select_tier2_items_filters_sorts_and_respects_minimum_slice() -> None:
    items = [
        _gold_item(item_id="b"),
        _gold_item(item_id="a", verification="machine"),
        _gold_item(item_id="c", tier2=None),
        _gold_item(item_id="d"),
    ]

    selected = canary_module._select_tier2_items(items, max_items=0)

    assert [item.item_id for item in selected] == ["b"]


def test_evaluate_pass_reports_each_threshold_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_FAILURE_RATE", 0.2)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_TREND_MATCH_ACCURACY", 0.8)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_SIGNAL_TYPE_ACCURACY", 0.8)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_DIRECTION_ACCURACY", 0.8)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_SEVERITY_MAE", 0.2)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_CONFIDENCE_MAE", 0.2)

    no_items = canary_module.Tier2CanaryMetrics(0, 0, 0, 0, 0, 0, 0)
    assert canary_module._evaluate_pass(no_items) == (False, "no_items")

    too_many_failures = canary_module.Tier2CanaryMetrics(10, 3, 1, 1, 1, 0, 0)
    assert canary_module._evaluate_pass(too_many_failures)[0] is False

    bad_trend = canary_module.Tier2CanaryMetrics(10, 0, 0.7, 1, 1, 0, 0)
    assert canary_module._evaluate_pass(bad_trend)[1].startswith("trend_match_accuracy")

    bad_signal = canary_module.Tier2CanaryMetrics(10, 0, 0.8, 0.7, 1, 0, 0)
    assert canary_module._evaluate_pass(bad_signal)[1].startswith("signal_type_accuracy")

    bad_direction = canary_module.Tier2CanaryMetrics(10, 0, 0.8, 0.8, 0.7, 0, 0)
    assert canary_module._evaluate_pass(bad_direction)[1].startswith("direction_accuracy")

    bad_severity = canary_module.Tier2CanaryMetrics(10, 0, 0.8, 0.8, 0.8, 0.3, 0)
    assert canary_module._evaluate_pass(bad_severity)[1].startswith("severity_mae")

    bad_confidence = canary_module.Tier2CanaryMetrics(10, 0, 0.8, 0.8, 0.8, 0.1, 0.3)
    assert canary_module._evaluate_pass(bad_confidence)[1].startswith("confidence_mae")

    healthy = canary_module.Tier2CanaryMetrics(10, 0, 0.9, 0.9, 0.9, 0.1, 0.1)
    assert canary_module._evaluate_pass(healthy) == (True, "ok")


@pytest.mark.asyncio
async def test_run_tier2_canary_returns_missing_api_key_without_calling_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canary_module.settings, "OPENAI_API_KEY", "")

    result = await canary_module.run_tier2_canary(model="gpt-test")

    assert result.passed is False
    assert result.reason == "missing_api_key"
    assert result.metrics.items_total == 0


@pytest.mark.asyncio
async def test_run_tier2_canary_returns_empty_selection_when_no_human_verified_tier2_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canary_module.settings, "OPENAI_API_KEY", "x")
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_GOLD_SET_PATH", "gold.jsonl")
    monkeypatch.setattr(
        canary_module,
        "load_gold_set",
        _return_items([_gold_item(item_id="a", verification="machine")]),
    )

    result = await canary_module.run_tier2_canary(model="gpt-test")

    assert result.passed is False
    assert result.reason == "empty_selection"
    assert result.metrics.items_total == 0


@pytest.mark.asyncio
async def test_run_tier2_canary_evaluates_predictions_and_logs_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        _gold_item(item_id="a"),
        _gold_item(item_id="b"),
        _gold_item(
            item_id="c", tier2=_tier2_label(trend_id="trend-c", severity=0.4, confidence=0.6)
        ),
        _gold_item(item_id="d", verification="machine"),
    ]
    logger = MagicMock()
    client_factory = MagicMock(return_value="client")
    classifier_instances: list[object] = []

    class _FakeTier2Classifier:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.calls = 0
            classifier_instances.append(self)

        async def classify_event(self, *, event: Event, trends, context_chunks) -> None:
            _ = (trends, context_chunks)
            self.calls += 1
            if self.calls == 1:
                event.extracted_claims = {
                    "trend_impacts": [
                        {
                            "trend_id": "eu-russia",
                            "signal_type": "military_movement",
                            "direction": "escalatory",
                            "severity": 0.7,
                            "confidence": 0.8,
                        }
                    ]
                }
                return
            if self.calls == 2:
                raise RuntimeError("tier2 failed")
            event.extracted_claims = {
                "trend_impacts": [
                    {
                        "trend_id": "trend-c",
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                        "severity": 0.1,
                        "confidence": 0.2,
                    }
                ]
            }

    monkeypatch.setattr(canary_module, "logger", logger)
    monkeypatch.setattr(canary_module.settings, "OPENAI_API_KEY", "x")
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_GOLD_SET_PATH", "gold.jsonl")
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_TIER2_ITEMS", 5)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_FAILURE_RATE", 0.5)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_TREND_MATCH_ACCURACY", 0.3)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_SIGNAL_TYPE_ACCURACY", 0.3)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_DIRECTION_ACCURACY", 0.3)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_SEVERITY_MAE", 0.5)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_CONFIDENCE_MAE", 0.39)
    monkeypatch.setattr(canary_module, "load_gold_set", _return_items(items))
    monkeypatch.setattr(canary_module, "load_trends_from_config_dir", _return_trends)
    monkeypatch.setattr(canary_module, "AsyncOpenAI", client_factory)
    monkeypatch.setattr(canary_module, "Tier2Classifier", _FakeTier2Classifier)

    result = await canary_module.run_tier2_canary(
        model="gpt-test",
        base_url=" https://example.test/v1 ",
        gold_set_path="gold.jsonl",
        trend_config_dir="config/trends",
        max_items=4,
        request_overrides={"temperature": 0},
    )

    assert result.model == "gpt-test"
    assert result.metrics.items_total == 3
    assert result.metrics.failures == 1
    assert result.metrics.trend_match_accuracy == pytest.approx(2 / 3)
    assert result.metrics.signal_type_accuracy == pytest.approx(2 / 3)
    assert result.metrics.direction_accuracy == pytest.approx(2 / 3)
    assert result.metrics.severity_mae == pytest.approx((0.0 + 0.7 + 0.3) / 3)
    assert result.metrics.confidence_mae == pytest.approx((0.0 + 0.8 + 0.4) / 3)
    assert result.passed is False
    assert result.reason.startswith("confidence_mae")
    client_factory.assert_called_once_with(
        api_key="x",  # pragma: allowlist secret
        base_url="https://example.test/v1",
    )
    assert classifier_instances[0].kwargs["request_overrides"] == {"temperature": 0}
    logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_run_tier2_canary_uses_default_client_without_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_gold_item(item_id="a")]
    client_factory = MagicMock(return_value="client")

    class _FakeTier2Classifier:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def classify_event(self, *, event: Event, trends, context_chunks) -> None:
            _ = (trends, context_chunks)
            event.extracted_claims = {
                "trend_impacts": [
                    {
                        "trend_id": "eu-russia",
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                        "severity": 0.7,
                        "confidence": 0.8,
                    }
                ]
            }

    monkeypatch.setattr(canary_module.settings, "OPENAI_API_KEY", "x")
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_GOLD_SET_PATH", "gold.jsonl")
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_TIER2_ITEMS", 1)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_FAILURE_RATE", 1.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_TREND_MATCH_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_SIGNAL_TYPE_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_DIRECTION_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_SEVERITY_MAE", 1.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_CONFIDENCE_MAE", 1.0)
    monkeypatch.setattr(canary_module, "load_gold_set", _return_items(items))
    monkeypatch.setattr(canary_module, "load_trends_from_config_dir", _return_trends)
    monkeypatch.setattr(canary_module, "AsyncOpenAI", client_factory)
    monkeypatch.setattr(canary_module, "Tier2Classifier", _FakeTier2Classifier)

    result = await canary_module.run_tier2_canary(model="gpt-test", base_url="   ")

    assert result.passed is True
    assert result.reason == "ok"
    client_factory.assert_called_once_with(api_key="x")  # pragma: allowlist secret


@pytest.mark.asyncio
async def test_run_tier2_canary_skips_selected_items_without_expected_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unlabeled = _gold_item(item_id="a")
    unlabeled.tier2 = None

    class _FakeTier2Classifier:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def classify_event(self, *, event: Event, trends, context_chunks) -> None:
            _ = (event, trends, context_chunks)
            raise AssertionError("classifier should not be called")

    monkeypatch.setattr(canary_module.settings, "OPENAI_API_KEY", "x")
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_FAILURE_RATE", 1.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_TREND_MATCH_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_SIGNAL_TYPE_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_DIRECTION_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_SEVERITY_MAE", 1.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_CONFIDENCE_MAE", 1.0)
    monkeypatch.setattr(canary_module, "load_gold_set", _return_items([_gold_item(item_id="b")]))
    monkeypatch.setattr(canary_module, "_select_tier2_items", lambda *_args, **_kwargs: [unlabeled])
    monkeypatch.setattr(canary_module, "load_trends_from_config_dir", _return_trends)
    monkeypatch.setattr(canary_module, "AsyncOpenAI", MagicMock(return_value="client"))
    monkeypatch.setattr(canary_module, "Tier2Classifier", _FakeTier2Classifier)

    result = await canary_module.run_tier2_canary(model="gpt-test")

    assert result.metrics.items_total == 1
    assert result.metrics.failures == 0
    assert result.metrics.trend_match_accuracy == 0.0


@pytest.mark.asyncio
async def test_run_tier2_canary_counts_invalid_predictions_as_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_gold_item(item_id="a", tier2=_tier2_label(direction="deescalatory"))]

    class _FakeTier2Classifier:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def classify_event(self, *, event: Event, trends, context_chunks) -> None:
            _ = (trends, context_chunks)
            event.extracted_claims = {"trend_impacts": [{"trend_id": "broken", "severity": "bad"}]}

    monkeypatch.setattr(canary_module.settings, "OPENAI_API_KEY", "x")
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_FAILURE_RATE", 1.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_TREND_MATCH_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_SIGNAL_TYPE_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MIN_DIRECTION_ACCURACY", 0.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_SEVERITY_MAE", 1.0)
    monkeypatch.setattr(canary_module.settings, "LLM_DEGRADED_CANARY_MAX_CONFIDENCE_MAE", 1.0)
    monkeypatch.setattr(canary_module, "load_gold_set", _return_items(items))
    monkeypatch.setattr(canary_module, "load_trends_from_config_dir", _return_trends)
    monkeypatch.setattr(canary_module, "AsyncOpenAI", MagicMock(return_value="client"))
    monkeypatch.setattr(canary_module, "Tier2Classifier", _FakeTier2Classifier)

    result = await canary_module.run_tier2_canary(model="gpt-test")

    assert result.metrics.items_total == 1
    assert result.metrics.failures == 1
    assert result.metrics.severity_mae == pytest.approx(0.7)
    assert result.metrics.confidence_mae == pytest.approx(0.8)
