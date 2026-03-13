from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed
from tools.horadus.python.horadus_cli.app import main

pytestmark = pytest.mark.unit


def test_ensure_required_hooks_reports_missing_hooks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text("#!/bin/sh\n", encoding="utf-8")
    pre_commit.chmod(0o755)

    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    hooks_ok, missing = task_commands_module._ensure_required_hooks()

    assert hooks_ok is False
    assert missing == ["pre-push", "commit-msg"]


def test_open_task_prs_filters_non_task_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "list"],
            stdout=json.dumps(
                [
                    {
                        "number": 12,
                        "headRefName": "codex/task-253-coverage-100",
                        "url": "https://x/12",
                    },
                    {"number": 13, "headRefName": "feature/misc", "url": "https://x/13"},
                ]
            ),
        ),
    )

    ok, payload = task_commands_module._open_task_prs()

    assert ok is True
    assert payload == ["#12 codex/task-253-coverage-100 https://x/12"]


def test_open_task_prs_reports_gh_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["gh", "pr", "list"], returncode=1, stderr="boom"),
    )

    ok, payload = task_commands_module._open_task_prs()

    assert ok is False
    assert payload == "boom"


def test_task_preflight_data_skips_when_env_override_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP_TASK_SEQUENCE_GUARD", "1")

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.OK
    assert data == {"skipped": True}
    assert "skipped" in lines[0]


def test_task_preflight_data_fails_without_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKIP_TASK_SEQUENCE_GUARD", raising=False)
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: None)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_command"] == "gh"
    assert "GitHub CLI" in lines[-1]


def test_task_preflight_data_fails_when_required_hooks_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(
        task_commands_module,
        "_ensure_required_hooks",
        lambda: (False, ["pre-commit", "pre-push"]),
    )

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_hooks"] == ["pre-commit", "pre-push"]
    assert "pre-commit, pre-push" in lines[-1]


def test_task_preflight_data_fails_when_not_on_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["git", "rev-parse"], stdout="codex/task-253-coverage-100\n"
        ),
    )

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["current_branch"] == "codex/task-253-coverage-100"
    assert "must start tasks from 'main'" in lines[-1]


def test_task_preflight_data_fails_for_dirty_worktree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=" M tasks/BACKLOG.md\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["working_tree_clean"] is False
    assert data["dirty_paths"] == ["tasks/BACKLOG.md"]
    assert "Working tree must be clean" in lines[1]


def test_git_status_dirty_paths_handles_blank_rename_and_quoted_paths() -> None:
    paths = task_commands_module._git_status_dirty_paths(
        '\nR  tasks/OLD.md -> tasks/BACKLOG.md\n M "PROJECT_STATUS.md"\n??\n'
    )

    assert paths == ["tasks/BACKLOG.md", "PROJECT_STATUS.md"]


def test_head_text_for_path_returns_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, stdout="head text"),
    )

    assert task_commands_module._head_text_for_path("tasks/BACKLOG.md") == "head text"


def test_head_text_for_path_returns_empty_on_missing_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, returncode=1),
    )

    assert task_commands_module._head_text_for_path("tasks/BACKLOG.md") == ""


def test_working_tree_text_for_path_returns_file_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "tasks" / "BACKLOG.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("working tree", encoding="utf-8")
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    assert task_commands_module._working_tree_text_for_path("tasks/BACKLOG.md") == "working tree"


def test_working_tree_text_for_path_returns_empty_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    assert task_commands_module._working_tree_text_for_path("tasks/BACKLOG.md") == ""


def test_index_text_for_path_returns_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, stdout="index text"),
    )

    assert task_commands_module._index_text_for_path("tasks/BACKLOG.md") == "index text"


def test_index_text_for_path_returns_empty_on_missing_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, returncode=1),
    )

    assert task_commands_module._index_text_for_path("tasks/BACKLOG.md") == ""


def test_changed_line_numbers_tracks_context_adds_and_deletes() -> None:
    old_lines, new_lines = task_commands_module._changed_line_numbers(
        "\n".join(
            [
                "diff --git a/tasks/BACKLOG.md b/tasks/BACKLOG.md",
                "@@ -3,2 +3,3 @@",
                " context",
                "-removed",
                "+added",
                "+added-two",
            ]
        )
    )

    assert old_lines == [4]
    assert new_lines == [4, 5]


def test_changed_line_numbers_ignores_non_content_hunk_lines() -> None:
    old_lines, new_lines = task_commands_module._changed_line_numbers(
        "\n".join(
            [
                "@@ -1 +1 @@",
                "\\ No newline at end of file",
            ]
        )
    )

    assert old_lines == []
    assert new_lines == []


def test_diff_texts_for_path_collects_staged_and_unstaged(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            _completed(["git", "diff"], stdout="unstaged"),
            _completed(["git", "diff", "--cached"], stdout="staged"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    texts = task_commands_module._diff_texts_for_path("tasks/BACKLOG.md")

    assert texts == [("unstaged", "unstaged"), ("staged", "staged")]


def test_diff_texts_for_path_skips_empty_or_failed_diffs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            _completed(["git", "diff"], stdout=""),
            _completed(["git", "diff", "--cached"], returncode=1, stdout="staged"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    texts = task_commands_module._diff_texts_for_path("tasks/BACKLOG.md")

    assert texts == []


def test_backlog_task_id_for_line_returns_nearest_header() -> None:
    text = "\n".join(
        [
            "# Backlog",
            "",
            "### TASK-253: Coverage",
            "Detail",
            "",
            "### TASK-254: Other",
            "Other detail",
        ]
    )

    assert task_commands_module._backlog_task_id_for_line(text, 4) == "TASK-253"
    assert task_commands_module._backlog_task_id_for_line(text, 7) == "TASK-254"
    assert task_commands_module._backlog_task_id_for_line(text, 0) is None
    assert task_commands_module._backlog_task_id_for_line("", 1) is None
    assert task_commands_module._backlog_task_id_for_line("No task header\nDetail", 2) is None


def test_backlog_task_id_for_line_does_not_cross_separator_boundaries() -> None:
    text = "\n".join(
        [
            "# Backlog",
            "",
            "### TASK-291: Existing",
            "Body",
            "---",
            "",
            "### TASK-296: New",
            "More",
        ]
    )

    assert task_commands_module._backlog_task_id_for_line(text, 5) is None
    assert task_commands_module._backlog_task_id_for_line(text, 6) is None
    assert task_commands_module._backlog_task_id_for_line(text, 7) == "TASK-296"


def test_dirty_task_refs_for_path_uses_changed_line_mapping_for_backlog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_head_text_for_path",
        lambda _path: "### TASK-253: Coverage\nold\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_index_text_for_path",
        lambda _path: "### TASK-253: Coverage\nold\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_working_tree_text_for_path",
        lambda _path: "### TASK-253: Coverage\nnew\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [("unstaged", "@@ -1,2 +1,2 @@\n-old\n+new\n")],
    )

    refs = task_commands_module._dirty_task_refs_for_path("tasks/BACKLOG.md")

    assert refs == {"TASK-253"}


def test_dirty_task_refs_for_path_parses_diff_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_head_text_for_path",
        lambda _path: "### TASK-253: Coverage\nold\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_index_text_for_path",
        lambda _path: "### TASK-254: Coverage\nnew\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_working_tree_text_for_path",
        lambda _path: "### TASK-254: Coverage\nnew\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [("staged", "@@ -1,2 +1,2 @@\n-old\n+new\n")],
    )

    refs = task_commands_module._dirty_task_refs_for_path("tasks/BACKLOG.md")

    assert refs == {"TASK-253", "TASK-254"}


def test_dirty_task_refs_for_path_parses_non_backlog_diff_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [
            (
                "unstaged",
                "\n".join(
                    [
                        "@@ -1 +1 @@",
                        "  `TASK-999` Context only",
                        "- `TASK-253` Coverage",
                        "+ `TASK-254` Coverage",
                    ]
                ),
            )
        ],
    )

    refs = task_commands_module._dirty_task_refs_for_path("tasks/CURRENT_SPRINT.md")

    assert refs == {"TASK-253", "TASK-254"}


def test_dirty_task_refs_for_path_returns_empty_on_diff_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [],
    )

    refs = task_commands_module._dirty_task_refs_for_path("tasks/BACKLOG.md")

    assert refs == set()


def test_dirty_task_refs_for_path_maps_unstaged_backlog_hunks_against_index_and_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_head_text_for_path",
        lambda _path: "### TASK-252: Head\nold\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_index_text_for_path",
        lambda _path: "### TASK-253: Index\nold\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_working_tree_text_for_path",
        lambda _path: "### TASK-254: Working\nnew\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [("unstaged", "@@ -1,2 +1,2 @@\n-old\n+new\n")],
    )

    refs = task_commands_module._dirty_task_refs_for_path("tasks/BACKLOG.md")

    assert refs == {"TASK-253", "TASK-254"}


def test_dirty_task_refs_for_path_maps_staged_backlog_hunks_against_head_and_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_head_text_for_path",
        lambda _path: "### TASK-252: Head\nold\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_index_text_for_path",
        lambda _path: "### TASK-253: Index\nnew\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_working_tree_text_for_path",
        lambda _path: "### TASK-254: Working\nnewer\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [("staged", "@@ -1,2 +1,2 @@\n-old\n+new\n")],
    )

    refs = task_commands_module._dirty_task_refs_for_path("tasks/BACKLOG.md")

    assert refs == {"TASK-252", "TASK-253"}


def test_dirty_task_refs_for_path_does_not_attribute_new_task_boundary_lines_to_prior_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_head_text_for_path",
        lambda _path: "### TASK-291: Existing\nBody\n---\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_index_text_for_path",
        lambda _path: "### TASK-291: Existing\nBody\n---\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_working_tree_text_for_path",
        lambda _path: "### TASK-291: Existing\nBody\n---\n\n### TASK-296: New\nMore\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [
            (
                "unstaged",
                "\n".join(
                    [
                        "@@ -1,3 +1,6 @@",
                        " ### TASK-291: Existing",
                        " Body",
                        " ---",
                        "+",
                        "+### TASK-296: New",
                        "+More",
                    ]
                ),
            )
        ],
    )

    refs = task_commands_module._dirty_task_refs_for_path("tasks/BACKLOG.md")

    assert refs == {"TASK-296"}


def test_task_ledger_intake_state_reports_missing_backlog_and_sprint_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "task_block_match", lambda _task_id: None)
    monkeypatch.setattr(
        task_commands_module, "_dirty_task_refs_for_path", lambda _path: {"TASK-253"}
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda: (_ for _ in ()).throw(ValueError("bad sprint section")),
    )

    state = task_commands_module._task_ledger_intake_state(
        task_id="TASK-253",
        dirty_paths=["tasks/CURRENT_SPRINT.md"],
    )

    assert state.ready is False
    assert state.eligible_paths == ["tasks/CURRENT_SPRINT.md"]
    assert state.consistency_errors == [
        "TASK-253 is not present in tasks/BACKLOG.md in the working tree.",
        "bad sprint section",
    ]


def test_task_ledger_intake_state_requires_target_task_in_dirty_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "task_block_match", lambda _task_id: object())
    monkeypatch.setattr(
        task_commands_module, "_dirty_task_refs_for_path", lambda _path: {"TASK-254"}
    )

    state = task_commands_module._task_ledger_intake_state(
        task_id="TASK-253",
        dirty_paths=["tasks/BACKLOG.md"],
    )

    assert state.ready is False
    assert state.consistency_errors == [
        "tasks/BACKLOG.md does not include TASK-253 in its dirty diff.",
        "tasks/BACKLOG.md contains edits for other tasks: TASK-254",
    ]


def test_task_ledger_intake_state_accepts_target_exec_plan_by_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "task_block_match", lambda _task_id: object())

    state = task_commands_module._task_ledger_intake_state(
        task_id="TASK-253",
        dirty_paths=["tasks/exec_plans/TASK-253.md"],
    )

    assert state.ready is True
    assert state.eligible_paths == ["tasks/exec_plans/TASK-253.md"]
    assert state.blocking_paths == []
    assert state.consistency_errors == []


def test_task_ledger_intake_state_rejects_other_task_exec_plan_by_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "task_block_match", lambda _task_id: object())

    state = task_commands_module._task_ledger_intake_state(
        task_id="TASK-253",
        dirty_paths=["tasks/exec_plans/TASK-254.md"],
    )

    assert state.ready is False
    assert state.eligible_paths == ["tasks/exec_plans/TASK-254.md"]
    assert state.consistency_errors == [
        "tasks/exec_plans/TASK-254.md does not belong to TASK-253.",
        "tasks/exec_plans/TASK-254.md contains edits for other tasks: TASK-254",
    ]


def test_task_ledger_intake_state_rejects_renamed_spec_with_other_task_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "task_block_match", lambda _task_id: object())
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [
            (
                "unstaged",
                "\n".join(
                    [
                        "diff --git a/tasks/specs/254-old-name.md b/tasks/specs/253-new-name.md",
                        "similarity index 100%",
                        "rename from tasks/specs/254-old-name.md",
                        "rename to tasks/specs/253-new-name.md",
                    ]
                ),
            )
        ],
    )

    state = task_commands_module._task_ledger_intake_state(
        task_id="TASK-253",
        dirty_paths=["tasks/specs/253-new-name.md"],
    )

    assert state.ready is False
    assert state.eligible_paths == ["tasks/specs/253-new-name.md"]
    assert state.consistency_errors == [
        "tasks/specs/253-new-name.md contains edits for other tasks: TASK-254",
    ]


def test_path_owned_task_start_intake_refs_from_diff_handles_diff_path_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [
            (
                "unstaged",
                "\n".join(
                    [
                        "--- a/tasks/exec_plans/TASK-254.md",
                        "+++ b/tasks/exec_plans/TASK-253.md",
                        "rename from docs/notes.md",
                        "rename to /dev/null",
                    ]
                ),
            )
        ],
    )

    refs = task_commands_module._path_owned_task_start_intake_refs_from_diff(
        "tasks/exec_plans/TASK-253.md"
    )

    assert refs == {"TASK-253", "TASK-254"}


def test_path_owned_task_start_intake_refs_from_diff_handles_shared_ledgers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_diff_texts_for_path",
        lambda _path: [("unstaged", "+++ b/tasks/specs/253-shared-ledger.md")],
    )

    refs = task_commands_module._path_owned_task_start_intake_refs_from_diff("tasks/BACKLOG.md")

    assert refs == {"TASK-253"}


def test_task_ledger_intake_state_handles_missing_backlog_and_sprint_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_block_match",
        lambda _task_id: (_ for _ in ()).throw(FileNotFoundError("missing backlog")),
    )
    monkeypatch.setattr(
        task_commands_module, "_dirty_task_refs_for_path", lambda _path: {"TASK-253"}
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda: (_ for _ in ()).throw(FileNotFoundError("missing sprint")),
    )

    state = task_commands_module._task_ledger_intake_state(
        task_id="TASK-253",
        dirty_paths=["tasks/BACKLOG.md", "tasks/CURRENT_SPRINT.md"],
    )

    assert state.ready is False
    assert state.consistency_errors == [
        "tasks/BACKLOG.md is missing in the working tree.",
        "TASK-253 is not present in tasks/BACKLOG.md in the working tree.",
        "missing sprint",
    ]


def _seed_task_start_intake_repo(tmp_path: Path, *, include_task_in_sprint: bool = True) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-253: Coverage",
                "**Priority**: P1",
                "**Estimate**: 1d",
                "",
                "Exercise intake-aware task start.",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    sprint_lines = [
        "# Current Sprint",
        "",
        "## Active Tasks",
    ]
    if include_task_in_sprint:
        sprint_lines.append("- `TASK-253` Coverage")
    (tasks_dir / "CURRENT_SPRINT.md").write_text(
        "\n".join([*sprint_lines, ""]),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "# Project Status\n\n**Status**: Archived pointer stub (non-authoritative)\n",
        encoding="utf-8",
    )


def test_task_preflight_data_reports_safe_start_hint_for_task_ledger_only_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(
                ["git", "status"], stdout=" M tasks/BACKLOG.md\n M tasks/CURRENT_SPRINT.md\n"
            ),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["eligible_dirty_paths"] == ["tasks/BACKLOG.md", "tasks/CURRENT_SPRINT.md"]
    assert "safe-start TASK-XXX --name short-name" in "\n".join(lines)


def test_task_preflight_data_blocks_mixed_dirty_paths_without_safe_start_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(
                ["git", "status"], stdout=" M tasks/BACKLOG.md\n M src/core/trend_engine.py\n"
            ),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["eligible_dirty_paths"] == ["tasks/BACKLOG.md"]
    assert data["blocking_dirty_paths"] == ["src/core/trend_engine.py"]
    assert "safe-start TASK-XXX --name short-name" not in "\n".join(lines)
    assert "Blocking dirty files: src/core/trend_engine.py" in lines


def test_task_preflight_data_allows_task_ledger_intake_for_target_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_task_start_intake_repo(tmp_path)
    monkeypatch.setattr(
        task_commands_module, "_dirty_task_refs_for_path", lambda _path: {"TASK-253"}
    )
    monkeypatch.setattr(
        task_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "tasks" / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_block_match",
        lambda task_id: task_repo_module.task_block_match(
            task_id, tmp_path / "tasks" / "BACKLOG.md"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda _path=None: task_repo_module.parse_active_tasks(
            tmp_path / "tasks" / "CURRENT_SPRINT.md"
        ),
    )
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(task_commands_module, "_open_task_prs", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(
                ["git", "status"], stdout=" M tasks/BACKLOG.md\n M tasks/CURRENT_SPRINT.md\n"
            ),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, data, lines = task_commands_module.task_preflight_data(
        task_id="TASK-253",
        allow_task_ledger_intake=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["working_tree_clean"] is False
    assert data["eligible_dirty_paths"] == ["tasks/BACKLOG.md", "tasks/CURRENT_SPRINT.md"]
    assert lines[1].startswith("Eligible planning intake files will carry onto the new branch")


def test_task_preflight_data_allows_untracked_target_exec_plan_for_task_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_task_start_intake_repo(tmp_path)
    monkeypatch.setattr(
        task_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "tasks" / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_block_match",
        lambda task_id: task_repo_module.task_block_match(
            task_id, tmp_path / "tasks" / "BACKLOG.md"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda _path=None: task_repo_module.parse_active_tasks(
            tmp_path / "tasks" / "CURRENT_SPRINT.md"
        ),
    )
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(task_commands_module, "_open_task_prs", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout="?? tasks/exec_plans/TASK-253.md\n"),
            _completed(["git", "diff"], stdout=""),
            _completed(["git", "diff", "--cached"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, data, lines = task_commands_module.task_preflight_data(
        task_id="TASK-253",
        allow_task_ledger_intake=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["eligible_dirty_paths"] == ["tasks/exec_plans/TASK-253.md"]
    assert "Eligible planning intake files will carry onto the new branch" in "\n".join(lines)


def test_task_preflight_data_allows_untracked_target_spec_for_task_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_task_start_intake_repo(tmp_path)
    monkeypatch.setattr(
        task_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "tasks" / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_block_match",
        lambda task_id: task_repo_module.task_block_match(
            task_id, tmp_path / "tasks" / "BACKLOG.md"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda _path=None: task_repo_module.parse_active_tasks(
            tmp_path / "tasks" / "CURRENT_SPRINT.md"
        ),
    )
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(task_commands_module, "_open_task_prs", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout="?? tasks/specs/253-some-plan.md\n"),
            _completed(["git", "diff"], stdout=""),
            _completed(["git", "diff", "--cached"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, data, _lines = task_commands_module.task_preflight_data(
        task_id="TASK-253",
        allow_task_ledger_intake=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["eligible_dirty_paths"] == ["tasks/specs/253-some-plan.md"]


def test_task_preflight_data_blocks_untracked_unrelated_exec_plan_for_task_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_task_start_intake_repo(tmp_path)
    monkeypatch.setattr(
        task_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "tasks" / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_block_match",
        lambda task_id: task_repo_module.task_block_match(
            task_id, tmp_path / "tasks" / "BACKLOG.md"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda _path=None: task_repo_module.parse_active_tasks(
            tmp_path / "tasks" / "CURRENT_SPRINT.md"
        ),
    )
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout="?? tasks/exec_plans/TASK-254.md\n"),
            _completed(["git", "diff"], stdout=""),
            _completed(["git", "diff", "--cached"], stdout=""),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, data, lines = task_commands_module.task_preflight_data(
        task_id="TASK-253",
        allow_task_ledger_intake=True,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["eligible_dirty_paths"] == ["tasks/exec_plans/TASK-254.md"]
    assert "does not belong to TASK-253" in "\n".join(lines)


def test_task_preflight_data_blocks_project_status_for_task_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=" M PROJECT_STATUS.md\n"),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, data, lines = task_commands_module.task_preflight_data(
        task_id="TASK-253",
        allow_task_ledger_intake=True,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["blocking_dirty_paths"] == ["PROJECT_STATUS.md"]
    assert "Blocking dirty files: PROJECT_STATUS.md" in lines


def test_task_preflight_data_blocks_unrelated_dirty_paths_even_with_task_ledger_intake(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_task_start_intake_repo(tmp_path)
    monkeypatch.setattr(
        task_commands_module, "_dirty_task_refs_for_path", lambda _path: {"TASK-253"}
    )
    monkeypatch.setattr(
        task_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "tasks" / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_block_match",
        lambda task_id: task_repo_module.task_block_match(
            task_id, tmp_path / "tasks" / "BACKLOG.md"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda _path=None: task_repo_module.parse_active_tasks(
            tmp_path / "tasks" / "CURRENT_SPRINT.md"
        ),
    )
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(
                ["git", "status"], stdout=" M tasks/BACKLOG.md\n M src/core/trend_engine.py\n"
            ),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, data, lines = task_commands_module.task_preflight_data(
        task_id="TASK-253",
        allow_task_ledger_intake=True,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["eligible_dirty_paths"] == ["tasks/BACKLOG.md"]
    assert data["blocking_dirty_paths"] == ["src/core/trend_engine.py"]
    assert "Blocking dirty files: src/core/trend_engine.py" in lines


def test_task_preflight_data_blocks_conflicting_task_ledger_intake_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_task_start_intake_repo(tmp_path, include_task_in_sprint=False)
    monkeypatch.setattr(
        task_commands_module, "_dirty_task_refs_for_path", lambda _path: {"TASK-253"}
    )
    monkeypatch.setattr(
        task_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "tasks" / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_block_match",
        lambda task_id: task_repo_module.task_block_match(
            task_id, tmp_path / "tasks" / "BACKLOG.md"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda _path=None: task_repo_module.parse_active_tasks(
            tmp_path / "tasks" / "CURRENT_SPRINT.md"
        ),
    )
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(
                ["git", "status"], stdout=" M tasks/BACKLOG.md\n M tasks/CURRENT_SPRINT.md\n"
            ),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, _data, lines = task_commands_module.task_preflight_data(
        task_id="TASK-253",
        allow_task_ledger_intake=True,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert "TASK-253 is not listed in Active Tasks" in "\n".join(lines)


def test_task_preflight_data_blocks_task_ledger_intake_for_other_task_refs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_task_start_intake_repo(tmp_path)
    monkeypatch.setattr(
        task_commands_module,
        "_dirty_task_refs_for_path",
        lambda path: {"TASK-253", "TASK-254"} if path == "tasks/BACKLOG.md" else {"TASK-253"},
    )
    monkeypatch.setattr(
        task_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "tasks" / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_block_match",
        lambda task_id: task_repo_module.task_block_match(
            task_id, tmp_path / "tasks" / "BACKLOG.md"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "parse_active_tasks",
        lambda _path=None: task_repo_module.parse_active_tasks(
            tmp_path / "tasks" / "CURRENT_SPRINT.md"
        ),
    )
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(
                ["git", "status"], stdout=" M tasks/BACKLOG.md\n M tasks/CURRENT_SPRINT.md\n"
            ),
        ]
    )

    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    exit_code, _data, lines = task_commands_module.task_preflight_data(
        task_id="TASK-253",
        allow_task_ledger_intake=True,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert "tasks/BACKLOG.md contains edits for other tasks: TASK-254" in "\n".join(lines)


def test_task_preflight_data_fails_when_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"], returncode=1, stderr="fetch failed"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["fetch_error"] == "fetch failed"
    assert lines[-1] == "fetch failed"


def test_task_preflight_data_fails_when_main_is_not_synced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="def\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["local_main_sha"] == "abc"
    assert data["remote_main_sha"] == "def"
    assert "not synced to origin/main" in lines[-1]


def test_task_preflight_data_fails_when_open_pr_query_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(task_commands_module, "_open_task_prs", lambda: (False, "gh failed"))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["open_pr_query_error"] == "gh failed"
    assert "Unable to query open PRs" in lines[-1]


def test_task_preflight_data_reports_open_task_prs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(
        task_commands_module, "_open_task_prs", lambda: (True, ["#12 codex/task-253-x"])
    )

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["open_task_prs"] == ["#12 codex/task-253-x"]
    assert "Open non-merged task PR" in "\n".join(lines)


def test_task_preflight_data_passes_when_open_pr_guard_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_OPEN_TASK_PRS", "1")
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["working_tree_clean"] is True
    assert "passed" in lines[0]


def test_task_preflight_data_passes_when_open_pr_query_returns_no_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALLOW_OPEN_TASK_PRS", raising=False)
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(task_commands_module, "_open_task_prs", lambda: (True, []))

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["local_main_sha"] == "abc"
    assert "passed" in lines[0]


def test_preflight_result_wraps_preflight_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["passed"]),
    )

    result = task_commands_module._preflight_result()

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data == {"ok": True}
    assert result.lines == ["passed"]


def test_eligibility_data_reports_missing_sprint_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", "/tmp/definitely-missing-sprint.md")

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert "Missing sprint file" in lines[0]
    assert data["sprint_file"].endswith("definitely-missing-sprint.md")


def test_eligibility_data_reports_invalid_active_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text("# Current Sprint\n", encoding="utf-8")
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["sprint_file"] == str(sprint_path)
    assert "Unable to locate Active Tasks section" in lines[0]


def test_eligibility_data_requires_task_to_be_in_active_tasks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-252` Something\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["task_id"] == "TASK-253"
    assert "not listed in Active Tasks" in lines[0]


def test_eligibility_data_reports_requires_human_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-189` Restricted health [REQUIRES_HUMAN]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-189")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["requires_human"] is True
    assert "[REQUIRES_HUMAN]" in lines[0]


def test_eligibility_data_respects_preflight_override_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-253` Coverage\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))
    monkeypatch.setenv("TASK_ELIGIBILITY_PREFLIGHT_CMD", "printf fail && exit 1")

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["preflight_cmd"] == "printf fail && exit 1"
    assert "preflight failed" in lines[0]


def test_eligibility_data_accepts_successful_preflight_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-253` Coverage\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))
    monkeypatch.setenv("TASK_ELIGIBILITY_PREFLIGHT_CMD", "printf ok")
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda _command: _completed(["sh"], stdout="ok"),
    )

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["task_id"] == "TASK-253"
    assert lines == ["Agent task eligibility passed: TASK-253"]


def test_eligibility_data_succeeds_for_active_non_human_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-253` Coverage\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))
    monkeypatch.delenv("TASK_ELIGIBILITY_PREFLIGHT_CMD", raising=False)
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["passed"]),
    )

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["requires_human"] is False
    assert lines == ["Agent task eligibility passed: TASK-253"]


def test_eligibility_data_propagates_preflight_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-253` Coverage\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))
    monkeypatch.delenv("TASK_ELIGIBILITY_PREFLIGHT_CMD", raising=False)
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"reason": "dirty"},
            ["preflight failed"],
        ),
    )

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["preflight"] == {"reason": "dirty"}
    assert lines[-1] == "Task sequencing preflight failed for TASK-253."


def test_start_task_data_rejects_existing_local_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _completed(args, returncode=0) if "show-ref" in args else _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert "already exists locally" in lines[0]


def test_start_task_data_returns_preflight_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"reason": "dirty"},
            ["preflight failed"],
        ),
    )

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["preflight"] == {"reason": "dirty"}
    assert lines == ["preflight failed"]


def test_start_task_data_rejects_existing_remote_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "show-ref" in args:
            return _completed(args, returncode=1)
        if "ls-remote" in args:
            return _completed(args, returncode=0)
        return _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert "already exists on origin" in lines[0]


def test_start_task_data_dry_run_reports_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _completed(args, returncode=1)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=True
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert "would create task branch codex/task-253-coverage-100" in lines[-1]


def test_start_task_data_reports_git_switch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "show-ref" in args or "ls-remote" in args:
            return _completed(args, returncode=1)
        if args[:2] == ["git", "switch"]:
            return _completed(args, returncode=1, stderr="switch failed")
        return _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["error"] == "switch failed"
    assert lines == ["switch failed"]


def test_start_task_data_switches_to_new_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "show-ref" in args or "ls-remote" in args:
            return _completed(args, returncode=1)
        if args[:2] == ["git", "switch"]:
            return _completed(args)
        return _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert lines[0] == "ok"
    assert "Created task branch: codex/task-253-coverage-100" in lines[-1]


def test_start_task_data_carries_task_ledger_intake_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda **_kwargs: (
            task_commands_module.ExitCode.OK,
            {
                "working_tree_clean": False,
                "eligible_dirty_paths": ["tasks/BACKLOG.md", "tasks/CURRENT_SPRINT.md"],
            },
            [
                "Task sequencing guard passed: main is synced and no open task PRs.",
                "Eligible planning intake files will carry onto the new branch for TASK-253: tasks/BACKLOG.md, tasks/CURRENT_SPRINT.md",
            ],
        ),
    )

    def fake_run_command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "show-ref" in args or "ls-remote" in args:
            return _completed(args, returncode=1)
        if args[:2] == ["git", "switch"]:
            return _completed(args)
        return _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert any(
        "Eligible planning intake files will carry onto the new branch" in line for line in lines
    )
    assert "Created task branch: codex/task-253-coverage-100" in lines


def test_safe_start_task_data_propagates_eligibility_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "eligibility_data",
        lambda _task_id: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"task_id": "TASK-253", "requires_human": True},
            ["TASK-253 is marked [REQUIRES_HUMAN] and is not eligible for autonomous start"],
        ),
    )

    exit_code, data, lines = task_commands_module.safe_start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["requires_human"] is True
    assert lines == ["TASK-253 is marked [REQUIRES_HUMAN] and is not eligible for autonomous start"]


def test_safe_start_task_data_runs_guarded_start_after_eligibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "eligibility_data",
        lambda _task_id: (
            task_commands_module.ExitCode.OK,
            {"task_id": "TASK-253"},
            ["Agent task eligibility passed: TASK-253"],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "start_task_data",
        lambda _task_id, name, *, dry_run: (
            task_commands_module.ExitCode.OK,
            {
                "task_id": "TASK-253",
                "branch_name": "codex/task-253-coverage-100",
                "dry_run": dry_run,
            },
            [
                "Task sequencing guard passed: main is clean/synced and no open task PRs.",
                f"Dry run: would create task branch codex/task-253-{name}",
            ],
        ),
    )

    exit_code, data, lines = task_commands_module.safe_start_task_data(
        "TASK-253", "coverage-100", dry_run=True
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert lines == [
        "Agent task eligibility passed: TASK-253",
        "Task sequencing guard passed: main is clean/synced and no open task PRs.",
        "Dry run: would create task branch codex/task-253-coverage-100",
    ]


def test_handle_preflight_returns_wrapped_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_preflight_result",
        lambda: task_commands_module.CommandResult(lines=["preflight ok"]),
    )

    result = task_commands_module.handle_preflight(argparse.Namespace())

    assert result.lines == ["preflight ok"]


def test_handle_eligibility_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_eligibility(argparse.Namespace(task_id="bad-task"))

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_handle_eligibility_wraps_eligibility_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "eligibility_data",
        lambda _task_id: (task_commands_module.ExitCode.OK, {"task_id": "TASK-253"}, ["eligible"]),
    )

    result = task_commands_module.handle_eligibility(argparse.Namespace(task_id="TASK-253"))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data == {"task_id": "TASK-253"}
    assert result.lines == ["eligible"]


def test_handle_start_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_start(
        argparse.Namespace(task_id="bad-task", name="coverage")
    )

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_handle_safe_start_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_safe_start(
        argparse.Namespace(task_id="bad-task", name="coverage")
    )

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_handle_safe_start_wraps_safe_start_task_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "safe_start_task_data",
        lambda _task_id, name, *, dry_run: (
            task_commands_module.ExitCode.OK,
            {"task_id": "TASK-253", "branch_name": f"codex/task-253-{name}", "dry_run": dry_run},
            ["safe start ok"],
        ),
    )

    result = task_commands_module.handle_safe_start(
        argparse.Namespace(task_id="TASK-253", name="coverage", dry_run=True)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data == {
        "task_id": "TASK-253",
        "branch_name": "codex/task-253-coverage",
        "dry_run": True,
    }
    assert result.lines == ["safe start ok"]


def test_main_tasks_start_honors_root_dry_run_flag(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_start_task_data(
        task_input: str,
        raw_name: str,
        *,
        dry_run: bool,
    ) -> tuple[int, dict[str, object], list[str]]:
        captured["task_input"] = task_input
        captured["raw_name"] = raw_name
        captured["dry_run"] = dry_run
        return (
            0,
            {
                "task_id": task_input,
                "branch_name": "codex/task-216-agent-facing-cli",
                "dry_run": dry_run,
            },
            ["ok"],
        )

    monkeypatch.setattr(task_commands_module, "start_task_data", fake_start_task_data)
    monkeypatch.setattr(task_commands_module, "start_task_data", fake_start_task_data)

    result = main(
        [
            "--format",
            "json",
            "--dry-run",
            "tasks",
            "start",
            "TASK-216",
            "--name",
            "agent-facing-cli",
        ]
    )

    assert result == 0
    assert captured == {
        "task_input": "TASK-216",
        "raw_name": "agent-facing-cli",
        "dry_run": True,
    }
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["dry_run"] is True


def test_handle_start_wraps_successful_start_task_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "start_task_data",
        lambda task_id, raw_name, *, dry_run: (
            0,
            {"task_id": task_id, "dry_run": dry_run},
            [raw_name],
        ),
    )

    result = task_commands_module.handle_start(
        argparse.Namespace(task_id="TASK-216", name="coverage", dry_run=True)
    )

    assert result.exit_code == 0
    assert result.data == {"task_id": "TASK-216", "dry_run": True}
    assert result.lines == ["coverage"]
