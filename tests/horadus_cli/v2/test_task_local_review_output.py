from __future__ import annotations

from pathlib import Path

import pytest

from tools.horadus.python.horadus_workflow import (
    _task_workflow_local_review_output as local_review_output_module,
)
from tools.horadus.python.horadus_workflow._task_workflow_local_review_models import (
    LocalReviewContext,
)

pytestmark = pytest.mark.unit


def _review_context() -> LocalReviewContext:
    return LocalReviewContext(
        current_branch="codex/task-369-slop-aware-local-review",
        task_id="TASK-369",
        base_branch="main",
        review_target_kind="branch_diff",
        review_target_value="main...HEAD",
        diff_text="diff --git a/foo.py b/foo.py\n+line\n",
        diff_stat=" foo.py | 1 +\n",
        changed_files=["foo.py"],
        working_tree_dirty=False,
    )


def test_build_configuration_lines_renders_stable_output_contract() -> None:
    lines = local_review_output_module.build_configuration_lines(
        context=_review_context(),
        selected_provider="claude",
        selection_source="default",
        provider_order=["claude", "codex", "gemini"],
        instructions="Focus on contract drift.",
        save_raw_output=True,
        usefulness="pending",
        code_health_artifact_path="ai/eval/results/code-health.json",
    )

    assert lines == [
        "Local review configuration:",
        "- provider: claude (source=default)",
        "- provider order: claude, codex, gemini",
        "- base branch: main",
        "- target: main...HEAD",
        "- provider timeout: 180s",
        "- changed-file code-health: ai/eval/results/code-health.json",
        "- instructions supplied: yes",
        "- usefulness: pending",
        "- raw output: keep",
    ]


def test_prepare_review_run_returns_provider_order_instructions_and_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_attempt_calls: list[tuple[str, str, bool]] = []

    def fake_provider_attempt_order(
        selected_provider: str,
        *,
        selection_source: str,
        allow_provider_fallback: bool,
    ) -> list[str]:
        provider_attempt_calls.append(
            (selected_provider, selection_source, allow_provider_fallback)
        )
        return ["claude", "codex"]

    def fake_resolve_review_instructions(**_: object) -> tuple[str | None, str | None]:
        return (
            "ai/eval/results/code-health.json",
            "Focus on hotspot growth.\n\nChanged-file code-health summary:",
        )

    monkeypatch.setattr(
        local_review_output_module,
        "resolve_review_instructions",
        fake_resolve_review_instructions,
    )

    provider_order, effective_instructions, lines = local_review_output_module.prepare_review_run(
        context=_review_context(),
        selected_provider="claude",
        selection_source="default",
        allow_provider_fallback=True,
        provider_attempt_order=fake_provider_attempt_order,
        instructions="Focus on hotspot growth.",
        save_raw_output=False,
        usefulness="useful",
        repo_root=Path("/tmp/repo"),
        run_git=lambda _args: None,
    )

    assert provider_attempt_calls == [("claude", "default", True)]
    assert provider_order == ["claude", "codex"]
    assert effective_instructions == "Focus on hotspot growth.\n\nChanged-file code-health summary:"
    assert lines == [
        "Local review configuration:",
        "- provider: claude (source=default)",
        "- provider order: claude, codex",
        "- base branch: main",
        "- target: main...HEAD",
        "- provider timeout: 180s",
        "- changed-file code-health: ai/eval/results/code-health.json",
        "- instructions supplied: yes",
        "- usefulness: useful",
        "- raw output: discard on success",
    ]
