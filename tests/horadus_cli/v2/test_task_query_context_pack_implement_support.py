from __future__ import annotations

from pathlib import Path

import pytest

import tools.horadus.python.horadus_workflow.task_workflow_context_pack_implement_support as support_module

pytestmark = pytest.mark.unit


def test_current_sprint_extract_returns_placeholder_when_sprint_file_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_path = tmp_path / "tasks" / "CURRENT_SPRINT.md"
    monkeypatch.setattr(support_module.task_repo, "current_sprint_path", lambda: missing_path)

    payload = support_module.current_sprint_extract("TASK-999")

    assert payload == {
        "path": "tasks/CURRENT_SPRINT.md",
        "sprint_number": None,
        "sprint_goal": None,
        "sprint_dates": None,
        "active_task_lines": [],
        "selection_note_lines": [],
        "suggested_sequence_lines": [],
        "applicable_blockers": [],
        "constraints": [],
    }


def test_derive_test_candidates_covers_cli_runtime_and_transformed_module_stems(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tests" / "horadus_cli" / "v2").mkdir(parents=True)
    (tmp_path / "tests" / "api").mkdir(parents=True)
    (tmp_path / "tests" / "workflow").mkdir(parents=True)
    (tmp_path / "tests" / "horadus_cli" / "v2" / "test_task_demo.py").write_text(
        "def test_fixture() -> None:\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(support_module.task_repo, "repo_root", lambda: tmp_path)

    candidates = support_module.derive_test_candidates(
        declared_paths=[
            "tools/horadus/python/horadus_cli/",
            "tools/horadus/python/horadus_cli/",
            "src/api/routes.py",
            "src/",
            "tools/horadus/python/horadus_workflow/task_workflow_demo.py",
        ]
    )

    assert candidates == [
        {
            "path": "tests/horadus_cli/v2",
            "source_path": "tools/horadus/python/horadus_cli/",
            "match_reason": "cli_surface_path",
        },
        {
            "path": "tests/api",
            "source_path": "src/api/routes.py",
            "match_reason": "runtime_surface_path",
        },
        {
            "path": "tests/workflow",
            "source_path": "tools/horadus/python/horadus_workflow/task_workflow_demo.py",
            "match_reason": "workflow_helper_path",
        },
        {
            "path": "tests/horadus_cli/v2",
            "source_path": "tools/horadus/python/horadus_workflow/task_workflow_demo.py",
            "match_reason": "workflow_cli_surface",
        },
        {
            "path": "tests/horadus_cli/v2/test_task_demo.py",
            "source_path": "tools/horadus/python/horadus_workflow/task_workflow_demo.py",
            "match_reason": "module_stem_match",
        },
    ]


def test_derived_task_status_returns_none_when_status_is_missing() -> None:
    assert support_module.derived_task_status({}) is None


def test_current_sprint_extract_matches_exact_task_id_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_blockers(*, task_ids: set[str]) -> list[object]:
        _ = task_ids
        return []

    sprint_path = tmp_path / "tasks" / "CURRENT_SPRINT.md"
    sprint_path.parent.mkdir(parents=True)
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- `TASK-190` Dependency-note fixture blocked by `TASK-189` [REQUIRES_HUMAN]",
                "- `TASK-189` Human-gated fixture [REQUIRES_HUMAN]",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(support_module.task_repo, "current_sprint_path", lambda: sprint_path)
    monkeypatch.setattr(support_module.task_repo, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(support_module.task_repo, "parse_human_blockers", _no_blockers)

    payload = support_module.current_sprint_extract("TASK-189")

    assert payload["active_task_lines"] == ["- `TASK-189` Human-gated fixture [REQUIRES_HUMAN]"]
