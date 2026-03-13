from __future__ import annotations

import pytest

import tools.horadus.python.horadus_cli.task_process as task_process_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module

pytestmark = pytest.mark.unit


def test_task_process_wrapper_reexports_workflow_core_helpers() -> None:
    assert task_process_module._run_command is task_commands_module._run_command
    assert task_process_module._run_command_with_timeout is (
        task_commands_module._run_command_with_timeout
    )
    assert task_process_module.ensure_docker_ready is task_commands_module.ensure_docker_ready
    assert "CommandTimeoutError" in task_process_module.__all__
