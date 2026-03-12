"""
Horadus command-line interface compatibility module.
"""

import src.cli_runtime as _runtime
from src.cli_runtime import _doctor_check_database, _doctor_check_redis, settings
from tools.horadus.python.horadus_cli import ops_commands as _ops
from tools.horadus.python.horadus_cli.app import _build_parser, main

_change_arrow = _ops._change_arrow
_format_trend_status_lines = _ops._format_trend_status_lines
_http_get = _ops._http_get
_http_get_json = _ops._http_get_json


def _run_agent_smoke(*, base_url: str, timeout_seconds: float, api_key: str | None) -> int:
    _ops._http_get = _http_get
    _ops._http_get_json = _http_get_json
    return _ops._run_agent_smoke(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
    )


def _run_doctor(*, timeout_seconds: float) -> int:
    _runtime._doctor_check_database = _doctor_check_database
    _runtime._doctor_check_redis = _doctor_check_redis
    _data, lines, exit_code = _runtime._collect_doctor(timeout_seconds)
    for line in lines:
        print(line)
    return int(exit_code)


__all__ = [
    "_build_parser",
    "_change_arrow",
    "_doctor_check_database",
    "_doctor_check_redis",
    "_format_trend_status_lines",
    "_http_get",
    "_http_get_json",
    "_run_agent_smoke",
    "_run_doctor",
    "main",
    "settings",
]


if __name__ == "__main__":
    raise SystemExit(main())
