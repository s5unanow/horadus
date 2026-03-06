"""Unit tests for scripts/check_pr_review_gate.py."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_pr_review_gate.py"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_gate(
    *, env: dict[str, str], args: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        ["python", str(SCRIPT_PATH), *(args or [])],
        cwd=REPO_ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_review_gate_passes_when_current_head_review_has_no_comments(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  repo)
    echo '{"nameWithOwner":"example/repo"}'
    ;;
  pr)
    echo '{"number":215,"headRefOid":"head-sha-215","url":"https://example.invalid/pr/215"}'
    ;;
  api)
    if [[ "${2:-}" == "repos/example/repo/pulls/215/reviews" ]]; then
      echo '[{"id":501,"commit_id":"head-sha-215","user":{"login":"chatgpt-codex-connector[bot]"}}]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/pulls/215/comments" ]]; then
      echo '[]'
      exit 0
    fi
    exit 1
    ;;
  *)
    exit 1
    ;;
esac
""",
    )

    result = _run_gate(
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        args=["--pr-url", "https://example.invalid/pr/215", "--timeout-seconds", "0"],
    )
    assert result.returncode == 0
    assert "review gate passed" in result.stdout


def test_review_gate_fails_when_current_head_review_has_comments(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  repo)
    echo '{"nameWithOwner":"example/repo"}'
    ;;
  pr)
    echo '{"number":215,"headRefOid":"head-sha-215","url":"https://example.invalid/pr/215"}'
    ;;
  api)
    if [[ "${2:-}" == "repos/example/repo/pulls/215/reviews" ]]; then
      echo '[{"id":502,"commit_id":"head-sha-215","user":{"login":"chatgpt-codex-connector[bot]"}}]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/pulls/215/comments" ]]; then
      echo '[{"pull_request_review_id":502,"user":{"login":"chatgpt-codex-connector[bot]"},"path":"scripts/finish_task_pr.sh","line":80,"html_url":"https://example.invalid/comment/1","body":"Please address this before merge."}]'
      exit 0
    fi
    exit 1
    ;;
  *)
    exit 1
    ;;
esac
""",
    )

    result = _run_gate(
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        args=["--pr-url", "https://example.invalid/pr/215", "--timeout-seconds", "0"],
    )
    assert result.returncode == 2
    assert "actionable current-head review comments found" in result.stdout
    assert "scripts/finish_task_pr.sh:80" in result.stdout


def test_review_gate_allows_timeout_when_no_review_arrives(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  repo)
    echo '{"nameWithOwner":"example/repo"}'
    ;;
  pr)
    echo '{"number":215,"headRefOid":"head-sha-215","url":"https://example.invalid/pr/215"}'
    ;;
  api)
    if [[ "${2:-}" == "repos/example/repo/pulls/215/reviews" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/pulls/215/comments" ]]; then
      echo '[]'
      exit 0
    fi
    exit 1
    ;;
  *)
    exit 1
    ;;
esac
""",
    )

    result = _run_gate(
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        args=["--pr-url", "https://example.invalid/pr/215", "--timeout-seconds", "0"],
    )
    assert result.returncode == 0
    assert "review gate timeout" in result.stdout
    assert "timeout policy=allow" in result.stdout
