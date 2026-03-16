from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType

import pytest

from src.core.trend_engine import prob_to_logodds
from src.storage.models import Trend

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "seed_trends.py"


class _ScalarResult:
    def __init__(self, trend: Trend | None) -> None:
        self._trend = trend

    def scalar_one_or_none(self) -> Trend | None:
        return self._trend


class _FakeSession:
    def __init__(
        self,
        *,
        existing_by_runtime_id: dict[str, Trend] | None = None,
        existing_by_name: dict[str, Trend] | None = None,
    ) -> None:
        self._existing_by_runtime_id = existing_by_runtime_id or {}
        self._existing_by_name = existing_by_name or {}
        self.added: list[Trend] = []
        self.commit_calls = 0

    async def execute(self, statement: object) -> _ScalarResult:
        compiled = statement.compile()
        params = compiled.params
        if "runtime_trend_id_1" in params:
            return _ScalarResult(self._existing_by_runtime_id.get(params["runtime_trend_id_1"]))
        if "name_1" in params:
            return _ScalarResult(self._existing_by_name.get(params["name_1"]))
        msg = f"Unexpected query: {compiled}"
        raise AssertionError(msg)

    def add(self, trend: Trend) -> None:
        self.added.append(trend)

    async def commit(self) -> None:
        self.commit_calls += 1


def _load_seed_trends_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_trends_module", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _session_maker(session: _FakeSession):
    @asynccontextmanager
    async def _manager():
        yield session

    return _manager


def _write_trend_yaml(trends_dir: Path, filename: str, body: str) -> None:
    (trends_dir / filename).write_text(body.strip() + "\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_seed_trends_sets_runtime_trend_id_on_created_trends(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_trends_module = _load_seed_trends_module()
    trends_dir = tmp_path / "trends"
    trends_dir.mkdir()
    _write_trend_yaml(
        trends_dir,
        "signal-watch.yaml",
        """
name: Signal Watch
description: Track the signal watch scenario.
baseline_probability: 0.20
decay_half_life_days: 15
indicators:
  signal:
    weight: 0.04
    direction: escalatory
""",
    )
    session = _FakeSession()
    monkeypatch.setattr(seed_trends_module, "async_session_maker", _session_maker(session))

    result = await seed_trends_module.seed_trends(trends_dir, dry_run=False)

    assert result == 0
    assert session.commit_calls == 1
    assert len(session.added) == 1
    created = session.added[0]
    assert created.runtime_trend_id == "signal-watch"
    assert created.definition["id"] == "signal-watch"


@pytest.mark.asyncio
async def test_seed_trends_updates_renamed_trends_by_runtime_trend_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_trends_module = _load_seed_trends_module()
    trends_dir = tmp_path / "trends"
    trends_dir.mkdir()
    _write_trend_yaml(
        trends_dir,
        "signal-watch.yaml",
        """
id: signal-watch
name: Signal Watch Renamed
description: Updated description
baseline_probability: 0.30
decay_half_life_days: 45
indicators:
  signal:
    weight: 0.07
    direction: de_escalatory
""",
    )
    existing = Trend(
        name="Signal Watch",
        description="Old description",
        runtime_trend_id="signal-watch",
        definition={"id": "signal-watch"},
        baseline_log_odds=prob_to_logodds(0.10),
        current_log_odds=prob_to_logodds(0.25),
        indicators={"signal": {"weight": 0.04, "direction": "escalatory"}},
        decay_half_life_days=30,
        is_active=True,
    )
    session = _FakeSession(existing_by_runtime_id={"signal-watch": existing})
    monkeypatch.setattr(seed_trends_module, "async_session_maker", _session_maker(session))

    result = await seed_trends_module.seed_trends(trends_dir, dry_run=False)

    assert result == 0
    assert session.commit_calls == 1
    assert session.added == []
    assert existing.name == "Signal Watch Renamed"
    assert existing.runtime_trend_id == "signal-watch"
    assert existing.definition["id"] == "signal-watch"
    assert existing.description == "Updated description"
    assert existing.decay_half_life_days == 45
    assert existing.baseline_log_odds == pytest.approx(prob_to_logodds(0.30))
