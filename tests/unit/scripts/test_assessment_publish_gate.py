"""Unit tests for scripts/assessment_publish_gate.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "assessment_publish_gate.py"


def _run(*args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT_PATH), *[str(arg) for arg in args]],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_module() -> ModuleType:
    module_name = f"assessment_publish_gate_test_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_current_sprint(
    tmp_path: Path,
    *,
    active_lines: list[str],
    blocker_lines: list[str],
) -> Path:
    sprint_file = tmp_path / "tasks" / "CURRENT_SPRINT.md"
    sprint_file.parent.mkdir(parents=True, exist_ok=True)
    sprint_file.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "**Sprint Goal**: Test gate",
                "**Sprint Number**: 3",
                "**Sprint Dates**: 2026-03-04 to 2026-03-18",
                "",
                "## Active Tasks",
                "",
                *active_lines,
                "",
                "## Human Blocker Metadata",
                "",
                *blocker_lines,
                "",
                "## Telegram Launch Scope",
                "",
                "- launch_scope: excluded_until_task_080_done",
                "- decision_date: 2026-03-03",
                "- rationale: Telegram stays out of scope.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return sprint_file


def test_publish_gate_skips_unchanged_human_gated_queue(tmp_path: Path) -> None:
    sprint_file = _write_current_sprint(
        tmp_path,
        active_lines=[
            "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
            "- `TASK-189` Restrict `/health` and `/metrics` exposure outside development [REQUIRES_HUMAN]",
        ],
        blocker_lines=[
            "- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7",
            "- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7",
        ],
    )
    memory_file = tmp_path / ".codex" / "automations" / "repo-state-po" / "memory.md"
    first_publish = _run(
        "--role",
        "po",
        "--sprint-file",
        sprint_file,
        "--memory-file",
        memory_file,
        cwd=tmp_path,
    )
    assert first_publish.returncode == 0
    assert "decision=publish" in first_publish.stdout

    second_result = _run(
        "--role",
        "po",
        "--sprint-file",
        sprint_file,
        "--memory-file",
        memory_file,
        cwd=tmp_path,
    )
    assert second_result.returncode == 0
    assert "decision=skip" in second_result.stdout
    assert "reason=unchanged_human_gated_queue" in second_result.stdout


def test_publish_gate_publishes_when_human_gated_queue_changes(tmp_path: Path) -> None:
    sprint_file = _write_current_sprint(
        tmp_path,
        active_lines=[
            "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
            "- `TASK-189` Restrict `/health` and `/metrics` exposure outside development [REQUIRES_HUMAN]",
        ],
        blocker_lines=[
            "- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7",
            "- TASK-189 | owner=human-operator | last_touched=2026-03-06 | next_action=2026-03-07 | escalate_after_days=7",
        ],
    )
    memory_file = tmp_path / ".codex" / "automations" / "repo-state-po" / "memory.md"
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text(
        "\n".join(
            [
                "# Repo state PO automation memory",
                "",
                "## 2026-03-05 publish gate",
                "- role: po",
                "- decision: publish",
                "- reason: human_gated_queue_changed",
                "- blocker_state_hash: oldhash",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(
        "--role",
        "po",
        "--sprint-file",
        sprint_file,
        "--memory-file",
        memory_file,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "decision=publish" in result.stdout
    assert "reason=human_gated_queue_changed" in result.stdout


def test_publish_gate_publishes_when_queue_is_mixed(tmp_path: Path) -> None:
    sprint_file = _write_current_sprint(
        tmp_path,
        active_lines=[
            "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
            "- `TASK-214` Switch PO/BA automations to change-triggered publishing under fully human-gated queues",
        ],
        blocker_lines=[
            "- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7",
        ],
    )
    memory_file = tmp_path / ".codex" / "automations" / "repos-state-ba" / "memory.md"

    result = _run(
        "--role",
        "ba",
        "--sprint-file",
        sprint_file,
        "--memory-file",
        memory_file,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "decision=publish" in result.stdout
    assert "reason=queue_not_fully_human_gated" in result.stdout
    assert "fully_human_gated=false" in result.stdout
    assert "blocker_state_hash:" in memory_file.read_text(encoding="utf-8")


def test_parse_current_sprint_skips_malformed_lines_and_sections(tmp_path: Path) -> None:
    module = _load_module()
    sprint_file = tmp_path / "tasks" / "CURRENT_SPRINT.md"
    sprint_file.parent.mkdir(parents=True, exist_ok=True)
    sprint_file.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- malformed active line",
                "- `TASK-351` Tighten scripts gate posture [REQUIRES_HUMAN]",
                "",
                "## Human Blocker Metadata",
                "- malformed blocker metadata",
                "- TASK-351 | owner=human-operator | malformed-field | next_action=2026-03-19",
                "",
                "## Telegram Launch Scope",
                "- launch_scope: scripts_only",
                "- malformed launch scope",
                "",
                "## Another Section",
                "- ignored: value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    active_tasks, blocker_metadata, launch_scope = module._parse_current_sprint(sprint_file)

    assert [(task.task_id, task.requires_human) for task in active_tasks] == [("TASK-351", True)]
    assert blocker_metadata == {
        "TASK-351": {"owner": "human-operator", "next_action": "2026-03-19"}
    }
    assert launch_scope == {"launch_scope": "scripts_only"}


def test_memory_helpers_handle_missing_hash_and_unwritable_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    memory_file = tmp_path / "memory.md"
    memory_file.write_text("# memory\n", encoding="utf-8")
    assert module._load_previous_hash(memory_file) is None

    decision = module.GateDecision(
        role="po",
        decision="publish",
        reason="queue_not_fully_human_gated",
        blocker_state_hash="hash",
        previous_blocker_state_hash=None,
        fully_human_gated=False,
        active_task_ids=(),
    )
    target = tmp_path / "nested" / "memory.md"
    monkeypatch.setattr(module.os, "access", lambda *_args: False)

    with pytest.raises(PermissionError, match="memory directory is not writable"):
        module._append_memory_entry(target, decision)
