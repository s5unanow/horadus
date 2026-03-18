"""Unit tests for scripts/check_pr_closure_state.py."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "check_pr_closure_state.py"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _seed_repo(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "archive" / "closed_tasks").mkdir(parents=True, exist_ok=True)
    (tasks_dir / "BACKLOG.md").write_text(
        "# Backlog\n\n### TASK-295: Enforce closure\n**Priority**: P1\n**Estimate**: 1d\n",
        encoding="utf-8",
    )
    (tasks_dir / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n**Sprint Number**: 4\n\n## Active Tasks\n- `TASK-295` Enforce closure\n",
        encoding="utf-8",
    )
    (tasks_dir / "COMPLETED.md").write_text("# Completed Tasks\n", encoding="utf-8")


def _run_guard(repo_root: Path, task_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT_PATH), "--repo-root", str(repo_root), "--task-id", task_id],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_check_pr_closure_state_module", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_pr_closure_state_fails_when_task_is_still_open(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    result = _run_guard(tmp_path, "TASK-295")

    assert result.returncode == 1
    assert "closure guard failed: TASK-295 is not fully closed" in result.stdout
    assert "tasks/BACKLOG.md still contains the task as open" in result.stdout
    assert "tasks/CURRENT_SPRINT.md still lists the task under Active Tasks" in result.stdout


def test_check_pr_closure_state_passes_when_task_is_closed_and_archived(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "# Backlog\n\n### TASK-296: Keep me live\n**Priority**: P1\n**Estimate**: 1d\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n**Sprint Number**: 4\n\n## Active Tasks\n- `TASK-296` Keep me live\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n## Sprint 4\n- TASK-295: Enforce closure ✅\n",
        encoding="utf-8",
    )
    (tmp_path / "archive" / "closed_tasks" / "2026-Q1.md").write_text(
        "\n".join(
            [
                "# Closed Task Archive",
                "",
                "**Status**: Archived closed-task ledger (non-authoritative)",
                "**Quarter**: 2026-Q1",
                "",
                "Do not read `archive/closed_tasks/` during normal implementation flow unless a user explicitly asks for historical context or an archive-aware CLI flag is used.",
                "",
                "---",
                "",
                "### TASK-295: Enforce closure",
                "**Priority**: P1",
                "**Estimate**: 1d",
                "",
                "Archived.",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_guard(tmp_path, "TASK-295")

    assert result.returncode == 0
    assert "closure guard passed: TASK-295 is closed in live ledgers and archived" in result.stdout


def test_check_pr_closure_state_rejects_invalid_task_id(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    result = _run_guard(tmp_path, "bad")

    assert result.returncode == 2
    assert "Invalid task id 'bad'. Expected TASK-XXX or XXX." in result.stdout


def test_check_pr_closure_state_invalid_task_id_without_repo_root_override(tmp_path: Path) -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT_PATH), "--task-id", "bad"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Invalid task id 'bad'. Expected TASK-XXX or XXX." in result.stdout


def test_blocker_lines_only_include_missing_closure_surfaces() -> None:
    module = _load_module()
    closure_state = module.TaskClosureState(
        task_id="TASK-351",
        present_in_backlog=False,
        active_sprint_lines=["- `TASK-351` Tighten scripts gate posture"],
        present_in_completed=False,
        present_in_closed_archive=False,
        closed_archive_path=None,
    )

    assert module._blocker_lines(closure_state) == [
        "- tasks/CURRENT_SPRINT.md still lists the task under Active Tasks:",
        "  - `TASK-351` Tighten scripts gate posture",
        "- tasks/COMPLETED.md is missing the compact completion entry.",
        "- archive/closed_tasks/*.md is missing the full archived task body.",
    ]


def test_blocker_lines_skip_closed_sections_that_are_already_satisfied() -> None:
    module = _load_module()
    closure_state = module.TaskClosureState(
        task_id="TASK-351",
        present_in_backlog=True,
        active_sprint_lines=[],
        present_in_completed=True,
        present_in_closed_archive=True,
        closed_archive_path="archive/closed_tasks/2026-Q1.md",
    )

    assert module._blocker_lines(closure_state) == [
        "- tasks/BACKLOG.md still contains the task as open."
    ]


def test_check_pr_closure_state_main_without_repo_override(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    closure_state = module.TaskClosureState(
        task_id="TASK-351",
        present_in_backlog=False,
        active_sprint_lines=[],
        present_in_completed=True,
        present_in_closed_archive=True,
        closed_archive_path="archive/closed_tasks/2026-Q1.md",
    )
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda _self, _argv: type("Args", (), {"task_id": "TASK-351", "repo_root": None})(),
    )
    monkeypatch.setattr(module, "task_closure_state", lambda _task_id: closure_state)

    assert module.main([]) == 0
    assert "closure guard passed: TASK-351 is closed" in capsys.readouterr().out
