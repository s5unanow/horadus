from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "0021_add_runtime_trend_id_uniqueness.py"


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0021_runtime_trend_id", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_trend_id_migration_rejects_overlength_backfill_ids() -> None:
    migration = _load_migration_module()

    with pytest.raises(RuntimeError, match="longer than 255 characters"):
        migration._resolve_runtime_trend_id(name="Trend", definition={"id": "x" * 256})
