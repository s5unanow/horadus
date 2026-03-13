from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.result as result_module
import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module

pytestmark = pytest.mark.unit


def test_emit_result_serializes_errors_in_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = task_commands_module.CommandResult(
        exit_code=task_commands_module.ExitCode.VALIDATION_ERROR,
        data={"ok": False},
        error_lines=["bad input"],
    )

    result = result_module.emit_result(payload, "json")

    assert result == task_commands_module.ExitCode.VALIDATION_ERROR
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"
    assert output["errors"] == ["bad input"]


def test_json_default_serializes_dates_paths_and_dataclasses(tmp_path: Path) -> None:
    serialized_date = result_module._json_default(task_repo_module.date(2026, 3, 7))
    serialized_path = result_module._json_default(tmp_path / "artifact.json")
    serialized_dataclass = result_module._json_default(
        result_module.CommandResult(lines=["ok"], data={"x": 1})
    )

    assert serialized_date == "2026-03-07"
    assert str(tmp_path / "artifact.json") == serialized_path
    assert serialized_dataclass["lines"] == ["ok"]
    assert serialized_dataclass["data"] == {"x": 1}


def test_json_default_rejects_unknown_types() -> None:
    with pytest.raises(TypeError):
        result_module._json_default(object())


def test_emit_result_returns_plain_int_unchanged() -> None:
    assert result_module.emit_result(7, "json") == 7


def test_emit_result_json_omits_optional_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = result_module.emit_result(result_module.CommandResult(), "json")

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {"exit_code": 0, "status": "ok"}


def test_emit_result_prints_text_lines_and_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = result_module.CommandResult(
        exit_code=result_module.ExitCode.NOT_FOUND,
        lines=["stdout line"],
        error_lines=["stderr line"],
    )

    exit_code = result_module.emit_result(result, "text")

    captured = capsys.readouterr()
    assert exit_code == result_module.ExitCode.NOT_FOUND
    assert "stdout line" in captured.out
    assert "stderr line" in captured.err
