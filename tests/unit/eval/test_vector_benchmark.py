from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval import vector_benchmark as vector_benchmark_module

pytestmark = pytest.mark.unit


class _FakeConnection:
    def __init__(self) -> None:
        self.execute_calls: list[str] = []
        self.executemany_calls: list[tuple[str, list[tuple[int, str]]]] = []
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    async def execute(self, query: str) -> None:
        self.execute_calls.append(query.strip())

    async def executemany(self, query: str, rows: list[tuple[int, str]]) -> None:
        self.executemany_calls.append((query, rows))

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_calls.append((query, args))
        return [{"id": 2}, {"id": 7}]

    async def close(self) -> None:
        self.closed = True


def test_strategy_metrics_to_dict_rounds_values() -> None:
    metrics = vector_benchmark_module.StrategyMetrics(
        name="hnsw",
        avg_latency_ms=1.23456,
        p95_latency_ms=2.34567,
        recall_at_k=0.9876543,
    )

    assert metrics.to_dict() == {
        "name": "hnsw",
        "avg_latency_ms": 1.2346,
        "p95_latency_ms": 2.3457,
        "recall_at_k": 0.987654,
    }


def test_vector_literal_formats_values() -> None:
    assert vector_benchmark_module._vector_literal([1.0, -0.5, 0.1234567]) == (
        "[1.000000,-0.500000,0.123457]"
    )


def test_normalize_handles_zero_and_non_zero_vectors() -> None:
    assert vector_benchmark_module._normalize([0.0, 0.0]) == [0.0, 0.0]

    normalized = vector_benchmark_module._normalize([3.0, 4.0])

    assert normalized == pytest.approx([0.6, 0.8])


def test_build_clustered_vectors_is_deterministic_and_normalized() -> None:
    vectors = vector_benchmark_module._build_clustered_vectors(
        dataset_size=12,
        dimensions=4,
        seed=123,
    )

    assert len(vectors) == 12
    assert all(len(vector) == 4 for vector in vectors)
    assert vectors == vector_benchmark_module._build_clustered_vectors(
        dataset_size=12,
        dimensions=4,
        seed=123,
    )
    assert all(sum(value * value for value in vector) == pytest.approx(1.0) for vector in vectors)


def test_percentile_handles_empty_and_ordered_values() -> None:
    assert vector_benchmark_module._percentile([], 95.0) == 0.0
    assert vector_benchmark_module._percentile([10.0, 20.0, 30.0], 50.0) == 20.0
    assert vector_benchmark_module._percentile([1.0, 9.0], 99.0) == 9.0


def test_database_url_for_asyncpg_rewrites_driver_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vector_benchmark_module.settings,
        "DATABASE_URL",
        "postgresql+asyncpg://localhost/test_db",
    )

    assert vector_benchmark_module._database_url_for_asyncpg() == "postgresql://localhost/test_db"
    assert (
        vector_benchmark_module._database_url_for_asyncpg("postgresql://override/db")
        == "postgresql://override/db"
    )


def test_recommend_strategy_prefers_fast_high_recall_candidate() -> None:
    metrics = {
        "exact": vector_benchmark_module.StrategyMetrics(
            name="exact",
            avg_latency_ms=4.0,
            p95_latency_ms=5.0,
            recall_at_k=1.0,
        ),
        "ivfflat": vector_benchmark_module.StrategyMetrics(
            name="ivfflat",
            avg_latency_ms=3.9,
            p95_latency_ms=4.8,
            recall_at_k=0.93,
        ),
        "hnsw": vector_benchmark_module.StrategyMetrics(
            name="hnsw",
            avg_latency_ms=2.5,
            p95_latency_ms=3.1,
            recall_at_k=0.98,
        ),
    }

    selected = vector_benchmark_module._recommend_strategy(metrics_by_strategy=metrics)

    assert selected == "hnsw"


def test_recommend_strategy_falls_back_to_exact_when_recall_or_speed_not_met() -> None:
    low_recall = {
        "exact": vector_benchmark_module.StrategyMetrics("exact", 4.0, 5.0, 1.0),
        "ivfflat": vector_benchmark_module.StrategyMetrics("ivfflat", 2.9, 3.5, 0.82),
        "hnsw": vector_benchmark_module.StrategyMetrics("hnsw", 3.2, 3.9, 0.90),
    }
    assert vector_benchmark_module._recommend_strategy(metrics_by_strategy=low_recall) == "exact"

    not_fast_enough = {
        "exact": vector_benchmark_module.StrategyMetrics("exact", 4.0, 5.0, 1.0),
        "ivfflat": vector_benchmark_module.StrategyMetrics("ivfflat", 3.95, 4.5, 0.97),
        "hnsw": vector_benchmark_module.StrategyMetrics("hnsw", 3.9, 4.4, 0.98),
    }
    assert (
        vector_benchmark_module._recommend_strategy(metrics_by_strategy=not_fast_enough) == "exact"
    )


@pytest.mark.asyncio
async def test_prepare_dataset_creates_table_and_loads_rows() -> None:
    conn = _FakeConnection()

    await vector_benchmark_module._prepare_dataset(
        conn,
        vectors=[[1.0, 0.0], [0.0, 1.0]],
        dimensions=2,
    )

    assert conn.execute_calls[0] == "CREATE EXTENSION IF NOT EXISTS vector"
    assert "DROP TABLE IF EXISTS eval_vector_benchmark" in conn.execute_calls[1]
    assert "CREATE TABLE eval_vector_benchmark" in conn.execute_calls[2]
    assert "ANALYZE eval_vector_benchmark" in conn.execute_calls[3]
    assert conn.executemany_calls[0][1] == [
        (0, "[1.000000,0.000000]"),
        (1, "[0.000000,1.000000]"),
    ]


@pytest.mark.asyncio
async def test_drop_strategy_indexes_removes_both_index_types() -> None:
    conn = _FakeConnection()

    await vector_benchmark_module._drop_strategy_indexes(conn)

    assert conn.execute_calls == [
        "DROP INDEX IF EXISTS idx_eval_vector_benchmark_embedding_ivfflat",
        "DROP INDEX IF EXISTS idx_eval_vector_benchmark_embedding_hnsw",
    ]


@pytest.mark.asyncio
async def test_apply_strategy_index_supports_exact_ivfflat_and_hnsw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection()
    drop_calls: list[_FakeConnection] = []

    async def fake_drop(connection: _FakeConnection) -> None:
        drop_calls.append(connection)

    monkeypatch.setattr(vector_benchmark_module, "_drop_strategy_indexes", fake_drop)

    await vector_benchmark_module._apply_strategy_index(conn, strategy="exact")
    await vector_benchmark_module._apply_strategy_index(conn, strategy="ivfflat")
    await vector_benchmark_module._apply_strategy_index(conn, strategy="hnsw")

    assert drop_calls == [conn, conn, conn]
    assert any("ivfflat" in query for query in conn.execute_calls)
    assert any("hnsw" in query for query in conn.execute_calls)
    assert conn.execute_calls.count("ANALYZE eval_vector_benchmark") == 2


@pytest.mark.asyncio
async def test_apply_strategy_index_rejects_unknown_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection()

    async def fake_drop_indexes(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(vector_benchmark_module, "_drop_strategy_indexes", fake_drop_indexes)

    with pytest.raises(ValueError, match="Unsupported strategy 'bogus'"):
        await vector_benchmark_module._apply_strategy_index(conn, strategy="bogus")


@pytest.mark.asyncio
async def test_query_neighbors_returns_ids_and_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConnection()
    times = iter([10.0, 10.012])
    monkeypatch.setattr(vector_benchmark_module.time, "perf_counter", lambda: next(times))

    ids, latency_ms = await vector_benchmark_module._query_neighbors(
        conn,
        query_vector=[0.1, 0.2],
        max_distance=0.3,
        top_k=5,
    )

    assert ids == [2, 7]
    assert latency_ms == pytest.approx(12.0)
    assert conn.fetch_calls[0][1] == ("[0.100000,0.200000]", 0.3, 5)


@pytest.mark.asyncio
async def test_run_strategy_computes_recall_and_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConnection()
    applied: list[str] = []

    async def fake_apply_strategy_index(_conn: _FakeConnection, *, strategy: str) -> None:
        applied.append(strategy)

    responses = iter([([1, 2], 4.0), ([3], 8.0), ([8], 2.0)])

    async def fake_query_neighbors(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(vector_benchmark_module, "_apply_strategy_index", fake_apply_strategy_index)
    monkeypatch.setattr(vector_benchmark_module, "_query_neighbors", fake_query_neighbors)

    metrics = await vector_benchmark_module._run_strategy(
        conn,
        strategy="hnsw",
        query_vectors=[[0.1], [0.2], [0.3]],
        max_distance=0.3,
        top_k=3,
        exact_neighbors=[[1, 2, 3], [], [7, 8]],
    )

    assert applied == ["hnsw"]
    assert metrics.name == "hnsw"
    assert metrics.avg_latency_ms == pytest.approx((4.0 + 8.0 + 2.0) / 3)
    assert metrics.p95_latency_ms == 8.0
    assert metrics.recall_at_k == pytest.approx(((2 / 3) + 1.0 + (1 / 2)) / 3)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"dataset_size": 99}, "dataset_size must be >= 100"),
        ({"query_count": 9}, "query_count must be >= 10"),
        ({"dimensions": 7}, "dimensions must be >= 8"),
        ({"top_k": 0}, "top_k must be >= 1"),
    ],
)
@pytest.mark.asyncio
async def test_run_vector_retrieval_benchmark_validates_inputs(
    kwargs: dict[str, int],
    message: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=message):
        await vector_benchmark_module.run_vector_retrieval_benchmark(
            output_dir=str(tmp_path), **kwargs
        )


@pytest.mark.asyncio
async def test_run_vector_retrieval_benchmark_writes_artifact_and_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    conn = _FakeConnection()

    async def fake_connect(_url: str) -> _FakeConnection:
        return conn

    async def fake_prepare_dataset(*_args, **_kwargs) -> None:
        return None

    exact_responses = iter([([0, 1], 5.0) for _ in range(10)])

    async def fake_query_neighbors(*_args, **_kwargs):
        return next(exact_responses)

    run_calls: list[str] = []

    async def fake_run_strategy(*_args, strategy: str, **_kwargs):
        run_calls.append(strategy)
        if strategy == "ivfflat":
            return vector_benchmark_module.StrategyMetrics("ivfflat", 4.0, 5.0, 0.97)
        return vector_benchmark_module.StrategyMetrics("hnsw", 3.0, 3.5, 0.99)

    async def fake_drop_indexes(_conn: _FakeConnection) -> None:
        return None

    monkeypatch.setattr(vector_benchmark_module.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(vector_benchmark_module, "_prepare_dataset", fake_prepare_dataset)
    monkeypatch.setattr(vector_benchmark_module, "_query_neighbors", fake_query_neighbors)
    monkeypatch.setattr(vector_benchmark_module, "_run_strategy", fake_run_strategy)
    monkeypatch.setattr(vector_benchmark_module, "_drop_strategy_indexes", fake_drop_indexes)
    monkeypatch.setattr(
        vector_benchmark_module.settings,
        "VECTOR_REVALIDATION_CADENCE_DAYS",
        14,
    )
    monkeypatch.setattr(
        vector_benchmark_module.settings,
        "VECTOR_REVALIDATION_DATASET_GROWTH_PCT",
        25,
    )

    artifact_path = await vector_benchmark_module.run_vector_retrieval_benchmark(
        output_dir=str(tmp_path),
        database_url="postgresql://example/db",
        dataset_size=100,
        query_count=10,
        dimensions=8,
        top_k=2,
        similarity_threshold=0.9,
        seed=7,
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / vector_benchmark_module.SUMMARY_FILENAME).read_text("utf-8"))

    assert artifact_path.exists()
    assert payload["dataset"]["size"] == 100
    assert payload["recommendation"]["selected_default"] == "hnsw"
    assert set(payload["strategies"]) == {"exact", "hnsw", "ivfflat"}
    assert summary["latest"]["artifact"] == artifact_path.name
    assert summary["latest"]["selected_default"] == "hnsw"
    assert run_calls == ["ivfflat", "hnsw"]
    assert conn.closed is True


def test_summary_entry_handles_non_mapping_payload_sections(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text("{}", encoding="utf-8")

    entry = vector_benchmark_module._summary_entry(
        payload={
            "generated_at": "2026-03-07T00:00:00+00:00",
            "dataset": [],
            "recommendation": None,
        },
        artifact_path=artifact_path,
    )

    assert entry["generated_at"] == "2026-03-07T00:00:00+00:00"
    assert entry["dataset_size"] is None
    assert entry["selected_default"] is None


def test_update_revalidation_summary_writes_latest_and_history(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-02-16T00:00:00+00:00",
        "dataset": {
            "size": 4000,
            "dimensions": 64,
            "query_count": 200,
            "vector_fingerprint_sha256": "abc123",
        },
        "recommendation": {
            "selected_default": "ivfflat",
            "selection_rule": "rule",
        },
    }
    artifact_path = tmp_path / "vector-benchmark-1.json"
    artifact_path.write_text("{}", encoding="utf-8")

    summary_path = vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=payload,
        artifact_path=artifact_path,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["latest"]["artifact"] == "vector-benchmark-1.json"
    assert summary["latest"]["selected_default"] == "ivfflat"
    assert len(summary["history"]) == 1


def test_update_revalidation_summary_appends_history_entries(tmp_path: Path) -> None:
    base_payload = {
        "generated_at": "2026-02-16T00:00:00+00:00",
        "dataset": {
            "size": 4000,
            "dimensions": 64,
            "query_count": 200,
            "vector_fingerprint_sha256": "abc123",
        },
        "recommendation": {
            "selected_default": "ivfflat",
            "selection_rule": "rule",
        },
    }
    first_artifact = tmp_path / "vector-benchmark-1.json"
    second_artifact = tmp_path / "vector-benchmark-2.json"
    first_artifact.write_text("{}", encoding="utf-8")
    second_artifact.write_text("{}", encoding="utf-8")

    vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=base_payload,
        artifact_path=first_artifact,
    )
    second_payload = {
        **base_payload,
        "generated_at": "2026-02-17T00:00:00+00:00",
        "recommendation": {
            "selected_default": "hnsw",
            "selection_rule": "rule",
        },
    }
    summary_path = vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=second_payload,
        artifact_path=second_artifact,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["latest"]["artifact"] == "vector-benchmark-2.json"
    assert summary["latest"]["selected_default"] == "hnsw"
    assert len(summary["history"]) == 2


def test_update_revalidation_summary_recovers_from_invalid_json_and_deduplicates(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / vector_benchmark_module.SUMMARY_FILENAME
    summary_path.write_text("{not-json", encoding="utf-8")
    payload = {
        "generated_at": "2026-02-16T00:00:00+00:00",
        "dataset": {
            "size": 4000,
            "dimensions": 64,
            "query_count": 200,
            "vector_fingerprint_sha256": "abc123",
        },
        "recommendation": {
            "selected_default": "ivfflat",
            "selection_rule": "rule",
        },
    }
    artifact_path = tmp_path / "vector-benchmark-1.json"
    artifact_path.write_text("{}", encoding="utf-8")

    vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=payload,
        artifact_path=artifact_path,
    )
    summary_path = vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=payload,
        artifact_path=artifact_path,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert len(summary["history"]) == 1


def test_update_revalidation_summary_ignores_non_dict_history_rows(tmp_path: Path) -> None:
    summary_path = tmp_path / vector_benchmark_module.SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps({"history": [{"artifact": "keep.json"}, "skip-me"]}),
        encoding="utf-8",
    )
    payload = {
        "generated_at": "2026-02-16T00:00:00+00:00",
        "dataset": {
            "size": 4000,
            "dimensions": 64,
            "query_count": 200,
            "vector_fingerprint_sha256": "abc123",
        },
        "recommendation": {
            "selected_default": "ivfflat",
            "selection_rule": "rule",
        },
    }
    artifact_path = tmp_path / "vector-benchmark-2.json"
    artifact_path.write_text("{}", encoding="utf-8")

    updated_path = vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=payload,
        artifact_path=artifact_path,
    )

    summary = json.loads(updated_path.read_text(encoding="utf-8"))
    assert [row["artifact"] for row in summary["history"]] == [
        "keep.json",
        "vector-benchmark-2.json",
    ]


def test_update_revalidation_summary_ignores_non_mapping_root(tmp_path: Path) -> None:
    summary_path = tmp_path / vector_benchmark_module.SUMMARY_FILENAME
    summary_path.write_text(json.dumps(["not-a-dict"]), encoding="utf-8")
    payload = {
        "generated_at": "2026-02-16T00:00:00+00:00",
        "dataset": {
            "size": 4000,
            "dimensions": 64,
            "query_count": 200,
            "vector_fingerprint_sha256": "abc123",
        },
        "recommendation": {
            "selected_default": "ivfflat",
            "selection_rule": "rule",
        },
    }
    artifact_path = tmp_path / "vector-benchmark-3.json"
    artifact_path.write_text("{}", encoding="utf-8")

    updated_path = vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=payload,
        artifact_path=artifact_path,
    )

    summary = json.loads(updated_path.read_text(encoding="utf-8"))
    assert summary["latest"]["artifact"] == "vector-benchmark-3.json"
