from __future__ import annotations

import pytest

from src.processing.degraded_llm_tracker import (
    DegradedLLMWindow,
    compute_availability_degraded,
    compute_availability_recovered,
)

pytestmark = pytest.mark.unit


def test_compute_availability_degraded_trips_on_min_failovers() -> None:
    window = DegradedLLMWindow(total_calls=2, secondary_calls=2)
    assert (
        compute_availability_degraded(
            window=window,
            enter_min_failovers=2,
            enter_ratio=0.99,
            enter_min_calls=100,
        )
        is True
    )


def test_compute_availability_degraded_trips_on_ratio_with_min_calls() -> None:
    window = DegradedLLMWindow(total_calls=8, secondary_calls=3)
    assert (
        compute_availability_degraded(
            window=window,
            enter_min_failovers=10,
            enter_ratio=0.25,
            enter_min_calls=6,
        )
        is True
    )


def test_compute_availability_recovered_requires_min_calls() -> None:
    window = DegradedLLMWindow(total_calls=2, secondary_calls=0)
    assert compute_availability_recovered(window=window, exit_ratio=0.0, exit_min_calls=6) is False


def test_compute_availability_recovered_trips_below_ratio() -> None:
    window = DegradedLLMWindow(total_calls=10, secondary_calls=0)
    assert compute_availability_recovered(window=window, exit_ratio=0.0, exit_min_calls=6) is True
