from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "0033_add_provisional_event_extraction_state.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_0033_event_provisional_state", MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration module from {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_event_extraction_state_migration_backfills_degraded_rows_as_provisional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    executed: list[str] = []

    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            add_column=lambda *_args, **_kwargs: None,
            create_check_constraint=lambda *_args, **_kwargs: None,
            execute=lambda statement: executed.append(str(statement)),
        ),
    )

    migration.upgrade()

    assert any(
        "extracted_claims -> '_llm_policy' ->> 'degraded_llm'" in statement
        for statement in executed
    )
    assert any("provisional_extraction = jsonb_build_object" in statement for statement in executed)
    assert any("UPDATE event_claims" in statement for statement in executed)
    assert any("SET is_active = false" in statement for statement in executed)
    assert any("SET extraction_status = 'canonical'" in statement for statement in executed)
