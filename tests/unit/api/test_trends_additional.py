from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError

import src.api.middleware.auth as auth_middleware_module
import src.api.routes._trend_write_contract as trend_write_contract_module
import src.api.routes._trend_write_persistence as trend_write_persistence_module
import src.api.routes.trends as trends_module
from src.api.routes.trends import (
    _downsample_snapshots,
    _get_evidence_stats,
    _get_top_movers_7d,
    _history_bucket_key,
    _record_definition_version_if_material_change,
    get_trend,
    get_trend_history,
    get_trend_retrospective,
    list_trends,
    load_trends_from_config,
    simulate_trend,
    sync_trends_from_config,
    update_trend,
)
from src.core.trend_engine import prob_to_logodds
from src.storage.models import Trend, TrendEvidence, TrendSnapshot

pytestmark = pytest.mark.unit


def _build_trend(*, trend_id=None, name: str = "Trend A", is_active: bool = True) -> Trend:
    now = datetime.now(tz=UTC)
    return Trend(
        id=trend_id or uuid4(),
        name=name,
        description="description",
        runtime_trend_id=name.lower().replace(" ", "-"),
        definition={"id": name.lower().replace(" ", "-")},
        baseline_log_odds=prob_to_logodds(0.1),
        current_log_odds=prob_to_logodds(0.2),
        indicators={"signal": {"direction": "escalatory", "weight": 0.04, "keywords": ["x"]}},
        decay_half_life_days=30,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _build_request(*, admin_key: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if admin_key is not None:
        headers.append((b"x-admin-api-key", admin_key.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/trends",
            "headers": headers,
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


@pytest.mark.asyncio
async def test_record_definition_version_requires_previous_definition_and_skips_identical_hashes(
    mock_db_session,
) -> None:
    trend = _build_trend()

    with pytest.raises(ValueError, match="previous_definition is required"):
        await _record_definition_version_if_material_change(
            mock_db_session,
            trend=trend,
            previous_definition=None,
            actor="api",
            context="update",
        )

    changed = await _record_definition_version_if_material_change(
        mock_db_session,
        trend=trend,
        previous_definition={"id": "other"},
        actor="api",
        context="update",
    )
    assert changed is True

    mock_db_session.add.reset_mock()
    unchanged = await _record_definition_version_if_material_change(
        mock_db_session,
        trend=trend,
        previous_definition={"id": "trend-a"},
        actor="api",
        context="update",
    )
    assert unchanged is False
    mock_db_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_evidence_stats_and_top_movers_cover_fallback_paths(mock_db_session) -> None:
    naive_recent = (datetime.now(tz=UTC) - timedelta(days=2)).replace(tzinfo=None)
    mock_db_session.execute.return_value = SimpleNamespace(one=lambda: (3, None, naive_recent))

    count, avg_corroboration, days_since_last = await _get_evidence_stats(
        mock_db_session,
        trend_id=uuid4(),
    )

    assert count == 3
    assert avg_corroboration == pytest.approx(0.5)
    assert days_since_last >= 0

    mock_db_session.execute.return_value = SimpleNamespace(one=lambda: (0, 0.6, None))
    count, avg_corroboration, days_since_last = await _get_evidence_stats(
        mock_db_session,
        trend_id=uuid4(),
    )
    assert count == 0
    assert avg_corroboration == pytest.approx(0.6)
    assert days_since_last == 30

    records = [
        TrendEvidence(
            id=uuid4(),
            trend_id=uuid4(),
            event_id=uuid4(),
            signal_type="military_movement",
            delta_log_odds=0.1,
            reasoning=None,
        ),
        TrendEvidence(
            id=uuid4(),
            trend_id=uuid4(),
            event_id=uuid4(),
            signal_type="sanctions",
            delta_log_odds=0.05,
            reasoning=None,
        ),
    ]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: records)

    movers = await _get_top_movers_7d(mock_db_session, trend_id=uuid4(), limit=2)
    assert movers == ["military_movement", "sanctions"]

    records[0].reasoning = " Trim me "
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: records)
    assert await _get_top_movers_7d(mock_db_session, trend_id=uuid4(), limit=2) == ["Trim me"]


def test_history_helpers_cover_weekly_bucket_and_downsampling() -> None:
    first = TrendSnapshot(
        trend_id=uuid4(),
        timestamp=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
        log_odds=0.1,
    )
    second = TrendSnapshot(
        trend_id=uuid4(),
        timestamp=datetime(2026, 2, 3, 10, 0, tzinfo=UTC),
        log_odds=0.2,
    )
    third = TrendSnapshot(
        trend_id=uuid4(),
        timestamp=datetime(2026, 2, 10, 10, 0, tzinfo=UTC),
        log_odds=0.3,
    )

    assert _history_bucket_key(first.timestamp, "weekly") == (2026, 6)
    assert _history_bucket_key(first.timestamp, "hourly") == (2026, 2, 2, 10)
    assert _downsample_snapshots([first, second, third], interval="weekly") == [second, third]


@pytest.mark.asyncio
async def test_load_trends_sync_and_list_trends_cover_wrapper_paths(
    tmp_path,
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = await load_trends_from_config(mock_db_session, config_dir=str(tmp_path / "missing"))
    assert missing.errors == [f"Config directory not found: {tmp_path / 'missing'}"]

    broken = tmp_path / "broken.yaml"
    broken.write_text("- not-a-mapping\n", encoding="utf-8")
    invalid = await load_trends_from_config(mock_db_session, config_dir=str(tmp_path))
    assert invalid.loaded_files == 1
    assert len(invalid.errors) == 1

    trend = _build_trend(is_active=False)
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [trend])
    monkeypatch.setattr(trends_module, "_get_evidence_stats", AsyncMock(return_value=(0, 0.5, 30)))
    monkeypatch.setattr(trends_module, "_get_top_movers_7d", AsyncMock(return_value=[]))
    monkeypatch.setattr(auth_middleware_module.settings, "API_ADMIN_KEY", "admin-secret")
    called: list[str] = []

    async def fake_sync(*, session, config_dir: str = "config/trends"):
        assert session is mock_db_session
        called.append(config_dir)
        return SimpleNamespace(loaded_files=0, created=0, updated=0, errors=[])

    monkeypatch.setattr(trends_module, "load_trends_from_config", fake_sync)

    results = await list_trends(
        request=_build_request(admin_key="admin-secret"),
        active_only=False,
        sync_from_config=True,
        session=mock_db_session,
    )

    synced = await sync_trends_from_config(config_dir="custom/trends", session=mock_db_session)

    assert len(results) == 1
    assert results[0].id == trend.id
    assert called == ["config/trends", "custom/trends"]
    assert synced.loaded_files == 0


@pytest.mark.asyncio
async def test_load_trends_from_config_upserts_by_runtime_trend_id(
    tmp_path,
    mock_db_session,
) -> None:
    config_file = tmp_path / "renamed.yaml"
    config_file.write_text(
        """
id: shared-runtime-id
name: Renamed Trend
baseline_probability: 0.20
decay_half_life_days: 15
indicators:
  signal:
    weight: 0.04
    direction: escalatory
""".strip()
        + "\n",
        encoding="utf-8",
    )
    existing = _build_trend(name="Old Name")
    existing.runtime_trend_id = "shared-runtime-id"
    mock_db_session.scalar.side_effect = [existing, None]

    result = await load_trends_from_config(mock_db_session, config_dir=str(tmp_path))

    assert result.created == 0
    assert result.updated == 1
    assert existing.name == "Renamed Trend"
    assert existing.runtime_trend_id == "shared-runtime-id"


@pytest.mark.asyncio
async def test_load_trends_from_config_rejects_conflicting_name_and_runtime_rows(
    tmp_path,
    mock_db_session,
) -> None:
    config_file = tmp_path / "conflict.yaml"
    config_file.write_text(
        """
id: shared-runtime-id
name: Renamed Trend
baseline_probability: 0.20
decay_half_life_days: 15
indicators:
  signal:
    weight: 0.04
    direction: escalatory
""".strip()
        + "\n",
        encoding="utf-8",
    )
    existing_by_runtime = _build_trend(name="Runtime Owner")
    existing_by_runtime.runtime_trend_id = "shared-runtime-id"
    existing_by_name = _build_trend(name="Renamed Trend")
    existing_by_name.runtime_trend_id = "other-runtime-id"
    mock_db_session.scalar.side_effect = [existing_by_runtime, existing_by_name]

    result = await load_trends_from_config(mock_db_session, config_dir=str(tmp_path))

    assert result.created == 0
    assert result.updated == 0
    assert result.errors == [
        "conflict.yaml: Config sync found conflicting trend identity rows for name 'Renamed Trend' and runtime id 'shared-runtime-id'"
    ]


def test_trend_write_helper_edges_cover_blank_runtime_id_and_integrity_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        trend_write_contract_module,
        "build_trend_config",
        lambda **_: SimpleNamespace(
            id=None,
            baseline_probability=0.2,
            model_dump=lambda **__: {},
            indicators={},
        ),
    )

    with pytest.raises(ValueError, match="cannot be blank"):
        trend_write_contract_module.build_validated_trend_write_payload(
            name="Trend",
            description=None,
            baseline_probability=0.2,
            decay_half_life_days=30,
            indicators={},
            definition={},
        )

    exc = IntegrityError("insert", {}, Exception("runtime_trend_id"))
    assert (
        trend_write_persistence_module.is_unique_integrity_error(
            exc,
            marker="runtime_trend_id",
        )
        is True
    )


@pytest.mark.asyncio
async def test_load_trends_from_config_updates_existing_trend(mock_db_session, tmp_path) -> None:
    config_file = tmp_path / "trend.yaml"
    config_file.write_text(
        """
id: eu-russia
name: EU Russia
description: Updated description
baseline_probability: 0.25
decay_half_life_days: 20
indicators:
  military_movement:
    weight: 0.04
    direction: escalatory
""".strip(),
        encoding="utf-8",
    )
    existing = _build_trend(name="EU Russia")
    mock_db_session.scalar.return_value = existing

    result = await load_trends_from_config(mock_db_session, config_dir=str(tmp_path))

    assert result.updated == 1
    assert existing.description == "Updated description"
    assert existing.decay_half_life_days == 20


@pytest.mark.asyncio
async def test_trend_endpoints_cover_success_filter_and_default_window_paths(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend = _build_trend(name="Trend One")
    mock_db_session.get.return_value = trend
    monkeypatch.setattr(trends_module, "_get_evidence_stats", AsyncMock(return_value=(1, 0.5, 0)))
    monkeypatch.setattr(trends_module, "_get_top_movers_7d", AsyncMock(return_value=["signal"]))
    assert (await get_trend(trend_id=trend.id, session=mock_db_session)).id == trend.id

    snapshots = [
        TrendSnapshot(
            trend_id=trend.id,
            timestamp=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
            log_odds=prob_to_logodds(0.2),
        ),
        TrendSnapshot(
            trend_id=trend.id,
            timestamp=datetime(2026, 2, 4, 10, 0, tzinfo=UTC),
            log_odds=prob_to_logodds(0.25),
        ),
    ]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: snapshots)

    history = await get_trend_history(
        trend_id=trend.id,
        start_at=snapshots[0].timestamp,
        end_at=snapshots[1].timestamp,
        interval="weekly",
        session=mock_db_session,
    )
    query_text = str(mock_db_session.scalars.await_args.args[0]).lower()
    assert "trend_snapshots.timestamp >=" in query_text
    assert "trend_snapshots.timestamp <=" in query_text
    assert len(history) == 1

    class FakeAnalyzer:
        def __init__(self, session) -> None:
            assert session is mock_db_session

        async def analyze(self, *, trend, start_date, end_date):
            assert start_date.tzinfo is UTC
            assert end_date.tzinfo is UTC
            assert (end_date - start_date) <= timedelta(days=31)
            return {
                "trend_id": trend.id,
                "trend_name": trend.name,
                "period_start": start_date,
                "period_end": end_date,
                "pivotal_events": [],
                "category_breakdown": {},
                "predictive_signals": [],
                "accuracy_assessment": {},
                "narrative": "none",
                "grounding_status": "grounded",
                "grounding_violation_count": 0,
                "grounding_references": None,
            }

    monkeypatch.setattr(trends_module, "RetrospectiveAnalyzer", FakeAnalyzer)

    retrospective = await get_trend_retrospective(
        trend_id=trend.id,
        start_date=datetime(2026, 2, 1, 9, 0, tzinfo=UTC).replace(tzinfo=None),
        end_date=datetime(2026, 2, 10, 9, 0, tzinfo=UTC).replace(tzinfo=None),
        session=mock_db_session,
    )
    assert retrospective.trend_id == trend.id

    default_window = await get_trend_retrospective(
        trend_id=trend.id,
        session=mock_db_session,
    )
    assert default_window.trend_id == trend.id


@pytest.mark.asyncio
async def test_simulate_remove_event_and_update_trend_duplicate_name_paths(
    mock_db_session,
) -> None:
    trend = _build_trend(name="Current Trend")
    mock_db_session.get.return_value = trend
    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [
            TrendEvidence(
                id=uuid4(),
                trend_id=trend.id,
                event_id=uuid4(),
                signal_type="military_movement",
                delta_log_odds=0.2,
            )
        ]
    )

    simulation = await simulate_trend(
        trend_id=trend.id,
        payload=trends_module.RemoveEventImpactSimulationRequest(
            mode="remove_event_impact",
            event_id=uuid4(),
            signal_type="military_movement",
        ),
        session=mock_db_session,
    )
    assert simulation.factor_breakdown["signal_type"] == "military_movement"

    mock_db_session.scalar.return_value = uuid4()
    with pytest.raises(HTTPException, match="already exists") as exc:
        await update_trend(
            trend_id=trend.id,
            trend=trends_module.TrendUpdate(name="Duplicate"),
            session=mock_db_session,
        )

    assert exc.value.status_code == 409
