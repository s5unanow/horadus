"""Runtime-bridge helpers for regression-intake CLI commands."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from src.eval.regression_intake import run_regression_intake


def collect_eval_regression_intake(args: Any) -> tuple[dict[str, Any], list[str], int]:
    """Run regression intake and format a runtime-bridge friendly payload."""

    try:
        result = run_regression_intake(
            source_surface=args.source_surface,
            input_path=args.input,
            output_dir=args.output_dir,
        )
    except ValueError as exc:
        message = str(exc)
        return (
            {"error": message},
            [f"Regression intake configuration error: {message}"],
            2,
        )

    lines = [
        f"Regression intake output: {result.output_path}",
        f"Source surface: {result.source_surface}",
        f"Source records: {result.total_records}",
        f"Emitted cases: {result.emitted_cases}",
    ]
    return (
        {
            "output_path": str(result.output_path),
            "source_surface": result.source_surface,
            "total_records": result.total_records,
            "emitted_cases": result.emitted_cases,
        },
        lines,
        0,
    )


def action_eval_regression_intake(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap regression intake into the runtime-bridge action payload shape."""

    data, lines, exit_code = collect_eval_regression_intake(SimpleNamespace(**payload))
    result: dict[str, Any] = {"exit_code": exit_code, "data": data}
    if lines:
        result["lines"] = lines
    return result
