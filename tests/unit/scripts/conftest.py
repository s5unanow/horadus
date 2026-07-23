from __future__ import annotations

from uuid import uuid4

import pytest

import src.core.trend_seed as trend_seed


@pytest.fixture(autouse=True)
def stub_seed_trend_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep standalone seeder unit fakes focused on orchestration."""

    async def _activate(*, trend, **_kwargs):
        trend.active_state_version_id = uuid4()

    monkeypatch.setattr(trend_seed, "activate_trend_state", _activate)
