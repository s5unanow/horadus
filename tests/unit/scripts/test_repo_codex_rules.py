from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_FILE = REPO_ROOT / "codex" / "rules" / "default.rules"
RULES_README = REPO_ROOT / "codex" / "README.md"


def test_repo_owned_codex_rules_baseline_covers_autopilot_prefixes() -> None:
    rules = RULES_FILE.read_text(encoding="utf-8")

    assert 'pattern = ["uv", "run", "--no-sync", "horadus", "tasks", "preflight"]' in rules
    assert 'pattern = ["uv", "run", "--no-sync", "horadus", "tasks", "eligibility"]' in rules
    assert 'pattern = ["uv", "run", "--no-sync", "horadus", "tasks", "safe-start"]' in rules
    assert 'pattern = ["uv", "run", "--no-sync", "horadus", "tasks", "finish"]' in rules
    assert 'pattern = ["uv", "run", "--no-sync", "horadus", "tasks", "automation-lock"]' in rules
    assert "/Users/s5una/.codex/automations/horadus-sprint-autopilot/lock" in rules
    assert "automation-lock lock --path /tmp/lock" in rules
    assert 'pattern = ["uv", "run", "--no-sync", "horadus"]' not in rules


def test_repo_owned_codex_rules_baseline_covers_git_prefixes() -> None:
    rules = RULES_FILE.read_text(encoding="utf-8")

    assert 'pattern = ["git", "status"]' in rules
    assert 'pattern = ["git", "rev-parse"]' in rules
    assert 'pattern = ["git", "fetch"]' in rules
    assert 'pattern = ["git", "show-ref"]' in rules
    assert 'pattern = ["git", "ls-remote"]' in rules
    assert 'pattern = ["git", "switch"]' in rules
    assert 'pattern = ["git", "pull", "--ff-only"]' in rules
    assert 'pattern = ["git", "cat-file"]' in rules
    assert 'pattern = ["git", "branch"]' in rules
    assert 'pattern = ["git", "push", "origin"]' in rules
    assert 'pattern = ["git", "push", "-u", "origin"]' in rules
    assert 'pattern = ["git", "push", "--set-upstream", "origin"]' in rules


def test_repo_owned_codex_rules_baseline_covers_gh_and_forbidden_prefixes() -> None:
    rules = RULES_FILE.read_text(encoding="utf-8")

    assert 'pattern = ["gh", "pr"]' in rules
    assert 'pattern = ["gh", "repo"]' in rules
    assert 'pattern = ["gh", "api"]' in rules
    assert 'pattern = ["git", "push", "origin", "main"]' in rules
    assert 'pattern = ["git", "push", "--force"]' in rules
    assert 'pattern = ["gh", "api", "--method", "PATCH"]' in rules
    assert 'decision = "forbidden"' in rules


def test_repo_owned_codex_rules_readme_documents_local_activation() -> None:
    readme = RULES_README.read_text(encoding="utf-8")

    assert "codex/rules/default.rules" in readme
    assert "~/.codex/rules/default.rules" in readme
    assert "restart Codex" in readme
    assert "repo file as the canonical reviewed baseline" in readme
