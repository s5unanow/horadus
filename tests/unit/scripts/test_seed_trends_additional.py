from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from src.storage.models import Trend

pytestmark = pytest.mark.unit

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "seed_trends.py"


def _load_module() -> ModuleType:
    module_name = f"seed_trends_additional_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


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
        raise AssertionError(f"Unexpected query: {compiled}")

    def add(self, trend: Trend) -> None:
        self.added.append(trend)

    async def commit(self) -> None:
        self.commit_calls += 1


def _session_maker(session: _FakeSession):
    @asynccontextmanager
    async def _manager():
        yield session

    return _manager


def _write_yaml(path: Path, body: str) -> None:
    path.write_text(body.strip() + "\n", encoding="utf-8")


def test_seed_trends_helper_validation_errors(tmp_path: Path) -> None:
    module = _load_module()
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("- item\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        module._load_yaml(invalid_yaml)

    with pytest.raises(ValueError, match="Missing required 'name'"):
        module._trend_name({}, invalid_yaml)

    with pytest.raises(ValueError, match="Indicator key must be a non-empty string"):
        module._validate_indicators({"": {}}, invalid_yaml)
    with pytest.raises(ValueError, match="must be a mapping"):
        module._validate_indicators({"signal": []}, invalid_yaml)
    with pytest.raises(ValueError, match="missing required 'weight'"):
        module._validate_indicators({"signal": {}}, invalid_yaml)
    with pytest.raises(ValueError, match="non-numeric weight"):
        module._validate_indicators({"signal": {"weight": "x"}}, invalid_yaml)
    with pytest.raises(ValueError, match="weight must be >= 0"):
        module._validate_indicators(
            {"signal": {"weight": -1, "direction": "escalatory"}}, invalid_yaml
        )
    with pytest.raises(ValueError, match="invalid direction"):
        module._validate_indicators(
            {"signal": {"weight": 1, "direction": "sideways"}}, invalid_yaml
        )


@pytest.mark.asyncio
async def test_get_existing_trend_rejects_conflicting_identity() -> None:
    module = _load_module()
    existing_runtime = Trend(name="A", runtime_trend_id="same", definition={"id": "same"})
    existing_runtime.id = "runtime"
    existing_name = Trend(name="B", runtime_trend_id="other", definition={"id": "other"})
    existing_name.id = "name"
    session = _FakeSession(
        existing_by_runtime_id={"same": existing_runtime},
        existing_by_name={"Renamed": existing_name},
    )

    with pytest.raises(ValueError, match="Seeded trend identity conflict"):
        await module._get_existing_trend(
            session,
            runtime_trend_id="same",
            trend_name="Renamed",
        )


@pytest.mark.asyncio
async def test_seed_trends_additional_paths_and_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    with pytest.raises(FileNotFoundError, match="Trends path not found"):
        await module.seed_trends(tmp_path / "missing", dry_run=False)

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="No YAML files found"):
        await module.seed_trends(empty_dir, dry_run=False)

    trends_dir = tmp_path / "trends"
    trends_dir.mkdir()
    _write_yaml(
        trends_dir / "signal.yaml",
        """
name: Signal
baseline_probability: 0.25
indicators:
  signal:
    weight: 0.1
    direction: escalatory
""",
    )
    session = _FakeSession()
    monkeypatch.setattr(module, "async_session_maker", _session_maker(session))
    assert await module.seed_trends(trends_dir, dry_run=True) == 0
    assert session.added == []
    assert session.commit_calls == 0

    _write_yaml(
        trends_dir / "invalid-indicators.yaml",
        """
name: Broken
indicators: nope
""",
    )
    with pytest.raises(ValueError, match="'indicators' must be a mapping"):
        await module.seed_trends(trends_dir, dry_run=True)
    (trends_dir / "invalid-indicators.yaml").unlink()

    existing = Trend(name="Signal", runtime_trend_id="signal", definition={"id": "signal"})
    existing.id = "signal"
    update_session = _FakeSession(existing_by_runtime_id={"signal": existing})
    monkeypatch.setattr(module, "async_session_maker", _session_maker(update_session))
    assert await module.seed_trends(trends_dir, dry_run=True) == 0
    assert update_session.commit_calls == 0
    assert "created=0 updated=1 dry_run=True" in capsys.readouterr().out

    async def _fake_seed(path: Path, *, dry_run: bool) -> int:
        assert path == Path("config/trends")
        assert dry_run is True
        return 7

    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(path="config/trends", dry_run=True),
    )
    monkeypatch.setattr(module, "seed_trends", _fake_seed)
    monkeypatch.setattr(
        module.asyncio,
        "run",
        lambda coro: (coro.close(), 7)[1] if asyncio.iscoroutine(coro) else 7,
    )
    assert module.main() == 7
