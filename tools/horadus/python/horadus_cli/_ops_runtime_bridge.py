from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from tools.horadus.python.horadus_cli.result import CommandResult


def runtime_payload(args: Any, *, internal_arg_keys: set[str]) -> dict[str, Any]:
    return {key: value for key, value in vars(args).items() if key not in internal_arg_keys}


def run_runtime_bridge(
    action: str,
    payload: dict[str, Any],
    *,
    executable: str,
    runtime_bridge_module: str,
    json_default: Callable[[object], object],
    run: Callable[..., Any],
) -> Any:
    return run(  # nosec B603
        [
            executable,
            "-m",
            runtime_bridge_module,
            action,
            "--payload",
            json.dumps(payload, sort_keys=True, default=json_default),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def runtime_result(
    action: str,
    args: Any,
    *,
    run_bridge: Callable[[str, dict[str, Any]], Any],
    payload_factory: Callable[[Any], dict[str, Any]],
    environment_error_exit_code: int,
) -> CommandResult:
    completed = run_bridge(action, payload_factory(args))
    stdout = completed.stdout.strip()
    if not stdout:
        return CommandResult(
            exit_code=environment_error_exit_code,
            error_lines=[
                f"{action} runtime bridge returned no JSON output",
                completed.stderr.strip() or "bridge stderr was empty",
            ],
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return CommandResult(
            exit_code=environment_error_exit_code,
            error_lines=[
                f"{action} runtime bridge returned invalid JSON: {exc}",
                stdout,
            ],
        )

    if not isinstance(payload, dict):
        return CommandResult(
            exit_code=environment_error_exit_code,
            error_lines=[f"{action} runtime bridge returned a non-object payload"],
        )

    exit_code = int(payload.get("exit_code", completed.returncode or environment_error_exit_code))
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
