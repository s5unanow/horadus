from __future__ import annotations

import pytest

from src.processing.llm_pricing import estimate_model_cost_usd, price_for_model

pytestmark = pytest.mark.unit


def test_price_for_model_supports_exact_and_prefix_lookup() -> None:
    assert price_for_model("gpt-4.1-mini") == (0.40, 1.60)
    assert price_for_model("gpt-4.1-mini-2026-02-01") == (0.40, 1.60)


def test_price_for_model_returns_zero_for_unknown_model() -> None:
    assert price_for_model("unknown-model") == (0.0, 0.0)


def test_estimate_model_cost_usd_uses_model_pricing() -> None:
    cost = estimate_model_cost_usd(
        model="gpt-4.1-nano",
        prompt_tokens=100,
        completion_tokens=20,
    )
    assert cost == pytest.approx(0.000018, rel=0.001)
