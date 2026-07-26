from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from src.storage.models import Trend

pytestmark = pytest.mark.unit

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "alembic" / "versions" / "0040_add_trend_decay_clock.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_0040_trend_decay_clock", MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration module from {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trend_decay_clock_migration_backfills_before_not_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    operations: list[tuple[str, object]] = []

    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            add_column=lambda table, column: operations.append(("add", (table, column))),
            execute=lambda statement: operations.append(("execute", str(statement))),
            alter_column=lambda *args, **kwargs: operations.append(("alter", (args, kwargs))),
        ),
    )

    migration.upgrade()

    assert [kind for kind, _payload in operations] == ["add", "execute", "alter"]
    assert "SET last_decayed_at = updated_at" in str(operations[1][1])
    alter_args, alter_kwargs = operations[2][1]
    assert alter_args == ("trends", "last_decayed_at")
    assert alter_kwargs["nullable"] is False
    assert str(alter_kwargs["server_default"]) == "now()"


def test_trend_decay_clock_present_in_model_metadata() -> None:
    column = Trend.__table__.c.last_decayed_at

    assert column.nullable is False
    assert column.server_default is not None
