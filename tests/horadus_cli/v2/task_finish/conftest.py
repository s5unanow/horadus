from __future__ import annotations

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.task_finish.helpers import _closed_task_closure_state


@pytest.fixture(autouse=True)
def _default_task_closure_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_closure_state",
        lambda task_id: _closed_task_closure_state(task_id),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_pre_merge_task_closure_blocker",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_branch_head_alignment_blocker",
        lambda **_kwargs: None,
    )
