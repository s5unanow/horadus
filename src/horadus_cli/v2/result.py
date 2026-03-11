from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, cast


class ExitCode(IntEnum):
    OK = 0
    VALIDATION_ERROR = 2
    NOT_FOUND = 3
    ENVIRONMENT_ERROR = 4


@dataclass(slots=True)
class CommandResult:
    exit_code: int = ExitCode.OK
    lines: list[str] | None = None
    data: dict[str, Any] | None = None
    error_lines: list[str] | None = None


def _json_default(value: object) -> object:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return asdict(cast("Any", value))
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def emit_result(result: CommandResult | int, output_format: str) -> int:
    if isinstance(result, int):
        return result
    if output_format == "json":
        payload: dict[str, Any] = {
            "exit_code": int(result.exit_code),
            "status": "ok" if result.exit_code == 0 else "error",
        }
        if result.data is not None:
            payload["data"] = result.data
        if result.lines:
            payload["lines"] = result.lines
        if result.error_lines:
            payload["errors"] = result.error_lines
        print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))
        return int(result.exit_code)
    for line in result.lines or []:
        print(line)
    for line in result.error_lines or []:
        print(line, file=sys.stderr)
    return int(result.exit_code)
