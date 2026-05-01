from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.processing.tier2_runtime import parse_tier2_datetime

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("2024", datetime(2024, 1, 1, tzinfo=UTC)),
        ("2024-07", datetime(2024, 7, 1, tzinfo=UTC)),
        ("2024-03 to early 2025", datetime(2024, 3, 1, tzinfo=UTC)),
        ("as of 2024-03 to early 2025", datetime(2024, 3, 1, tzinfo=UTC)),
        ("2025/26", datetime(2025, 1, 1, tzinfo=UTC)),
        ("2025-04-01/2025-04-02", datetime(2025, 4, 1, tzinfo=UTC)),
        ("2024-02/2024-07", datetime(2024, 2, 1, tzinfo=UTC)),
        ("2025-2026", datetime(2025, 1, 1, tzinfo=UTC)),
        ("late 2025", datetime(2025, 10, 1, tzinfo=UTC)),
        ("mid-2024", datetime(2024, 6, 1, tzinfo=UTC)),
        ("since 2023-10", datetime(2023, 10, 1, tzinfo=UTC)),
        ("2026-02-07T12:00:00Z", datetime(2026, 2, 7, 12, 0, tzinfo=UTC)),
    ],
)
def test_parse_tier2_datetime_accepts_partial_and_range_values(
    raw_value: str,
    expected: datetime,
) -> None:
    assert parse_tier2_datetime(raw_value) == expected
