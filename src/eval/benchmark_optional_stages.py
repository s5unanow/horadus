"""Optional benchmark stage dispatch helpers."""

from __future__ import annotations

from typing import Any

from src.eval.benchmark_stages import run_tier2_benchmark_stage


async def run_optional_tier2_benchmark_stage(**kwargs: Any) -> None:
    if kwargs.get("tier2") is None:
        return
    await run_tier2_benchmark_stage(**kwargs)
