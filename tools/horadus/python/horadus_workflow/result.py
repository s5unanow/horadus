from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any


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


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, Any] | list[Any] | tuple[Any, ...] | date | datetime | Path

__all__ = [
    "CommandResult",
    "ExitCode",
    "JsonScalar",
    "JsonValue",
]
