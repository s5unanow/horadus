#!/usr/bin/env python3
"""Runtime SLO/error-budget release gate evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.config import settings
from src.core.release_gate_runtime import (
    RuntimeGateThresholds,
    evaluate_runtime_gate,
    parse_stage_metrics,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate cross-stage runtime SLO gate.")
    parser.add_argument(
        "--input",
        default="artifacts/agent/runtime_slo_metrics.json",
        help="Path to runtime metrics JSON payload.",
    )
    parser.add_argument(
        "--environment",
        default=settings.ENVIRONMENT,
        choices=["development", "staging", "production"],
        help="Environment posture used to resolve strict vs warn-only mode.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Force strict fail-closed behavior regardless of environment.",
    )
    parser.add_argument("--max-error-rate", type=float, default=0.05)
    parser.add_argument("--max-p95-latency-ms", type=float, default=1200.0)
    parser.add_argument("--max-budget-denial-rate", type=float, default=0.10)
    parser.add_argument("--max-production-error-rate-drift", type=float, default=0.02)
    parser.add_argument("--min-window-minutes", type=int, default=60)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    strict_mode = bool(args.strict or args.environment in {"staging", "production"})

    input_path = Path(args.input)
    if not input_path.exists():
        message = f"runtime metrics input not found: {input_path}"
        if strict_mode:
            print(f"FAIL {message}")
            return 2
        print(f"WARN {message}")
        return 0

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL invalid JSON in {input_path}: {exc}")
        return 2

    try:
        stage_metrics = parse_stage_metrics(payload)
    except ValueError as exc:
        print(f"FAIL {exc}")
        return 2

    thresholds = RuntimeGateThresholds(
        max_error_rate=max(0.0, min(1.0, args.max_error_rate)),
        max_p95_latency_ms=max(1.0, args.max_p95_latency_ms),
        max_budget_denial_rate=max(0.0, min(1.0, args.max_budget_denial_rate)),
        max_production_error_rate_drift=max(0.0, min(1.0, args.max_production_error_rate_drift)),
        min_window_minutes=max(1, args.min_window_minutes),
    )

    result = evaluate_runtime_gate(
        metrics_by_stage=stage_metrics,
        thresholds=thresholds,
        strict_mode=strict_mode,
    )

    for check in result.checks:
        print(
            f"{check.status} {check.stage}.{check.metric} "
            f"observed={check.observed:.4f} threshold={check.threshold:.4f} "
            f"({check.message})"
        )

    if result.has_failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
