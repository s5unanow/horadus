"""
Provider/model pricing helpers for estimated LLM cost reporting.
"""

from __future__ import annotations

from typing import Final

MODEL_PRICING_USD_PER_1M: Final[dict[str, tuple[float, float]]] = {
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.00),
    "text-embedding-3-large": (0.13, 0.00),
}


def price_for_model(model: str) -> tuple[float, float]:
    """
    Resolve input/output price per 1M tokens for a model name.

    Supports exact match and prefixed deployment names.
    """
    direct = MODEL_PRICING_USD_PER_1M.get(model)
    if direct is not None:
        return direct

    for known_model, pricing in MODEL_PRICING_USD_PER_1M.items():
        if model.startswith(known_model):
            return pricing
    return (0.0, 0.0)


def estimate_model_cost_usd(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate request cost in USD from token counts and model pricing."""
    input_price, output_price = price_for_model(model)
    safe_prompt = max(0, int(prompt_tokens))
    safe_completion = max(0, int(completion_tokens))
    return (safe_prompt * input_price) / 1_000_000 + (safe_completion * output_price) / 1_000_000
