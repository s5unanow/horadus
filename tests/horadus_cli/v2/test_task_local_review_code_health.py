from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_repo as task_repo_module
from tests.horadus_cli.v2.helpers import _completed
from tools.horadus.python.horadus_workflow import (
    _task_workflow_local_review_code_health as code_health_prompt_module,
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


def _write_code_health_artifact(
    tmp_path: Path,
    *,
    filename: str,
    resolved_base_ref: str,
    resolved_head_ref: str,
    compared_files: int = 1,
    flagged_files: int = 1,
    files: list[dict[str, object]] | None = None,
) -> None:
    results_dir = tmp_path / "ai" / "eval" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": "code-health.v1",
        "generated_at": "2026-04-13T10:00:00+00:00",
        "passes_validation": flagged_files == 0,
        "comparison": {
            "mode": "merge-base",
            "base_ref": "merge-base(main, HEAD)",
            "resolved_base_ref": resolved_base_ref,
            "head_ref": "HEAD",
            "resolved_head_ref": resolved_head_ref,
            "merge_base_target": "main",
        },
        "summary": {
            "compared_files": compared_files,
            "flagged_files": flagged_files,
            "change_counts": {"added": 0, "modified": compared_files, "removed": 0},
            "metrics": [
                "module_lines",
                "callable_count",
                "statement_count",
                "total_member_lines",
                "max_member_lines",
                "total_member_complexity",
                "max_member_complexity",
            ],
        },
        "files": files
        or [
            {
                "path": "foo.py",
                "change_type": "modified",
                "delta": {"statement_count": 3, "max_member_lines": 7},
                "worsened_metrics": ["statement_count", "max_member_lines"],
                "improved_metrics": [],
            }
        ],
    }
    (results_dir / filename).write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_local_review_data_appends_code_health_summary_to_provider_instructions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    _write_code_health_artifact(
        tmp_path,
        filename="code-health-20260413T100000Z-fixture.json",
        resolved_base_ref="merge-base-sha",
        resolved_head_ref="head-sha",
    )
    captured: dict[str, str | None] = {}

    def fake_review_git(args: list[str]) -> object:
        mapping = {
            ("rev-parse", "--abbrev-ref", "HEAD"): _completed(
                ["git", *args], stdout="codex/task-286-local-review\n"
            ),
            ("rev-parse", "--verify", "main"): _completed(["git", *args], stdout="base-sha\n"),
            ("rev-parse", "--verify", "HEAD"): _completed(["git", *args], stdout="head-sha\n"),
            ("merge-base", "main", "HEAD"): _completed(["git", *args], stdout="merge-base-sha\n"),
            (
                "diff",
                "--no-ext-diff",
                "--find-renames",
                "main...HEAD",
            ): _completed(["git", *args], stdout="diff --git a/foo.py b/foo.py\n+line\n"),
            ("diff", "--stat", "--no-ext-diff", "main...HEAD"): _completed(
                ["git", *args], stdout=" foo.py | 1 +\n"
            ),
            ("diff", "--name-only", "--no-ext-diff", "main...HEAD"): _completed(
                ["git", *args], stdout="foo.py\n"
            ),
            ("status", "--short"): _completed(["git", *args], stdout=""),
        }
        return mapping[tuple(args)]

    monkeypatch.setattr(task_commands_module, "_run_git", fake_review_git)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )

    def fake_execute_provider(
        provider: str, **kwargs: object
    ) -> task_commands_module.LocalReviewProviderRun:
        captured["instructions"] = kwargs.get("instructions")  # type: ignore[assignment]
        return task_commands_module.LocalReviewProviderRun(
            provider=provider,
            interface_kind="prompt",
            command=[provider],
            prompt="prompt",
            returncode=0,
            stdout="HORADUS-LOCAL-REVIEW: no-findings\nNo findings.\n",
            stderr="",
            duration_seconds=0.1,
        )

    monkeypatch.setattr(task_commands_module, "_execute_provider", fake_execute_provider)

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
    assert data["findings_reported"] is False
    assert (
        "- changed-file code-health: ai/eval/results/code-health-20260413T100000Z-fixture.json"
        in lines
    )
    assert captured["instructions"] is not None
    assert (
        "Changed-file code-health artifact: ai/eval/results/code-health-20260413T100000Z-fixture.json"
        in captured["instructions"]
    )
    assert (
        "foo.py: worsened statement_count (+3), max_member_lines (+7)" in captured["instructions"]
    )


def test_code_health_prompt_helpers_cover_matching_and_edge_case_summaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    _write_code_health_artifact(
        tmp_path,
        filename="code-health-20260413T090000Z-old.json",
        resolved_base_ref="other-base",
        resolved_head_ref="head-sha",
    )
    _write_code_health_artifact(
        tmp_path,
        filename="code-health-20260413T100000Z-match.json",
        resolved_base_ref="merge-base-sha",
        resolved_head_ref="head-sha",
        compared_files=4,
        flagged_files=4,
        files=[
            {
                "path": "a.py",
                "worsened_metrics": ["statement_count"],
                "delta": {"statement_count": 1},
            },
            {
                "path": "b.py",
                "worsened_metrics": ["max_member_lines"],
                "delta": {"max_member_lines": 2},
            },
            {
                "path": "c.py",
                "worsened_metrics": ["callable_count"],
                "delta": {"callable_count": 3},
            },
            {
                "path": "d.py",
                "worsened_metrics": ["statement_count"],
                "delta": {"statement_count": 4},
            },
        ],
    )

    artifact_path, summary = code_health_prompt_module.load_code_health_prompt_context(
        repo_root=tmp_path,
        resolved_base_ref="merge-base-sha",
        resolved_head_ref="head-sha",
    )

    assert artifact_path == "ai/eval/results/code-health-20260413T100000Z-match.json"
    assert summary is not None
    assert "Compared tracked Python files: 4; flagged regressions: 4." in summary
    assert "1 more flagged file(s) omitted from the prompt summary." in summary
    assert code_health_prompt_module.load_code_health_prompt_context(
        repo_root=tmp_path,
        resolved_base_ref="missing-base",
        resolved_head_ref="head-sha",
    ) == (None, None)
    assert (
        code_health_prompt_module._render_code_health_summary({"summary": None})
        == "Changed-file code-health artifact was present, but its summary was unreadable."
    )
    assert (
        "No tracked Python files were included"
        in code_health_prompt_module._render_code_health_summary(
            {"summary": {"compared_files": 0, "flagged_files": 0}}
        )
    )
    assert (
        "No structural regressions were flagged"
        in code_health_prompt_module._render_code_health_summary(
            {"summary": {"compared_files": 2, "flagged_files": 0}}
        )
    )
    assert (
        "Flagged file details were unavailable."
        in code_health_prompt_module._render_code_health_summary(
            {"summary": {"compared_files": 1, "flagged_files": 1}, "files": None}
        )
    )
    assert code_health_prompt_module._worsened_metrics({"worsened_metrics": "not-a-list"}) == []
    assert code_health_prompt_module._signed_delta("bad") == "n/a"
    assert (
        code_health_prompt_module.augment_review_instructions(
            None,
            artifact_path="ai/eval/results/code-health.json",
            summary="Compared tracked Python files: 1; flagged regressions: 0.",
        )
        is not None
    )
    merged_instructions = code_health_prompt_module.augment_review_instructions(
        "Focus on contract drift.",
        artifact_path=None,
        summary="Compared tracked Python files: 1; flagged regressions: 0.",
    )
    assert merged_instructions is not None
    assert merged_instructions.startswith("Focus on contract drift.")
    assert "Changed-file code-health artifact:" not in merged_instructions
    assert not code_health_prompt_module._matches_refs(
        payload=None,
        resolved_base_ref="merge-base-sha",
        resolved_head_ref="head-sha",
    )
    assert not code_health_prompt_module._matches_refs(
        payload={"format_version": "wrong"},
        resolved_base_ref="merge-base-sha",
        resolved_head_ref="head-sha",
    )
    assert not code_health_prompt_module._matches_refs(
        payload={"format_version": "code-health.v1", "comparison": None},
        resolved_base_ref="merge-base-sha",
        resolved_head_ref="head-sha",
    )

    invalid_path = tmp_path / "ai" / "eval" / "results" / "code-health-invalid.json"
    invalid_path.write_text("{not-json\n", encoding="utf-8")
    assert code_health_prompt_module._load_json(invalid_path) is None
    seen_match = {"count": 0}

    def flaky_load_json(path: Path) -> dict[str, object] | None:
        if not path.name.endswith("match.json"):
            return None
        seen_match["count"] += 1
        if seen_match["count"] == 1:
            return {
                "format_version": "code-health.v1",
                "comparison": {
                    "resolved_base_ref": "merge-base-sha",
                    "resolved_head_ref": "head-sha",
                },
            }
        return None

    monkeypatch.setattr(code_health_prompt_module, "_load_json", flaky_load_json)
    assert code_health_prompt_module.load_code_health_prompt_context(
        repo_root=tmp_path,
        resolved_base_ref="merge-base-sha",
        resolved_head_ref="head-sha",
    ) == (None, None)


def test_resolve_review_instructions_skips_code_health_lookup_when_git_refs_fail() -> None:
    def fake_run_git(args: list[str]) -> object:
        mapping = {
            ("rev-parse", "--verify", "HEAD"): _completed(["git", *args], returncode=1),
            ("merge-base", "main", "HEAD"): _completed(["git", *args], returncode=1),
        }
        return mapping[tuple(args)]

    artifact_path, instructions = code_health_prompt_module.resolve_review_instructions(
        repo_root=Path("/tmp/repo"),
        base_branch="main",
        instructions="Focus on contract drift.",
        run_git=fake_run_git,
    )

    assert artifact_path is None
    assert instructions == "Focus on contract drift."
