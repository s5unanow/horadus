"""Unit tests for scripts/finish_task_pr.sh using gh/git shims."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "finish_task_pr.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_finish(*, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)

    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_finish_task_pr_happy_path(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    # Avoid high-entropy hex strings that trigger detect-secrets; this can be any
    # deterministic token because git/gh are shims in this test.
    merge_commit = "merge-commit-175"

    _write_executable(
        bin_dir / "git",
        f"""#!/usr/bin/env bash
set -euo pipefail
cmd="${{1:-}}"
shift || true
case "$cmd" in
  rev-parse)
    # rev-parse --abbrev-ref HEAD
    echo "${{GIT_BRANCH:-codex/task-175-task-finish}}"
    ;;
  status)
    # status --porcelain
    printf '%s' "${{GIT_STATUS_PORCELAIN:-}}"
    ;;
  switch)
    exit 0
    ;;
  pull)
    echo "Already up to date."
    ;;
  cat-file)
    # cat-file -e <sha>
    if [[ "${{2:-}}" != "{merge_commit}" ]]; then
      exit 1
    fi
    ;;
  *)
    exit 0
    ;;
esac
""",
    )

    _write_executable(
        bin_dir / "gh",
        f"""#!/usr/bin/env bash
set -euo pipefail
for arg in "$@"; do
  if [[ "$arg" == "--yes" ]]; then
    echo "unsupported flag: --yes" >&2
    exit 2
  fi
done
if [[ "${{1:-}}" != "pr" ]]; then
  exit 1
fi
sub="${{2:-}}"
shift 2 || true
case "$sub" in
  view)
    # Handle: gh pr view --json <field> --jq <expr>
    if [[ "$*" == *"--json url"* ]]; then
      echo "https://example.invalid/pr/175"
      exit 0
    fi
    if [[ "$*" == *"--json body"* ]]; then
      echo "## Primary Task"
      echo "Primary-Task: TASK-175"
      exit 0
    fi
    if [[ "$*" == *"--json isDraft"* ]]; then
      echo "false"
      exit 0
    fi
    if [[ "$*" == *"--json mergeCommit"* ]]; then
      # Require an explicit PR identifier for mergeCommit lookups to avoid
      # branch-context reliance after merge.
      if [[ "$*" != *"https://example.invalid/pr/175"* ]]; then
        echo "no pull requests found for branch \"main\"" >&2
        exit 1
      fi
      echo "{merge_commit}"
      exit 0
    fi
    exit 1
    ;;
  checks)
    exit "${{GH_CHECKS_EXIT_CODE:-0}}"
    ;;
  merge)
    exit 0
    ;;
  *)
    exit 1
    ;;
esac
""",
    )

    result = _run_finish(
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GIT_BRANCH": "codex/task-175-task-finish",
            "GIT_STATUS_PORCELAIN": "",
            "GH_CHECKS_EXIT_CODE": "0",
        }
    )

    assert result.returncode == 0
    assert "task-finish passed" in result.stdout


def test_finish_task_pr_refuses_main_branch(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _write_executable(
        bin_dir / "git",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "rev-parse" ]]; then
  echo "main"
  exit 0
fi
exit 0
""",
    )
    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
exit 0
""",
    )

    result = _run_finish(env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 1
    assert "refusing to run on 'main'" in result.stdout


def test_finish_task_pr_rejects_primary_task_mismatch(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _write_executable(
        bin_dir / "git",
        """#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
shift || true
case "$cmd" in
  rev-parse) echo "codex/task-175-task-finish" ;;
  status) printf '%s' "" ;;
  *) exit 0 ;;
esac
""",
    )

    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
set -euo pipefail
for arg in "$@"; do
  if [[ "$arg" == "--yes" ]]; then
    echo "unsupported flag: --yes" >&2
    exit 2
  fi
done
if [[ "${1:-}" != "pr" ]]; then exit 1; fi
sub="${2:-}"
shift 2 || true
case "$sub" in
  view)
    if [[ "$*" == *"--json url"* ]]; then
      echo "https://example.invalid/pr/175"
      exit 0
    fi
    if [[ "$*" == *"--json body"* ]]; then
      echo "Primary-Task: TASK-174"
      exit 0
    fi
    if [[ "$*" == *"--json url"* ]]; then
      echo "https://example.invalid/pr/175"
      exit 0
    fi
    if [[ "$*" == *"--json isDraft"* ]]; then
      echo "false"
      exit 0
    fi
    if [[ "$*" == *"--json mergeCommit"* ]]; then
      echo "deadbeef"
      exit 0
    fi
    exit 1
    ;;
  checks) exit 0 ;;
  merge) exit 0 ;;
  *) exit 1 ;;
esac
""",
    )

    result = _run_finish(env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 1
    assert "PR scope guard failed" in result.stdout


def test_finish_task_pr_fails_when_checks_fail(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _write_executable(
        bin_dir / "git",
        """#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
shift || true
case "$cmd" in
  rev-parse) echo "codex/task-175-task-finish" ;;
  status) printf '%s' "" ;;
  switch|pull) exit 0 ;;
  cat-file) exit 0 ;;
  *) exit 0 ;;
esac
""",
    )

    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
set -euo pipefail
for arg in "$@"; do
  if [[ "$arg" == "--yes" ]]; then
    echo "unsupported flag: --yes" >&2
    exit 2
  fi
done
if [[ "${1:-}" != "pr" ]]; then exit 1; fi
sub="${2:-}"
shift 2 || true
case "$sub" in
  view)
    if [[ "$*" == *"--json url"* ]]; then
      echo "https://example.invalid/pr/175"
      exit 0
    fi
    if [[ "$*" == *"--json body"* ]]; then
      echo "Primary-Task: TASK-175"
      exit 0
    fi
    if [[ "$*" == *"--json url"* ]]; then
      echo "https://example.invalid/pr/175"
      exit 0
    fi
    if [[ "$*" == *"--json isDraft"* ]]; then
      echo "false"
      exit 0
    fi
    if [[ "$*" == *"--json mergeCommit"* ]]; then
      echo "deadbeef"
      exit 0
    fi
    exit 1
    ;;
  checks) exit 1 ;;
  merge) exit 0 ;;
  *) exit 1 ;;
esac
""",
    )

    result = _run_finish(
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CHECKS_TIMEOUT_SECONDS": "1",
            "CHECKS_POLL_SECONDS": "0",
        }
    )
    assert result.returncode == 1
    assert "checks did not pass" in result.stdout
