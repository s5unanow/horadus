"""
Horadus command-line interface compatibility module.
"""

from src.core.config import settings
from src.horadus_cli import legacy as _legacy
from src.horadus_cli.app import _build_parser, main

_change_arrow = _legacy._change_arrow
_format_trend_status_lines = _legacy._format_trend_status_lines
_http_get = _legacy._http_get
_http_get_json = _legacy._http_get_json
_doctor_check_database = _legacy._doctor_check_database
_doctor_check_redis = _legacy._doctor_check_redis


def _run_agent_smoke(*, base_url: str, timeout_seconds: float, api_key: str | None) -> int:
    _legacy._http_get = _http_get
    _legacy._http_get_json = _http_get_json
    return _legacy._run_agent_smoke(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
    )


def _run_doctor(*, timeout_seconds: float) -> int:
    _legacy._doctor_check_database = _doctor_check_database
    _legacy._doctor_check_redis = _doctor_check_redis
    return _legacy._run_doctor(timeout_seconds=timeout_seconds)


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
