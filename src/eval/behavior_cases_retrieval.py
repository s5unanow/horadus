"""Deterministic behavior cases for RFC-001 retrieval/context-pack contracts."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, cast

from src.eval.behavior_types import BehaviorEvalCaseDefinition

_LIVE_TASK_ID = "TASK-951"
_ARCHIVED_TASK_ID = "TASK-952"
_ARCHIVE_PATH = "archive/closed_tasks/2026-Q2.md"
_RETRIEVAL_MODE = "implement"
_RETRIEVAL_PHASE = "phase-1-cli-first"
_LIVE_EXCLUDED_SOURCES = {
    "README.md",
    "archive/",
    "local or hosted retrieval index",
    "ops/skills/",
    "policy-document front matter",
}
_ARCHIVED_EXCLUDED_SOURCES = {
    "README.md",
    "archive/closed_tasks/* except requested task",
    "local or hosted retrieval index",
    "ops/skills/",
    "policy-document front matter",
}


def retrieval_behavior_case_definitions() -> tuple[BehaviorEvalCaseDefinition, ...]:
    """Return deterministic retrieval/context-pack behavior cases."""

    return _RETRIEVAL_BEHAVIOR_CASE_DEFINITIONS


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _eval_live_vs_archived_context_sources() -> dict[str, Any]:
    with TemporaryDirectory() as tmpdir:
        repo_root = _seed_retrieval_repo(Path(tmpdir))
        live_payload = _run_context_pack(repo_root=repo_root, task_id=_LIVE_TASK_ID)
        archived_payload = _run_context_pack(
            repo_root=repo_root,
            task_id=_ARCHIVED_TASK_ID,
            include_archive=True,
        )

    live_included_paths = _included_paths(live_payload)
    live_excluded_sources = _excluded_sources(live_payload)
    archived_excluded_sources = _excluded_sources(archived_payload)
    archived_commands = cast("list[str]", archived_payload["workflow"]["commands"])
    _require(
        live_excluded_sources == _LIVE_EXCLUDED_SOURCES,
        "Live implement mode excluded an unexpected source set",
    )
    _require(
        all(not path.startswith("archive/") for path in live_included_paths),
        "Live implement mode included archived task history by default",
    )
    _require(
        archived_payload["retrieval_sources"]["included"][0]["path"] == _ARCHIVE_PATH,
        "Archived implement mode did not use the requested archive task body as its primary source",
    )
    _require(
        archived_excluded_sources == _ARCHIVED_EXCLUDED_SOURCES,
        "Archived implement mode did not scope archive access to the requested task",
    )
    _require(
        any(
            command.startswith(f"uv run --no-sync horadus tasks context-pack {_ARCHIVED_TASK_ID}")
            and "--include-archive" in command
            and "--mode implement --format json" in command
            for command in archived_commands
        ),
        "Archived implement mode did not propagate the archive-scoped workflow command",
    )

    return {
        "retrieval_mode": _RETRIEVAL_MODE,
        "retrieval_phase": _RETRIEVAL_PHASE,
        "authoritative_source_basis": _authoritative_source_basis(live_payload),
        "live_included_paths": live_included_paths,
        "live_excluded_sources": sorted(live_excluded_sources),
        "archived_primary_source": archived_payload["retrieval_sources"]["included"][0]["path"],
        "archived_excluded_sources": sorted(archived_excluded_sources),
    }


def _eval_minimal_context_basis() -> dict[str, Any]:
    with TemporaryDirectory() as tmpdir:
        repo_root = _seed_retrieval_repo(Path(tmpdir))
        payload = _run_context_pack(repo_root=repo_root, task_id=_LIVE_TASK_ID)

    included_paths = _included_paths(payload)
    expected_paths = [
        "tasks/BACKLOG.md",
        "tasks/CURRENT_SPRINT.md",
        "tasks/specs/951-retrieval-live-fixture.md",
        "tasks/exec_plans/TASK-951.md",
        "docs/ARCHITECTURE.md",
        "docs/DATA_MODEL.md",
    ]
    excluded_sources = _excluded_sources(payload)
    selected_spec_paths = cast(
        "list[str]",
        payload["retrieval_sources"]["task_spec_resolution"]["selected_paths"],
    )
    _require(
        included_paths == expected_paths,
        "Implement mode included sources outside the minimal authoritative retrieval set",
    )
    _require(
        selected_spec_paths == ["tasks/specs/951-retrieval-live-fixture.md"],
        "Implement mode did not resolve the canonical task spec deterministically",
    )
    _require(
        payload["planning_gates"]["authoritative_artifact_path"] == "tasks/exec_plans/TASK-951.md",
        "Implement mode did not surface the authoritative exec plan",
    )
    _require(
        excluded_sources == _LIVE_EXCLUDED_SOURCES,
        "Implement mode excluded an unexpected source set",
    )

    return {
        "retrieval_mode": _RETRIEVAL_MODE,
        "retrieval_phase": _RETRIEVAL_PHASE,
        "authoritative_source_basis": _authoritative_source_basis(payload),
        "included_paths": included_paths,
        "included_path_count": len(included_paths),
        "selected_spec_paths": selected_spec_paths,
        "authoritative_artifact_path": payload["planning_gates"]["authoritative_artifact_path"],
        "excluded_sources": sorted(excluded_sources),
    }


def _authoritative_source_basis(payload: dict[str, Any]) -> dict[str, object]:
    included = cast("list[dict[str, object]]", payload["retrieval_sources"]["included"])
    orientation_paths = [
        str(source["path"])
        for source in included
        if source.get("reason") == "compact orientation metadata"
    ]
    return {
        "primary_task_definition": included[0]["path"],
        "task_scoped_sprint_path": "tasks/CURRENT_SPRINT.md",
        "task_spec_paths": payload["retrieval_sources"]["task_spec_resolution"]["selected_paths"],
        "planning_artifact_path": payload["planning_gates"]["authoritative_artifact_path"],
        "orientation_paths": orientation_paths,
        "policy_registry_id": payload["policy"]["legacy_policy_registry"]["registry_id"],
    }


def _included_paths(payload: dict[str, Any]) -> list[str]:
    return [
        str(source["path"])
        for source in cast("list[dict[str, object]]", payload["retrieval_sources"]["included"])
    ]


def _excluded_sources(payload: dict[str, Any]) -> set[str]:
    return {
        str(source["source"])
        for source in cast("list[dict[str, object]]", payload["retrieval_sources"]["excluded"])
    }


def _run_context_pack(
    *,
    repo_root: Path,
    task_id: str,
    include_archive: bool = False,
) -> dict[str, Any]:
    # Keep this path on the in-process CLI entry point so behavior evals stay
    # deterministic and fast while still exercising the real context-pack
    # contract. The argument names and repo_root patching intentionally mirror
    # `handle_context_pack` / `task_repo.repo_root` today.
    cli_task_repo_module = importlib.import_module("tools.horadus.python.horadus_cli.task_repo")
    task_commands_module = importlib.import_module(
        "tools.horadus.python.horadus_cli.task_workflow_core"
    )
    workflow_task_repo_module = importlib.import_module(
        "tools.horadus.python.horadus_workflow.task_repo"
    )
    with _patched_repo_root(
        repo_root=repo_root,
        cli_task_repo_module=cli_task_repo_module,
        task_commands_module=task_commands_module,
        workflow_task_repo_module=workflow_task_repo_module,
    ):
        result = task_commands_module.handle_context_pack(
            SimpleNamespace(
                task_id=task_id,
                mode=_RETRIEVAL_MODE,
                output_format="json",
                include_archive=include_archive,
            )
        )
    _require(
        result.exit_code == task_commands_module.ExitCode.OK,
        f"context-pack failed for {task_id}: {result.error_lines}",
    )
    data = result.data
    _require(isinstance(data, dict), f"context-pack returned no payload for {task_id}")
    return cast("dict[str, Any]", data)


@contextmanager
def _patched_repo_root(
    *,
    repo_root: Path,
    cli_task_repo_module: Any,
    task_commands_module: Any,
    workflow_task_repo_module: Any,
) -> Iterator[None]:
    original_cli_repo_root = cli_task_repo_module.repo_root
    original_workflow_repo_root = workflow_task_repo_module.repo_root
    missing = object()
    try:
        original_task_commands_repo_root = task_commands_module.repo_root
    except AttributeError:
        original_task_commands_repo_root = missing

    def repo_root_factory() -> Path:
        return repo_root

    # These evals execute serially and patch the shared CLI repo-root lookup in
    # place so the in-process context-pack entrypoint reads from the fixture
    # repository instead of the live checkout.
    cli_task_repo_module.repo_root = repo_root_factory
    task_commands_module.repo_root = repo_root_factory
    workflow_task_repo_module.repo_root = repo_root_factory
    try:
        yield
    finally:
        cli_task_repo_module.repo_root = original_cli_repo_root
        if original_task_commands_repo_root is missing:
            delattr(task_commands_module, "repo_root")
        else:
            task_commands_module.repo_root = original_task_commands_repo_root
        workflow_task_repo_module.repo_root = original_workflow_repo_root


def _seed_retrieval_repo(repo_root: Path) -> Path:
    tasks_dir = repo_root / "tasks"
    docs_dir = repo_root / "docs"
    specs_dir = tasks_dir / "specs"
    exec_plans_dir = tasks_dir / "exec_plans"
    archived_dir = repo_root / "archive" / "closed_tasks"
    tests_dir = repo_root / "tests" / "horadus_cli" / "v2"
    rfc_dir = docs_dir / "rfc"

    for path in (specs_dir, exec_plans_dir, archived_dir, docs_dir, tests_dir, rfc_dir):
        path.mkdir(parents=True, exist_ok=True)

    _seed_retrieval_task_ledgers(tasks_dir)
    _seed_retrieval_support_files(repo_root=repo_root, docs_dir=docs_dir, rfc_dir=rfc_dir)
    _seed_retrieval_spec_and_plan_files(specs_dir=specs_dir, exec_plans_dir=exec_plans_dir)
    _seed_retrieval_archive_fixture(archived_dir=archived_dir)
    _write(tests_dir / "test_cli.py", ["def test_fixture() -> None:", "    pass"])
    return repo_root


def _seed_retrieval_task_ledgers(tasks_dir: Path) -> None:
    _write(
        tasks_dir / "BACKLOG.md",
        [
            "# Backlog",
            "",
            "## Open Task Ledger",
            "",
            "### TASK-951: Retrieval live fixture",
            "**Priority**: P1",
            "**Estimate**: 2h",
            "**Exec Plan**: Required (`tasks/exec_plans/TASK-951.md`)",
            "",
            "Exercise implement-mode retrieval behavior over live task context.",
            "",
            "**Files**: `tools/horadus/python/horadus_workflow/`, `tests/horadus_cli/v2/`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] implement mode keeps the retrieval basis minimal and authoritative",
            "",
            "---",
            "",
        ],
    )
    _write(
        tasks_dir / "CURRENT_SPRINT.md",
        [
            "# Current Sprint",
            "",
            "**Sprint Goal**: Exercise retrieval behavior fixtures.",
            "**Sprint Number**: 9",
            "**Sprint Dates**: 2026-04-21 to 2026-05-04",
            "",
            "## Active Tasks",
            "- `TASK-951` Retrieval live fixture",
            "",
            "## Completed This Sprint",
            "- `TASK-952` Retrieval archived fixture ✅",
            "",
            "## Telegram Launch Scope",
            "- launch_scope: excluded_until_task_080_done",
            "",
        ],
    )
    _write(
        tasks_dir / "COMPLETED.md",
        ["# Completed Tasks", "", "- TASK-952: Retrieval archived fixture ✅"],
    )


def _seed_retrieval_support_files(*, repo_root: Path, docs_dir: Path, rfc_dir: Path) -> None:
    _write(repo_root / "README.md", ["# README", "", "Pointer surface only."])
    _write(repo_root / "AGENTS.md", ["# AGENTS", "", "Canonical workflow policy fixture."])
    _write(docs_dir / "AGENT_RUNBOOK.md", ["# Agent Runbook", "", "Operator runbook fixture."])
    _write(docs_dir / "ARCHITECTURE.md", ["# Architecture", "", "Architecture fixture."])
    _write(docs_dir / "DATA_MODEL.md", ["# Data Model", "", "Data model fixture."])
    _write(
        rfc_dir / "001-agent-context-retrieval.md",
        ["# RFC-001", "", "Phase 1 CLI-first retrieval contract fixture."],
    )


def _seed_retrieval_spec_and_plan_files(*, specs_dir: Path, exec_plans_dir: Path) -> None:
    _write(
        specs_dir / "TEMPLATE.md",
        [
            "---",
            "task_id: TASK-XXX",
            "retrieval:",
            "  kind: task-spec",
            "  status: active",
            "  canonical: true",
            "  supersedes: []",
            "  superseded_by: null",
            "---",
            "",
            "# Template",
        ],
    )
    _write(
        specs_dir / "951-retrieval-live-fixture.md",
        [
            "---",
            "task_id: TASK-951",
            "retrieval:",
            "  kind: task-spec",
            "  status: active",
            "  canonical: true",
            "  supersedes: []",
            "  superseded_by: null",
            "---",
            "",
            "# TASK-951: Retrieval live fixture",
            "",
            "## Problem Statement",
            "",
            "Exercise deterministic spec-backed implement-mode retrieval.",
            "",
            "## Inputs",
            "",
            "- `tasks/BACKLOG.md`",
            "",
            "## Outputs",
            "",
            "- Minimal authoritative retrieval context",
            "",
            "## Non-Goals",
            "",
            "- Archive lookups by default",
            "",
            "**Planning Gates**: Required — retrieval fixture",
            "",
            "## Phase -1 / Pre-Implementation Gates",
            "",
            "- `Simplicity Gate`: Reuse the existing context-pack surface.",
            "- `Anti-Abstraction Gate`: Avoid extra retrieval wrappers.",
            "- `Integration-First Gate`:",
            "  - Validation target: `horadus tasks context-pack` implement mode",
            "  - Exercises: live retrieval basis selection.",
            "- `Code Shape Gate`: Not applicable — fixture-only task.",
            "- `Determinism Gate`: Triggered — retrieval basis must stay explicit.",
            "- `LLM Budget/Safety Gate`: Not applicable — no LLM calls.",
            "- `Observability Gate`: Triggered — retrieval provenance must be visible.",
        ],
    )
    _write(
        exec_plans_dir / "TASK-951.md",
        [
            "# TASK-951: Retrieval live fixture",
            "",
            "## Status",
            "",
            "- Owner: Fixture",
            "- Started: 2026-04-21",
            "- Current state: In progress",
            "- Planning Gates: Required — retrieval exec-plan fixture",
            "",
            "## Gate Outcomes / Waivers",
            "",
            "- Accepted design / smallest safe shape: use one exec plan file.",
            "- Rejected simpler alternative: omit the authoritative planning artifact.",
            "- First integration proof: implement-mode context-pack for TASK-951.",
            "- Hotspot Outcome: keep-flat-with-rationale — fixture task avoids allowlisted hotspots.",
            "- Waivers: none.",
        ],
    )


def _seed_retrieval_archive_fixture(*, archived_dir: Path) -> None:
    _write(
        archived_dir / "2026-Q2.md",
        [
            "# Closed Task Archive",
            "",
            "**Status**: Archived closed-task ledger (non-authoritative)",
            "**Quarter**: 2026-Q2",
            "",
            "---",
            "",
            "### TASK-952: Retrieval archived fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "",
            "Exercise archive-scoped implement-mode retrieval.",
            "",
            "**Files**: `tests/horadus_cli/v2/test_cli.py`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] archive-scoped retrieval works only when requested",
            "",
            "---",
            "",
        ],
    )


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_RETRIEVAL_BEHAVIOR_CASE_DEFINITIONS = (
    BehaviorEvalCaseDefinition(
        case_id="context-retrieval-live-vs-archive-scope",
        title="Implement mode prefers live sources and scopes archive access",
        suite="context-retrieval",
        tags=("retrieval", "context-pack", "implement", "archive"),
        production_contract=(
            "Implement-mode retrieval must use live task documents by default and "
            "only read archived task history through an explicit archive-scoped lookup."
        ),
        expected_behavior=(
            "Live implement mode excludes archive sources, while archived lookup "
            "keeps archive access scoped to the explicitly requested task."
        ),
        surface_paths=(
            "tools/horadus/python/horadus_workflow/task_workflow_query.py",
            "tools/horadus/python/horadus_workflow/task_workflow_context_pack_spec.py",
        ),
        runner=_eval_live_vs_archived_context_sources,
    ),
    BehaviorEvalCaseDefinition(
        case_id="context-retrieval-minimal-authoritative-basis",
        title="Implement mode keeps a minimal authoritative basis",
        suite="context-retrieval",
        tags=("retrieval", "context-pack", "implement", "minimality"),
        production_contract=(
            "Implement-mode retrieval must keep the context set phase-appropriate "
            "and minimal while still exposing the authoritative task, spec, "
            "planning, and orientation basis."
        ),
        expected_behavior=(
            "Included retrieval sources stay limited to the live task definition, "
            "task-scoped sprint slice, canonical spec, authoritative planning "
            "artifact, and compact orientation docs."
        ),
        surface_paths=(
            "tools/horadus/python/horadus_workflow/task_workflow_context_pack_implement.py",
            "tools/horadus/python/horadus_workflow/task_workflow_context_pack_implement_support.py",
            "tools/horadus/python/horadus_workflow/task_spec_resolution.py",
        ),
        runner=_eval_minimal_context_basis,
    ),
)
