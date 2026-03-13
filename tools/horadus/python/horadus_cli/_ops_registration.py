from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any


def add_ops_leaf_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default=argparse.SUPPRESS,
        help="Output format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Validate and describe the command without making changes.",
    )


def register_ops_commands(
    subparsers: Any,
    *,
    add_leaf_options: Callable[[argparse.ArgumentParser], None],
    runtime_result: Callable[[str, Any], Any],
    handle_agent_smoke: Callable[[Any], Any],
    default_embedding_model: Callable[[], str],
    default_agent_base_url: Callable[[], str],
    default_api_key: Callable[[], str],
    benchmark_config_choices: tuple[str, ...],
    replay_config_choices: tuple[str, ...],
) -> None:
    trends_parser = subparsers.add_parser("trends")
    trends_subparsers = trends_parser.add_subparsers(dest="trends_command")
    trends_status_parser = trends_subparsers.add_parser(
        "status",
        help="Show trend probabilities, weekly movement, and top movers.",
    )
    add_leaf_options(trends_status_parser)
    trends_status_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum number of active trends to display."
    )
    trends_status_parser.set_defaults(handler=lambda args: runtime_result("trends-status", args))

    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_command")
    dashboard_export_parser = dashboard_subparsers.add_parser(
        "export",
        help="Export calibration dashboard to static JSON/HTML artifacts.",
    )
    add_leaf_options(dashboard_export_parser)
    dashboard_export_parser.add_argument(
        "--output-dir",
        default="artifacts/dashboard",
        help="Directory where dashboard artifacts are written.",
    )
    dashboard_export_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of trend movement rows included in export.",
    )
    dashboard_export_parser.set_defaults(
        handler=lambda args: runtime_result("dashboard-export", args)
    )

    eval_parser = subparsers.add_parser("eval")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command")

    eval_benchmark_parser = eval_subparsers.add_parser(
        "benchmark",
        help="Run Tier-1/Tier-2 benchmark against ai/eval gold set.",
    )
    add_leaf_options(eval_benchmark_parser)
    eval_benchmark_parser.add_argument(
        "--gold-set", default="ai/eval/gold_set.jsonl", help="Path to gold-set JSONL file."
    )
    eval_benchmark_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for benchmark result artifacts."
    )
    eval_benchmark_parser.add_argument(
        "--trend-config-dir",
        default="config/trends",
        help="Directory containing trend config YAML files used for benchmark taxonomy.",
    )
    eval_benchmark_parser.add_argument(
        "--max-items",
        type=int,
        default=50,
        help="Maximum gold-set items to evaluate (use 200 for full run).",
    )
    eval_benchmark_parser.add_argument(
        "--config",
        action="append",
        choices=benchmark_config_choices,
        help=(
            "Benchmark config name (repeat to run multiple). Defaults to the baseline "
            "set (baseline, alternative); GPT-5 candidates require explicit "
            "--config selection."
        ),
    )
    eval_benchmark_parser.add_argument(
        "--require-human-verified",
        action="store_true",
        help="Evaluate only rows where label_verification=human_verified.",
    )
    eval_benchmark_parser.add_argument(
        "--dispatch-mode",
        choices=["realtime", "batch"],
        default="realtime",
        help="Offline dispatch profile.",
    )
    eval_benchmark_parser.add_argument(
        "--request-priority",
        choices=["realtime", "flex"],
        default="realtime",
        help="Provider priority hint.",
    )
    eval_benchmark_parser.set_defaults(handler=lambda args: runtime_result("eval-benchmark", args))

    eval_audit_parser = eval_subparsers.add_parser(
        "audit", help="Audit gold-set quality (provenance, diversity, and label coverage)."
    )
    add_leaf_options(eval_audit_parser)
    eval_audit_parser.add_argument(
        "--gold-set", default="ai/eval/gold_set.jsonl", help="Path to gold-set JSONL file."
    )
    eval_audit_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for audit result artifacts."
    )
    eval_audit_parser.add_argument(
        "--max-items", type=int, default=200, help="Maximum dataset rows to audit."
    )
    eval_audit_parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return non-zero exit code if audit warnings are present.",
    )
    eval_audit_parser.set_defaults(handler=lambda args: runtime_result("eval-audit", args))

    eval_taxonomy_parser = eval_subparsers.add_parser(
        "validate-taxonomy",
        help="Validate trend config taxonomy contract against the evaluation gold set.",
    )
    add_leaf_options(eval_taxonomy_parser)
    eval_taxonomy_parser.add_argument(
        "--trend-config-dir",
        default="config/trends",
        help="Directory containing trend config YAML files.",
    )
    eval_taxonomy_parser.add_argument(
        "--gold-set", default="ai/eval/gold_set.jsonl", help="Path to gold-set JSONL file."
    )
    eval_taxonomy_parser.add_argument(
        "--output-dir",
        default="ai/eval/results",
        help="Directory for taxonomy validation result artifacts.",
    )
    eval_taxonomy_parser.add_argument(
        "--max-items", type=int, default=200, help="Maximum dataset rows to validate."
    )
    eval_taxonomy_parser.add_argument(
        "--tier1-trend-mode",
        choices=["strict", "subset"],
        default="strict",
        help="Tier-1 key validation mode.",
    )
    eval_taxonomy_parser.add_argument(
        "--signal-type-mode",
        choices=["strict", "warn"],
        default="strict",
        help="Tier-2 signal-type mismatch behavior.",
    )
    eval_taxonomy_parser.add_argument(
        "--unknown-trend-mode",
        choices=["strict", "warn"],
        default="strict",
        help="Unknown trend mismatch behavior.",
    )
    eval_taxonomy_parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return non-zero exit code when warnings are emitted.",
    )
    eval_taxonomy_parser.set_defaults(
        handler=lambda args: runtime_result("eval-validate-taxonomy", args)
    )

    eval_replay_parser = eval_subparsers.add_parser(
        "replay", help="Run historical champion/challenger replay over stored outcomes."
    )
    add_leaf_options(eval_replay_parser)
    eval_replay_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for replay result artifacts."
    )
    eval_replay_parser.add_argument(
        "--champion-config",
        default="stable",
        choices=replay_config_choices,
        help="Champion replay policy config.",
    )
    eval_replay_parser.add_argument(
        "--challenger-config",
        default="fast_lower_threshold",
        choices=replay_config_choices,
        help="Challenger replay policy config.",
    )
    eval_replay_parser.add_argument("--trend-id", default=None, help="Optional trend UUID scope.")
    eval_replay_parser.add_argument(
        "--start-date", default=None, help="Optional ISO-8601 start datetime."
    )
    eval_replay_parser.add_argument(
        "--end-date", default=None, help="Optional ISO-8601 end datetime."
    )
    eval_replay_parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Replay window in days when start-date is not provided.",
    )
    eval_replay_parser.set_defaults(handler=lambda args: runtime_result("eval-replay", args))

    eval_vector_parser = eval_subparsers.add_parser(
        "vector-benchmark", help="Benchmark exact vs IVFFlat vs HNSW retrieval quality/latency."
    )
    add_leaf_options(eval_vector_parser)
    eval_vector_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for vector benchmark artifacts."
    )
    eval_vector_parser.add_argument(
        "--database-url", default=None, help="Optional PostgreSQL URL override."
    )
    eval_vector_parser.add_argument(
        "--dataset-size", type=int, default=4000, help="Number of benchmark vectors to generate."
    )
    eval_vector_parser.add_argument(
        "--query-count", type=int, default=200, help="Number of query vectors to evaluate."
    )
    eval_vector_parser.add_argument(
        "--dimensions",
        type=int,
        default=64,
        help="Embedding dimensions for synthetic benchmark vectors.",
    )
    eval_vector_parser.add_argument(
        "--top-k", type=int, default=10, help="Neighbors returned per query."
    )
    eval_vector_parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.88,
        help="Cosine similarity threshold used for retrieval filtering.",
    )
    eval_vector_parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for deterministic synthetic data."
    )
    eval_vector_parser.set_defaults(
        handler=lambda args: runtime_result("eval-vector-benchmark", args)
    )

    eval_embedding_lineage_parser = eval_subparsers.add_parser(
        "embedding-lineage", help="Report embedding model lineage and re-embed scope."
    )
    add_leaf_options(eval_embedding_lineage_parser)
    eval_embedding_lineage_parser.add_argument(
        "--target-model",
        default=default_embedding_model(),
        help="Embedding model that should be considered canonical.",
    )
    eval_embedding_lineage_parser.add_argument(
        "--fail-on-mixed",
        action="store_true",
        help="Return non-zero when multiple embedding models are detected.",
    )
    eval_embedding_lineage_parser.set_defaults(
        handler=lambda args: runtime_result("eval-embedding-lineage", args)
    )

    eval_source_freshness_parser = eval_subparsers.add_parser(
        "source-freshness", help="Report stale RSS/GDELT sources and catch-up candidates."
    )
    add_leaf_options(eval_source_freshness_parser)
    eval_source_freshness_parser.add_argument(
        "--stale-multiplier",
        type=float,
        default=None,
        help="Optional override for freshness stale threshold multiplier.",
    )
    eval_source_freshness_parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Return non-zero exit code when any stale source is detected.",
    )
    eval_source_freshness_parser.set_defaults(
        handler=lambda args: runtime_result("eval-source-freshness", args)
    )

    pipeline_parser = subparsers.add_parser("pipeline")
    pipeline_subparsers = pipeline_parser.add_subparsers(dest="pipeline_command")
    pipeline_dry_run_parser = pipeline_subparsers.add_parser(
        "dry-run",
        help="Run deterministic offline pipeline scoring on local fixtures.",
    )
    add_leaf_options(pipeline_dry_run_parser)
    pipeline_dry_run_parser.add_argument(
        "--fixture-path",
        default="ai/eval/fixtures/pipeline_dry_run_items.jsonl",
        help="Path to fixture JSONL file.",
    )
    pipeline_dry_run_parser.add_argument(
        "--trend-config-dir",
        default="config/trends",
        help="Directory containing trend config YAML files.",
    )
    pipeline_dry_run_parser.add_argument(
        "--output-path",
        default="artifacts/agent/pipeline-dry-run-output.json",
        help="Output JSON artifact path.",
    )
    pipeline_dry_run_parser.set_defaults(
        handler=lambda args: runtime_result("pipeline-dry-run", args)
    )

    agent_parser = subparsers.add_parser("agent")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")
    agent_smoke_parser = agent_subparsers.add_parser(
        "smoke",
        help="Run local agent-oriented smoke checks against a running Horadus API server.",
    )
    add_leaf_options(agent_smoke_parser)
    agent_smoke_parser.add_argument(
        "--base-url",
        default=default_agent_base_url(),
        help="Base URL for local smoke checks.",
    )
    agent_smoke_parser.add_argument(
        "--timeout-seconds", type=float, default=5.0, help="Per-request timeout in seconds."
    )
    agent_smoke_parser.add_argument(
        "--api-key",
        default=default_api_key(),
        help="Optional API key used when auth-protected smoke endpoints are checked.",
    )
    agent_smoke_parser.set_defaults(handler=handle_agent_smoke)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run local runtime diagnostics (hooks, config, DB, Redis, migration parity).",
    )
    add_leaf_options(doctor_parser)
    doctor_parser.add_argument(
        "--timeout-seconds", type=float, default=2.0, help="Timeout per dependency check."
    )
    doctor_parser.set_defaults(handler=lambda args: runtime_result("doctor", args))
