from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess  # nosec B404
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import dotenv_values

from tools.horadus.python.horadus_cli.result import CommandResult, ExitCode

_RUNTIME_BRIDGE_MODULE = "tools.horadus.python.horadus_app_cli_runtime"
_INTERNAL_ARG_KEYS = {
    "agent_command",
    "command",
    "dashboard_command",
    "dry_run",
    "eval_command",
    "handler",
    "output_format",
    "pipeline_command",
    "trends_command",
}
_BENCHMARK_CONFIG_CHOICES = (
    "baseline",
    "alternative",
    "tier1-gpt5-nano-minimal",
    "tier1-gpt5-nano-low",
    "tier2-gpt5-mini-low",
    "tier2-gpt5-mini-medium",
)
_REPLAY_CONFIG_CHOICES = ("stable", "fast_lower_threshold")


def _change_arrow(change: float) -> str:
    if change > 0:
        return "^"
    if change < 0:
        return "v"
    return "="


def _format_trend_status_lines(movement: Any) -> list[str]:
    header = (
        f"# {movement.trend_name}: "
        f"{movement.current_probability * 100:.1f}% "
        f"({movement.risk_level}) "
        f"{_change_arrow(movement.weekly_change)} "
        f"{movement.weekly_change * 100:+.1f}% this week "
        f"[{movement.movement_chart}]"
    )
    movers = ", ".join(movement.top_movers_7d) if movement.top_movers_7d else "none"
    return [header, f"  Top movers: {movers}"]


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def _format_embedding_model_counts(summary: Any) -> str:
    if not summary.model_counts:
        return "none"
    return ", ".join(f"{entry.model}={entry.count}" for entry in summary.model_counts)


def _json_default(value: object) -> object:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _runtime_payload(args: Any) -> dict[str, Any]:
    return {key: value for key, value in vars(args).items() if key not in _INTERNAL_ARG_KEYS}


def _run_runtime_bridge(action: str, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        [
            sys.executable,
            "-m",
            _RUNTIME_BRIDGE_MODULE,
            action,
            "--payload",
            json.dumps(payload, sort_keys=True, default=_json_default),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _runtime_result(action: str, args: Any) -> CommandResult:
    completed = _run_runtime_bridge(action, _runtime_payload(args))
    stdout = completed.stdout.strip()
    if not stdout:
        return CommandResult(
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            error_lines=[
                f"{action} runtime bridge returned no JSON output",
                completed.stderr.strip() or "bridge stderr was empty",
            ],
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return CommandResult(
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            error_lines=[
                f"{action} runtime bridge returned invalid JSON: {exc}",
                stdout,
            ],
        )

    if not isinstance(payload, dict):
        return CommandResult(
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            error_lines=[f"{action} runtime bridge returned a non-object payload"],
        )

    exit_code = int(payload.get("exit_code", completed.returncode or ExitCode.ENVIRONMENT_ERROR))
    data = payload.get("data")
    lines = payload.get("lines")
    error_lines = payload.get("error_lines")
    if lines is not None and not isinstance(lines, list):
        lines = [str(lines)]
    if error_lines is not None and not isinstance(error_lines, list):
        error_lines = [str(error_lines)]
    return CommandResult(
        exit_code=exit_code,
        data=data if isinstance(data, dict) else None,
        lines=[str(line) for line in lines] if isinstance(lines, list) else None,
        error_lines=[str(line) for line in error_lines] if isinstance(error_lines, list) else None,
    )


def _http_get(url: str, *, timeout_seconds: float, headers: dict[str, str] | None = None) -> int:
    request = urllib_request.Request(url=url, method="GET", headers=headers or {})
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            return int(response.status)
    except urllib_error.HTTPError as exc:
        return int(exc.code)
    except urllib_error.URLError:
        return 0


def _http_get_json(
    url: str,
    *,
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object] | None]:
    request = urllib_request.Request(url=url, method="GET", headers=headers or {})
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            status = int(response.status)
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                return status, payload
            return status, None
    except urllib_error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return int(exc.code), payload
        return int(exc.code), None
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, None


def _agent_smoke_checks(
    *,
    base_url: str,
    timeout_seconds: float,
    api_key: str | None,
) -> tuple[int, list[str], dict[str, Any]]:
    normalized_base_url = base_url.rstrip("/")
    lines: list[str] = []

    health_status = _http_get(f"{normalized_base_url}/health", timeout_seconds=timeout_seconds)
    if 200 <= health_status < 300:
        lines.append(f"PASS /health {health_status}")
    else:
        lines.append(f"FAIL /health {health_status or 'connection_error'}")
        return (ExitCode.VALIDATION_ERROR, lines, {"health_status": health_status})

    openapi_status, openapi_payload = _http_get_json(
        f"{normalized_base_url}/openapi.json",
        timeout_seconds=timeout_seconds,
    )
    if 200 <= openapi_status < 300:
        lines.append(f"PASS /openapi.json {openapi_status}")
    else:
        lines.append(f"FAIL /openapi.json {openapi_status or 'connection_error'}")
        return (
            ExitCode.VALIDATION_ERROR,
            lines,
            {"health_status": health_status, "openapi_status": openapi_status},
        )

    trend_headers = {"X-API-Key": api_key} if api_key else None
    trend_status = _http_get(
        f"{normalized_base_url}/api/v1/trends",
        timeout_seconds=timeout_seconds,
        headers=trend_headers,
    )
    if 200 <= trend_status < 300:
        lines.append(f"PASS /api/v1/trends {trend_status}")
        return (
            ExitCode.OK,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
            },
        )

    if trend_status in {401, 403} and not api_key:
        auth_hint = "unknown"
        if openapi_payload is not None:
            auth_hint = "openapi_security_present"
        lines.append(f"PASS /api/v1/trends {trend_status} auth_enforced_without_key ({auth_hint})")
        return (
            ExitCode.OK,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
                "auth_hint": auth_hint,
            },
        )

    if trend_status in {401, 403} and api_key:
        lines.append(f"FAIL /api/v1/trends {trend_status} api_key_rejected")
        return (
            ExitCode.VALIDATION_ERROR,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
            },
        )

    lines.append(f"FAIL /api/v1/trends {trend_status or 'connection_error'}")
    return (
        ExitCode.VALIDATION_ERROR,
        lines,
        {
            "health_status": health_status,
            "openapi_status": openapi_status,
            "trend_status": trend_status,
        },
    )


def _run_agent_smoke(*, base_url: str, timeout_seconds: float, api_key: str | None) -> int:
    exit_code, lines, _data = _agent_smoke_checks(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
    )
    for line in lines:
        print(line)
    return int(exit_code)


def _env_default(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip()
    return normalized or default


def _dotenv_default(name: str) -> str | None:
    value = dotenv_values(".env").get(name)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _config_default(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is not None:
        normalized = value.strip()
        if normalized:
            return normalized
    dotenv_value = _dotenv_default(name)
    if dotenv_value is not None:
        return dotenv_value
    return default


def _read_secret_file(path_value: str | None) -> str | None:
    if path_value is None:
        return None
    try:
        secret = Path(path_value).expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return secret or None


def _default_api_key() -> str:
    direct_value = _config_default("API_KEY", "")
    if direct_value:
        return direct_value
    secret_path = _config_default("API_KEY_FILE", "")
    return _read_secret_file(secret_path) or ""


def _default_embedding_model() -> str:
    return _config_default("EMBEDDING_MODEL", "text-embedding-3-small")


def _default_agent_base_url() -> str:
    host = _config_default("API_HOST", "127.0.0.1")
    port = _config_default("API_PORT", "8000")
    return f"http://{host}:{port}"


def _ops_leaf_options(parser: argparse.ArgumentParser) -> None:
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


def register_ops_commands(subparsers: Any) -> None:
    trends_parser = subparsers.add_parser("trends")
    trends_subparsers = trends_parser.add_subparsers(dest="trends_command")
    trends_status_parser = trends_subparsers.add_parser(
        "status",
        help="Show trend probabilities, weekly movement, and top movers.",
    )
    _ops_leaf_options(trends_status_parser)
    trends_status_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum number of active trends to display."
    )
    trends_status_parser.set_defaults(handler=lambda args: _runtime_result("trends-status", args))

    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_command")
    dashboard_export_parser = dashboard_subparsers.add_parser(
        "export",
        help="Export calibration dashboard to static JSON/HTML artifacts.",
    )
    _ops_leaf_options(dashboard_export_parser)
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
        handler=lambda args: _runtime_result("dashboard-export", args)
    )

    eval_parser = subparsers.add_parser("eval")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command")

    eval_benchmark_parser = eval_subparsers.add_parser(
        "benchmark",
        help="Run Tier-1/Tier-2 benchmark against ai/eval gold set.",
    )
    _ops_leaf_options(eval_benchmark_parser)
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
        choices=_BENCHMARK_CONFIG_CHOICES,
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
    eval_benchmark_parser.set_defaults(handler=lambda args: _runtime_result("eval-benchmark", args))

    eval_audit_parser = eval_subparsers.add_parser(
        "audit", help="Audit gold-set quality (provenance, diversity, and label coverage)."
    )
    _ops_leaf_options(eval_audit_parser)
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
    eval_audit_parser.set_defaults(handler=lambda args: _runtime_result("eval-audit", args))

    eval_taxonomy_parser = eval_subparsers.add_parser(
        "validate-taxonomy",
        help="Validate trend config taxonomy contract against the evaluation gold set.",
    )
    _ops_leaf_options(eval_taxonomy_parser)
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
        handler=lambda args: _runtime_result("eval-validate-taxonomy", args)
    )

    eval_replay_parser = eval_subparsers.add_parser(
        "replay", help="Run historical champion/challenger replay over stored outcomes."
    )
    _ops_leaf_options(eval_replay_parser)
    eval_replay_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for replay result artifacts."
    )
    eval_replay_parser.add_argument(
        "--champion-config",
        default="stable",
        choices=_REPLAY_CONFIG_CHOICES,
        help="Champion replay policy config.",
    )
    eval_replay_parser.add_argument(
        "--challenger-config",
        default="fast_lower_threshold",
        choices=_REPLAY_CONFIG_CHOICES,
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
    eval_replay_parser.set_defaults(handler=lambda args: _runtime_result("eval-replay", args))

    eval_vector_parser = eval_subparsers.add_parser(
        "vector-benchmark", help="Benchmark exact vs IVFFlat vs HNSW retrieval quality/latency."
    )
    _ops_leaf_options(eval_vector_parser)
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
        handler=lambda args: _runtime_result("eval-vector-benchmark", args)
    )

    eval_embedding_lineage_parser = eval_subparsers.add_parser(
        "embedding-lineage", help="Report embedding model lineage and re-embed scope."
    )
    _ops_leaf_options(eval_embedding_lineage_parser)
    eval_embedding_lineage_parser.add_argument(
        "--target-model",
        default=_default_embedding_model(),
        help="Embedding model that should be considered canonical.",
    )
    eval_embedding_lineage_parser.add_argument(
        "--fail-on-mixed",
        action="store_true",
        help="Return non-zero when multiple embedding models are detected.",
    )
    eval_embedding_lineage_parser.set_defaults(
        handler=lambda args: _runtime_result("eval-embedding-lineage", args)
    )

    eval_source_freshness_parser = eval_subparsers.add_parser(
        "source-freshness", help="Report stale RSS/GDELT sources and catch-up candidates."
    )
    _ops_leaf_options(eval_source_freshness_parser)
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
        handler=lambda args: _runtime_result("eval-source-freshness", args)
    )

    pipeline_parser = subparsers.add_parser("pipeline")
    pipeline_subparsers = pipeline_parser.add_subparsers(dest="pipeline_command")
    pipeline_dry_run_parser = pipeline_subparsers.add_parser(
        "dry-run",
        help="Run deterministic offline pipeline scoring on local fixtures.",
    )
    _ops_leaf_options(pipeline_dry_run_parser)
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
        handler=lambda args: _runtime_result("pipeline-dry-run", args)
    )

    agent_parser = subparsers.add_parser("agent")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")
    agent_smoke_parser = agent_subparsers.add_parser(
        "smoke",
        help="Run local agent-oriented smoke checks against a running Horadus API server.",
    )
    _ops_leaf_options(agent_smoke_parser)
    agent_smoke_parser.add_argument(
        "--base-url",
        default=_default_agent_base_url(),
        help="Base URL for local smoke checks.",
    )
    agent_smoke_parser.add_argument(
        "--timeout-seconds", type=float, default=5.0, help="Per-request timeout in seconds."
    )
    agent_smoke_parser.add_argument(
        "--api-key",
        default=_default_api_key(),
        help="Optional API key used when auth-protected smoke endpoints are checked.",
    )
    agent_smoke_parser.set_defaults(handler=_handle_agent_smoke)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run local runtime diagnostics (hooks, config, DB, Redis, migration parity).",
    )
    _ops_leaf_options(doctor_parser)
    doctor_parser.add_argument(
        "--timeout-seconds", type=float, default=2.0, help="Timeout per dependency check."
    )
    doctor_parser.set_defaults(handler=lambda args: _runtime_result("doctor", args))


def _sync_result(data: dict[str, Any], lines: list[str], exit_code: int) -> CommandResult:
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def _async_result(coro: Any) -> CommandResult:
    data, lines = asyncio.run(coro)
    return CommandResult(lines=lines, data=data)


def _async_result_with_exit(coro: Any) -> CommandResult:
    data, lines, exit_code = asyncio.run(coro)
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def _handle_agent_smoke(args: Any) -> CommandResult:
    exit_code, lines, data = _agent_smoke_checks(
        base_url=args.base_url,
        timeout_seconds=max(0.1, args.timeout_seconds),
        api_key=(args.api_key or "").strip() or None,
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)
