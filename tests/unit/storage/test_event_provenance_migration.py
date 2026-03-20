from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "0027_add_event_provenance_corroboration.py"


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0027_event_provenance", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _SelectResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.updates: list[dict[str, object]] = []

    def execute(self, statement, params=None):  # type: ignore[no-untyped-def]
        sql = str(statement)
        if "FROM events AS e" in sql:
            return _SelectResult(self._rows)
        if "UPDATE events" in sql:
            assert isinstance(params, dict)
            self.updates.append(params)
            return None
        raise AssertionError(f"Unexpected SQL in test: {sql}")


def test_event_provenance_migration_backfills_historical_events() -> None:
    migration = _load_migration_module()
    first_event_id = uuid4()
    second_event_id = uuid4()
    connection = _FakeConnection(
        [
            {
                "event_id": first_event_id,
                "source_count": 3,
                "unique_source_count": 3,
                "source_id": uuid4(),
                "source_name": "Regional Outlet A",
                "source_url": "https://a.example.test",
                "source_tier": "major",
                "reporting_type": "secondary",
                "item_url": "https://a.example.test/story",
                "title": "Forces moved near the eastern border overnight",
                "author": "Reuters staff",
                "content_hash": "a" * 64,
            },
            {
                "event_id": first_event_id,
                "source_count": 3,
                "unique_source_count": 3,
                "source_id": uuid4(),
                "source_name": "Regional Outlet B",
                "source_url": "https://b.example.test",
                "source_tier": "major",
                "reporting_type": "secondary",
                "item_url": "https://b.example.test/story",
                "title": "Forces moved near the eastern border overnight",
                "author": "Reuters",
                "content_hash": "a" * 64,
            },
            {
                "event_id": first_event_id,
                "source_count": 3,
                "unique_source_count": 3,
                "source_id": uuid4(),
                "source_name": "Independent Paper",
                "source_url": "https://independent.example.test",
                "source_tier": "major",
                "reporting_type": "secondary",
                "item_url": "https://independent.example.test/story",
                "title": "Local reporting confirms troop movement near the border",
                "author": "Staff reporter",
                "content_hash": "b" * 64,
            },
            {
                "event_id": second_event_id,
                "source_count": 1,
                "unique_source_count": 1,
                "source_id": None,
                "source_name": None,
                "source_url": None,
                "source_tier": None,
                "reporting_type": None,
                "item_url": None,
                "title": None,
                "author": None,
                "content_hash": None,
            },
        ]
    )

    migration._backfill_event_provenance(connection)

    assert len(connection.updates) == 2
    updates_by_event = {update["event_id"]: update for update in connection.updates}

    first_event_update = updates_by_event[first_event_id]
    first_event_summary = json.loads(first_event_update["provenance_summary"])
    assert first_event_update["corroboration_mode"] == "provenance_aware"
    assert first_event_update["independent_evidence_count"] == 2
    assert first_event_summary["independent_evidence_count"] == 2
    assert first_event_summary["method"] == "provenance_aware"

    second_event_update = updates_by_event[second_event_id]
    second_event_summary = json.loads(second_event_update["provenance_summary"])
    assert second_event_update["corroboration_mode"] == "fallback"
    assert second_event_update["independent_evidence_count"] == 1
    assert second_event_summary["reason"] == "migration_backfill_no_event_items"
