from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_FILE = REPO_ROOT / "codex" / "rules" / "default.rules"
RULES_README = REPO_ROOT / "codex" / "README.md"


def test_repo_owned_codex_rules_baseline_covers_autopilot_prefixes() -> None:
    rules = RULES_FILE.read_text(encoding="utf-8")

    assert 'pattern = ["uv", "run", "--no-sync", "horadus"]' in rules
    assert 'pattern = ["git", "status"]' in rules
    assert 'pattern = ["git", "rev-parse"]' in rules
    assert 'pattern = ["git", "fetch"]' in rules
    assert 'pattern = ["git", "show-ref"]' in rules
    assert 'pattern = ["git", "ls-remote"]' in rules
    assert 'pattern = ["git", "switch"]' in rules
    assert 'pattern = ["git", "pull", "--ff-only"]' in rules
    assert 'pattern = ["git", "cat-file"]' in rules
    assert 'pattern = ["git", "branch"]' in rules
    assert 'pattern = ["git", "push"]' in rules
    assert 'pattern = ["gh", "pr"]' in rules
    assert 'pattern = ["gh", "repo"]' in rules
    assert 'pattern = ["gh", "api"]' in rules
    assert rules.count('decision = "allow"') == 14


def test_repo_owned_codex_rules_readme_documents_local_activation() -> None:
    readme = RULES_README.read_text(encoding="utf-8")

    assert "codex/rules/default.rules" in readme
    assert "~/.codex/rules/default.rules" in readme
    assert "restart Codex" in readme
    assert "repo file as the canonical reviewed baseline" in readme
