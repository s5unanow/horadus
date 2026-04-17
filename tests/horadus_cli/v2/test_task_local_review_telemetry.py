from __future__ import annotations

from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_repo as task_repo_module
from tools.horadus.python.horadus_workflow._task_workflow_local_review_models import (
    LocalReviewContext,
    LocalReviewProviderRun,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_repo_root_override() -> None:
    task_repo_module.clear_repo_root_override()
    yield
    task_repo_module.clear_repo_root_override()


def _seed_repo_root(tmp_path: Path) -> None:
    task_repo_module.set_repo_root_override(tmp_path)
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='horadus'\n", encoding="utf-8")


def _fake_review_context() -> LocalReviewContext:
    return LocalReviewContext(
        current_branch="codex/task-369-slop-aware-local-review",
        task_id="TASK-369",
        base_branch="main",
        review_target_kind="branch_diff",
        review_target_value="main...codex/task-369-slop-aware-local-review",
        diff_text="diff --git a/foo.py b/foo.py\n+line\n",
        diff_stat=" foo.py | 1 +\n",
        changed_files=["foo.py"],
        working_tree_dirty=False,
    )


def test_local_review_data_keeps_generated_context_out_of_custom_instruction_telemetry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    monkeypatch.setattr(
        task_commands_module, "_review_context", lambda **_kwargs: _fake_review_context()
    )
    monkeypatch.setattr(
        task_commands_module.local_review_module,
        "prepare_review_run",
        lambda **_kwargs: (
            ["claude"],
            "Use the changed-file code-health summary below.",
            [
                "Local review configuration:",
                "- instructions supplied: no",
                "- effective provider instructions: auto-enriched changed-file code-health context only",
            ],
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_execute_provider",
        lambda provider, **_kwargs: LocalReviewProviderRun(
            provider=provider,
            interface_kind="prompt",
            command=[provider],
            prompt="prompt",
            returncode=0,
            stdout="HORADUS-LOCAL-REVIEW: no-findings\nNo findings.\n",
            stderr="",
            duration_seconds=0.2,
        ),
    )

    exit_code, data, lines = task_commands_module.local_review_data(
        provider="claude",
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["custom_instructions_supplied"] is False
    assert "- instructions supplied: no" in lines
    assert (
        "- effective provider instructions: auto-enriched changed-file code-health context only"
        in lines
    )
