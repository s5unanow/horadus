from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import LIVE_TASK_ID
from tools.horadus.python.horadus_cli.app import main
from tools.horadus.python.horadus_workflow import task_spec_resolution as spec_resolution_module

pytestmark = pytest.mark.unit


def test_task_record_prefers_structured_spec_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    specs_dir = tasks_dir / "specs"
    specs_dir.mkdir(parents=True)
    (tasks_dir / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-381: Retrieval metadata",
                "**Priority**: P1",
                "**Estimate**: 2h",
                "**Spec**: `tasks/specs/381-canonical.md`",
                "",
                "**Files**: `tools/horadus/python/horadus_workflow/`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tasks_dir / "CURRENT_SPRINT.md").write_text("# Current Sprint\n", encoding="utf-8")
    (tasks_dir / "COMPLETED.md").write_text("# Completed\n", encoding="utf-8")
    (specs_dir / "381-canonical.md").write_text("# canonical\n", encoding="utf-8")
    (specs_dir / "381-other.md").write_text("# other\n", encoding="utf-8")
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    record = task_repo_module.task_record("TASK-381")

    assert record is not None
    assert record.spec_paths == ["tasks/specs/381-canonical.md"]


def test_context_pack_implement_mode_includes_spec_resolution(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = synthetic_task_repo

    result = main(
        ["tasks", "context-pack", LIVE_TASK_ID, "--mode", "implement", "--format", "json"]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    spec_resolution = payload["data"]["retrieval_sources"]["task_spec_resolution"]
    assert spec_resolution["selected_paths"] == ["tasks/specs/901-stable-live-fixture.md"]
    assert spec_resolution["ambiguous"] is False
    excluded_reasons = {
        source["source"]: source["reason"]
        for source in payload["data"]["retrieval_sources"]["excluded"]
    }
    assert (
        excluded_reasons["archive/"]
        == "Archived task history is available only through explicit archive lookup."
    )
    assert (
        excluded_reasons["README.md"]
        == "Pointer/setup surface excluded from the Phase 1 implementation policy payload."
    )
    assert (
        excluded_reasons["local or hosted retrieval index"]
        == "Out of scope for the Phase 1 CLI-first implementation slice."
    )


def test_context_pack_implement_mode_fails_closed_on_ambiguous_specs(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (synthetic_task_repo / "tasks" / "specs" / "901-second-candidate.md").write_text(
        "# TASK-901 second legacy spec\n",
        encoding="utf-8",
    )

    result = main(
        ["tasks", "context-pack", LIVE_TASK_ID, "--mode", "implement", "--format", "json"]
    )

    assert result == int(task_commands_module.ExitCode.VALIDATION_ERROR)
    payload = json.loads(capsys.readouterr().out)
    assert "ambiguous canonical task spec candidates" in payload["errors"][0]


def test_task_spec_resolution_uses_supersession_metadata(tmp_path: Path) -> None:
    specs_dir = tmp_path / "tasks" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "381-old.md").write_text("# old\n", encoding="utf-8")
    (specs_dir / "381-new.md").write_text(
        "\n".join(
            [
                "---",
                "task_id: TASK-381",
                "retrieval:",
                "  kind: task-spec",
                "  status: active",
                "  canonical: true",
                "  supersedes:",
                "    - tasks/specs/381-old.md",
                "  superseded_by: null",
                "---",
                "# new",
                "",
            ]
        ),
        encoding="utf-8",
    )

    resolution = spec_resolution_module.resolve_task_spec_paths(
        repo_root=tmp_path,
        task_id="TASK-381",
    )

    assert resolution.ambiguous is False
    assert resolution.selected_paths == ("tasks/specs/381-new.md",)
    candidates = {item["path"]: item for item in resolution.to_payload()["candidates"]}
    assert candidates["tasks/specs/381-new.md"]["retrieval_ready"] is True
    assert candidates["tasks/specs/381-new.md"]["supersedes"] == ["tasks/specs/381-old.md"]


def test_task_spec_resolution_filters_status_only_superseded_spec(tmp_path: Path) -> None:
    specs_dir = tmp_path / "tasks" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "381-old.md").write_text(
        "\n".join(
            [
                "---",
                "task_id: TASK-381",
                "retrieval:",
                "  kind: task-spec",
                "  status: superseded",
                "  canonical: true",
                "---",
                "# old",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (specs_dir / "381-current.md").write_text(
        "\n".join(
            [
                "---",
                "task_id: TASK-381",
                "retrieval:",
                "  kind: task-spec",
                "  status: active",
                "  canonical: true",
                "---",
                "# current",
                "",
            ]
        ),
        encoding="utf-8",
    )

    resolution = spec_resolution_module.resolve_task_spec_paths(
        repo_root=tmp_path,
        task_id="TASK-381",
    )

    assert resolution.ambiguous is False
    assert resolution.selected_paths == ("tasks/specs/381-current.md",)


def test_task_spec_resolution_covers_ambiguous_active_metadata(tmp_path: Path) -> None:
    specs_dir = tmp_path / "tasks" / "specs"
    specs_dir.mkdir(parents=True)
    for name in ("381-a.md", "381-b.md"):
        (specs_dir / name).write_text(
            "\n".join(
                [
                    "---",
                    "task_id: TASK-381",
                    "retrieval:",
                    "  kind: task-spec",
                    "  status: active",
                    "  canonical: true",
                    "---",
                    f"# {name}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    resolution = spec_resolution_module.resolve_task_spec_paths(
        repo_root=tmp_path,
        task_id="TASK-381",
    )

    assert resolution.ambiguous is True
    assert resolution.selected_paths == ()
    assert "multiple active canonical" in (resolution.ambiguity_reason or "")


def test_task_spec_resolution_covers_reference_and_front_matter_edges(tmp_path: Path) -> None:
    specs_dir = tmp_path / "tasks" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "381-shorthand.md").write_text(
        "\n".join(
            [
                "---",
                "# comment",
                "",
                "task_id: TASK-381",
                "owner:",
                "  ignored: true",
                "retrieval:",
                "  kind: task-spec",
                "  status: active",
                "  canonical: false",
                "  supersedes: [tasks/specs/old.md, 'tasks/specs/older.md']",
                "  superseded_by: tasks/specs/381-next.md",
                "  flags: []",
                "---",
                "# shorthand",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (specs_dir / "381-unterminated.md").write_text("---\ntask_id: TASK-381\n", encoding="utf-8")
    (specs_dir / "381-malformed-top.md").write_text(
        "---\nmalformed\nretrieval:\n  kind: task-spec\n---\n",
        encoding="utf-8",
    )
    (specs_dir / "381-list-top.md").write_text("---\n- item\n---\n", encoding="utf-8")

    assert spec_resolution_module.spec_reference_paths_from_text("no spec") == []
    assert spec_resolution_module.spec_reference_paths_from_text("**Spec**: n/a") == []
    assert spec_resolution_module.spec_reference_paths_from_text(
        "**Spec**: `381-unterminated.md`, 381-shorthand.md, ignored.txt, 381-shorthand.md"
    ) == ["tasks/specs/381-unterminated.md", "tasks/specs/381-shorthand.md"]

    empty = spec_resolution_module.resolve_task_spec_paths(repo_root=tmp_path, task_id="TASK-999")
    missing = spec_resolution_module.resolve_task_spec_paths(
        repo_root=tmp_path,
        task_id="TASK-381",
        raw_block="**Spec**: `missing.md`",
    )
    selected = spec_resolution_module.resolve_task_spec_paths(
        repo_root=tmp_path,
        task_id="TASK-381",
        raw_block="**Spec**: `381-shorthand.md`",
    )

    assert empty.paths_for_context() == []
    assert missing.paths_for_context() == ["tasks/specs/missing.md"]
    assert missing.to_payload()["candidates"][0]["exists"] is False
    candidate = selected.to_payload()["candidates"][0]
    assert candidate["canonical"] is False
    assert candidate["superseded_by"] == "tasks/specs/381-next.md"
    assert candidate["supersedes"] == ["tasks/specs/old.md", "tasks/specs/older.md"]

    for name in ("381-unterminated.md", "381-malformed-top.md", "381-list-top.md"):
        resolution = spec_resolution_module.resolve_task_spec_paths(
            repo_root=tmp_path,
            task_id="TASK-381",
            raw_block=f"**Spec**: `{name}`",
        )
        assert resolution.to_payload()["candidates"][0]["retrieval_ready"] is False


def test_task_spec_resolution_ignores_non_file_glob_candidates(tmp_path: Path) -> None:
    specs_dir = tmp_path / "tasks" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "381-directory.md").mkdir()
    (specs_dir / "381-note.txt").write_text("not a spec\n", encoding="utf-8")
    (specs_dir / "381-real.md").write_text("# real\n", encoding="utf-8")

    assert spec_resolution_module.filename_spec_paths_for_task(tmp_path, "TASK-381") == [
        "tasks/specs/381-real.md"
    ]

    directory_resolution = spec_resolution_module.resolve_task_spec_paths(
        repo_root=tmp_path,
        task_id="TASK-381",
        raw_block="**Spec**: `tasks/specs/381-directory.md`",
    )

    assert directory_resolution.to_payload()["candidates"][0]["exists"] is True
    assert directory_resolution.to_payload()["candidates"][0]["retrieval_ready"] is False
