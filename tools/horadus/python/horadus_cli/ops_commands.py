from __future__ import annotations

import asyncio
import os
import subprocess  # nosec B404
import sys
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import dotenv_values

from tools.horadus.python.horadus_cli import _ops_defaults as defaults
from tools.horadus.python.horadus_cli import _ops_formatting as formatting
from tools.horadus.python.horadus_cli import _ops_http as http_helpers
from tools.horadus.python.horadus_cli import _ops_registration as registration
from tools.horadus.python.horadus_cli import _ops_runtime_bridge as runtime_bridge
from tools.horadus.python.horadus_cli import _ops_smoke as smoke_helpers
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

_change_arrow = formatting.change_arrow
_format_trend_status_lines = formatting.format_trend_status_lines
_parse_iso_datetime = formatting.parse_iso_datetime
_format_embedding_model_counts = formatting.format_embedding_model_counts
_json_default = formatting.json_default


def _runtime_payload(args: Any) -> dict[str, Any]:
    return runtime_bridge.runtime_payload(args, internal_arg_keys=_INTERNAL_ARG_KEYS)


def _run_runtime_bridge(action: str, payload: dict[str, Any]) -> Any:
    return runtime_bridge.run_runtime_bridge(
        action,
        payload,
        executable=sys.executable,
        runtime_bridge_module=_RUNTIME_BRIDGE_MODULE,
        json_default=_json_default,
        run=subprocess.run,
    )


def _runtime_result(action: str, args: Any) -> CommandResult:
    return runtime_bridge.runtime_result(
        action,
        args,
        run_bridge=_run_runtime_bridge,
        payload_factory=_runtime_payload,
        environment_error_exit_code=ExitCode.ENVIRONMENT_ERROR,
    )


def _http_get(url: str, *, timeout_seconds: float, headers: dict[str, str] | None = None) -> int:
    return http_helpers.http_get(
        url,
        timeout_seconds=timeout_seconds,
        headers=headers,
        request_factory=urllib_request.Request,
        urlopen=urllib_request.urlopen,
        http_error_type=urllib_error.HTTPError,
        url_error_type=urllib_error.URLError,
    )


def _http_get_json(
    url: str,
    *,
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object] | None]:
    return http_helpers.http_get_json(
        url,
        timeout_seconds=timeout_seconds,
        headers=headers,
        request_factory=urllib_request.Request,
        urlopen=urllib_request.urlopen,
        http_error_type=urllib_error.HTTPError,
        url_error_type=urllib_error.URLError,
    )


def _agent_smoke_checks(
    *,
    base_url: str,
    timeout_seconds: float,
    api_key: str | None,
) -> tuple[int, list[str], dict[str, Any]]:
    return smoke_helpers.agent_smoke_checks(
        base_url=base_url,
        environment=_default_environment(),
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        http_get=_http_get,
        http_get_json=_http_get_json,
        ok_exit_code=ExitCode.OK,
        validation_error_exit_code=ExitCode.VALIDATION_ERROR,
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
    return defaults.env_default(name, default, getenv=os.getenv)


def _dotenv_default(name: str) -> str | None:
    return defaults.dotenv_default(name, dotenv_loader=dotenv_values)


def _config_default(name: str, default: str) -> str:
    return defaults.config_default(name, default, getenv=os.getenv, dotenv_lookup=_dotenv_default)


def _read_secret_file(path_value: str | None) -> str | None:
    return defaults.read_secret_file(path_value)


def _default_api_key() -> str:
    return defaults.default_api_key(config_lookup=_config_default, secret_reader=_read_secret_file)


def _default_embedding_model() -> str:
    return defaults.default_embedding_model(config_lookup=_config_default)


def _default_agent_base_url() -> str:
    return defaults.default_agent_base_url(config_lookup=_config_default)


def _default_environment() -> str:
    return _config_default("ENVIRONMENT", "development").strip().lower() or "development"


_ops_leaf_options = registration.add_ops_leaf_options


def register_ops_commands(subparsers: Any) -> None:
    registration.register_ops_commands(
        subparsers,
        add_leaf_options=_ops_leaf_options,
        runtime_result=_runtime_result,
        handle_agent_smoke=_handle_agent_smoke,
        default_embedding_model=_default_embedding_model,
        default_agent_base_url=_default_agent_base_url,
        default_api_key=_default_api_key,
        benchmark_config_choices=_BENCHMARK_CONFIG_CHOICES,
        replay_config_choices=_REPLAY_CONFIG_CHOICES,
    )


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
