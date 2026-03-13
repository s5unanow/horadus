from __future__ import annotations

import asyncio
from typing import Any

from tools.horadus.python.horadus_cli.result import CommandResult


def sync_result(data: dict[str, Any], lines: list[str], exit_code: int) -> CommandResult:
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def async_result(coro: Any) -> CommandResult:
    data, lines = asyncio.run(coro)
    return CommandResult(lines=lines, data=data)


def async_result_with_exit(coro: Any) -> CommandResult:
    data, lines, exit_code = asyncio.run(coro)
    return CommandResult(exit_code=exit_code, lines=lines, data=data)
