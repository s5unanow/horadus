from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tools.horadus.python.horadus_cli import _ops_runtime_bridge as runtime_bridge
from tools.horadus.python.horadus_cli._ops_runtime_output import runtime_json_stdout_line
from tools.horadus.python.horadus_cli.result import ExitCode

pytestmark = pytest.mark.unit


def test_runtime_result_accepts_json_after_runtime_noise() -> None:
    payload = {"exit_code": 0, "lines": ["ok"]}

    result = runtime_bridge.runtime_result(
        "doctor",
        SimpleNamespace(),
        run_bridge=lambda *_args: SimpleNamespace(
            returncode=0,
            stdout=f"runtime noise\n{json.dumps(payload)}",
            stderr="",
        ),
        payload_factory=lambda _args: {},
        environment_error_exit_code=ExitCode.ENVIRONMENT_ERROR,
    )

    assert result.exit_code == ExitCode.OK
    assert result.lines == ["ok"]


def test_runtime_result_ignores_noise_after_json_payload() -> None:
    payload = {"exit_code": 0, "lines": ["ok"]}

    result = runtime_bridge.runtime_result(
        "doctor",
        SimpleNamespace(),
        run_bridge=lambda *_args: SimpleNamespace(
            returncode=0,
            stdout=f"runtime noise\n{json.dumps(payload)}\nlate noise",
            stderr="",
        ),
        payload_factory=lambda _args: {},
        environment_error_exit_code=ExitCode.ENVIRONMENT_ERROR,
    )

    assert result.exit_code == ExitCode.OK
    assert result.lines == ["ok"]


def test_runtime_json_stdout_line_skips_blank_lines() -> None:
    payload = {"exit_code": 0, "lines": ["ok"]}

    assert runtime_json_stdout_line(f"\n{json.dumps(payload)}\n") == json.dumps(payload)
    assert runtime_json_stdout_line("\n") == ""


def test_runtime_json_stdout_line_skips_non_object_json_lines() -> None:
    payload = {"exit_code": 0, "lines": ["ok"]}

    assert runtime_json_stdout_line(f"{json.dumps(payload)}\n[]") == json.dumps(payload)
