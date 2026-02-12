"""
Vector retrieval benchmark utilities (exact vs IVFFlat vs HNSW).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]

from src.core.config import settings
from src.processing.vector_similarity import max_distance_for_similarity

BENCHMARK_TABLE_NAME = "eval_vector_benchmark"


@dataclass(slots=True, frozen=True)
class StrategyMetrics:
    """Latency/recall metrics for a retrieval strategy."""

    name: str
    avg_latency_ms: float
    p95_latency_ms: float
    recall_at_k: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "name": self.name,
            "avg_latency_ms": round(self.avg_latency_ms, 4),
            "p95_latency_ms": round(self.p95_latency_ms, 4),
            "recall_at_k": round(self.recall_at_k, 6),
        }


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"


def _normalize(vector: list[float]) -> list[float]:
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def _build_clustered_vectors(
    *,
    dataset_size: int,
    dimensions: int,
    seed: int,
) -> list[list[float]]:
    rng = random.Random(seed)  # nosec B311
    cluster_count = max(8, min(32, dataset_size // 80 if dataset_size >= 80 else 8))
    centers = [
        _normalize([rng.uniform(-1.0, 1.0) for _ in range(dimensions)])
        for _ in range(cluster_count)
    ]

    vectors: list[list[float]] = []
    for _ in range(dataset_size):
        center = centers[rng.randrange(len(centers))]
        noisy = [center[index] + rng.gauss(0.0, 0.08) for index in range(dimensions)]
        vectors.append(_normalize(noisy))
    return vectors


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round((percentile / 100.0) * (len(ordered) - 1)))
    return ordered[idx]


def _database_url_for_asyncpg(database_url: str | None = None) -> str:
    url = database_url or settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def _prepare_dataset(
    conn: asyncpg.Connection,
    *,
    vectors: list[list[float]],
    dimensions: int,
) -> None:
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await conn.execute("DROP TABLE IF EXISTS eval_vector_benchmark")
    await conn.execute(
        f"""
        CREATE TABLE {BENCHMARK_TABLE_NAME} (
            id BIGINT PRIMARY KEY,
            embedding vector({dimensions}) NOT NULL
        )
        """
    )
    rows = [(index, _vector_literal(vector)) for index, vector in enumerate(vectors)]
    await conn.executemany(
        "INSERT INTO eval_vector_benchmark (id, embedding) VALUES ($1, $2::vector)",
        rows,
    )
    await conn.execute("ANALYZE eval_vector_benchmark")


async def _drop_strategy_indexes(conn: asyncpg.Connection) -> None:
    await conn.execute("DROP INDEX IF EXISTS idx_eval_vector_benchmark_embedding_ivfflat")
    await conn.execute("DROP INDEX IF EXISTS idx_eval_vector_benchmark_embedding_hnsw")


async def _apply_strategy_index(
    conn: asyncpg.Connection,
    *,
    strategy: str,
) -> None:
    await _drop_strategy_indexes(conn)
    if strategy == "exact":
        return

    if strategy == "ivfflat":
        await conn.execute(
            """
            CREATE INDEX idx_eval_vector_benchmark_embedding_ivfflat
            ON eval_vector_benchmark
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
        )
        await conn.execute("SET ivfflat.probes = 10")
    elif strategy == "hnsw":
        await conn.execute(
            """
            CREATE INDEX idx_eval_vector_benchmark_embedding_hnsw
            ON eval_vector_benchmark
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """
        )
        await conn.execute("SET hnsw.ef_search = 64")
    else:
        msg = f"Unsupported strategy '{strategy}'"
        raise ValueError(msg)

    await conn.execute("ANALYZE eval_vector_benchmark")


async def _query_neighbors(
    conn: asyncpg.Connection,
    *,
    query_vector: list[float],
    max_distance: float,
    top_k: int,
) -> tuple[list[int], float]:
    started = time.perf_counter()
    rows = await conn.fetch(
        """
        SELECT id
        FROM eval_vector_benchmark
        WHERE embedding <=> $1::vector <= $2
        ORDER BY embedding <=> $1::vector ASC
        LIMIT $3
        """,
        _vector_literal(query_vector),
        max_distance,
        top_k,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return ([int(row["id"]) for row in rows], elapsed_ms)


async def _run_strategy(
    conn: asyncpg.Connection,
    *,
    strategy: str,
    query_vectors: list[list[float]],
    max_distance: float,
    top_k: int,
    exact_neighbors: list[list[int]],
) -> StrategyMetrics:
    await _apply_strategy_index(conn, strategy=strategy)

    latencies_ms: list[float] = []
    recalls: list[float] = []
    for index, query_vector in enumerate(query_vectors):
        predicted, latency_ms = await _query_neighbors(
            conn,
            query_vector=query_vector,
            max_distance=max_distance,
            top_k=top_k,
        )
        latencies_ms.append(latency_ms)

        baseline = exact_neighbors[index]
        if not baseline:
            recalls.append(1.0)
            continue
        overlap = len(set(predicted).intersection(set(baseline)))
        recalls.append(overlap / len(baseline))

    avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
    p95_latency = _percentile(latencies_ms, 95.0)
    avg_recall = sum(recalls) / len(recalls) if recalls else 0.0
    return StrategyMetrics(
        name=strategy,
        avg_latency_ms=avg_latency,
        p95_latency_ms=p95_latency,
        recall_at_k=avg_recall,
    )


def _recommend_strategy(
    *,
    metrics_by_strategy: dict[str, StrategyMetrics],
    min_recall_at_k: float = 0.95,
) -> str:
    exact = metrics_by_strategy["exact"]
    candidates = [
        metrics
        for strategy, metrics in metrics_by_strategy.items()
        if strategy != "exact" and metrics.recall_at_k >= min_recall_at_k
    ]
    if not candidates:
        return "exact"

    fastest = min(candidates, key=lambda candidate: candidate.avg_latency_ms)
    if fastest.avg_latency_ms <= exact.avg_latency_ms * 0.95:
        return fastest.name
    return "exact"


async def run_vector_retrieval_benchmark(
    *,
    output_dir: str,
    database_url: str | None = None,
    dataset_size: int = 4000,
    query_count: int = 200,
    dimensions: int = 64,
    top_k: int = 10,
    similarity_threshold: float = 0.88,
    seed: int = 42,
) -> Path:
    """
    Run deterministic vector retrieval benchmark and write JSON artifact.
    """
    if dataset_size < 100:
        msg = "dataset_size must be >= 100"
        raise ValueError(msg)
    if query_count < 10:
        msg = "query_count must be >= 10"
        raise ValueError(msg)
    if dimensions < 8:
        msg = "dimensions must be >= 8"
        raise ValueError(msg)
    if top_k < 1:
        msg = "top_k must be >= 1"
        raise ValueError(msg)

    max_distance = max_distance_for_similarity(similarity_threshold)
    vectors = _build_clustered_vectors(
        dataset_size=dataset_size,
        dimensions=dimensions,
        seed=seed,
    )
    vector_literals = [_vector_literal(vector) for vector in vectors]
    vector_fingerprint = hashlib.sha256("\n".join(vector_literals).encode("utf-8")).hexdigest()
    rng = random.Random(seed + 101)  # nosec B311
    query_vectors = [vectors[rng.randrange(len(vectors))] for _ in range(query_count)]

    conn = await asyncpg.connect(_database_url_for_asyncpg(database_url))
    try:
        await _prepare_dataset(conn, vectors=vectors, dimensions=dimensions)

        exact_neighbors: list[list[int]] = []
        exact_latencies: list[float] = []
        for query_vector in query_vectors:
            ids, latency_ms = await _query_neighbors(
                conn,
                query_vector=query_vector,
                max_distance=max_distance,
                top_k=top_k,
            )
            exact_neighbors.append(ids)
            exact_latencies.append(latency_ms)

        metrics_by_strategy: dict[str, StrategyMetrics] = {
            "exact": StrategyMetrics(
                name="exact",
                avg_latency_ms=(sum(exact_latencies) / len(exact_latencies))
                if exact_latencies
                else 0.0,
                p95_latency_ms=_percentile(exact_latencies, 95.0),
                recall_at_k=1.0,
            )
        }
        for strategy in ("ivfflat", "hnsw"):
            metrics_by_strategy[strategy] = await _run_strategy(
                conn,
                strategy=strategy,
                query_vectors=query_vectors,
                max_distance=max_distance,
                top_k=top_k,
                exact_neighbors=exact_neighbors,
            )
        recommendation = _recommend_strategy(metrics_by_strategy=metrics_by_strategy)
    finally:
        try:
            await _drop_strategy_indexes(conn)
            await conn.execute("DROP TABLE IF EXISTS eval_vector_benchmark")
        finally:
            await conn.close()

    generated_at = datetime.now(tz=UTC)
    payload = {
        "generated_at": generated_at.isoformat(),
        "dataset": {
            "size": dataset_size,
            "dimensions": dimensions,
            "query_count": query_count,
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
            "seed": seed,
            "vector_fingerprint_sha256": vector_fingerprint,
        },
        "strategies": {
            strategy: metrics.to_dict()
            for strategy, metrics in sorted(metrics_by_strategy.items(), key=lambda item: item[0])
        },
        "recommendation": {
            "selected_default": recommendation,
            "selection_rule": "fastest strategy with recall_at_k >= 0.95 and >=5% lower avg latency than exact",
        },
    }

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    payload_canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload_canonical.encode("utf-8")).hexdigest()[:8]
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = output_path / f"vector-benchmark-{timestamp}-{digest}.json"
    artifact_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return artifact_path
