from __future__ import annotations

import os
import subprocess  # nosec B404

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


def _run_pr_scope_guard(
    *, branch_name: str, pr_title: str, pr_body: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PR_BRANCH"] = branch_name
    env["PR_TITLE"] = pr_title
    env["PR_BODY"] = pr_body
    return subprocess.run(  # nosec B603
        ["./scripts/check_pr_task_scope.sh"],
        cwd=shared._compat_attr("repo_root", task_repo)(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _branch_head_alignment_blocker(
    *, branch_name: str, pr_url: str, config: shared.FinishConfig
) -> tuple[str, dict[str, object], list[str]] | None:
    local_head_result = shared._run_command([config.git_bin, "rev-parse", branch_name])
    remote_head_result = shared._run_command(
        [config.git_bin, "ls-remote", "--heads", "origin", branch_name]
    )
    pr_head_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "headRefOid", "--jq", ".headRefOid"]
    )

    local_head = local_head_result.stdout.strip() if local_head_result.returncode == 0 else ""
    remote_head = ""
    if remote_head_result.returncode == 0:
        remote_head = remote_head_result.stdout.split(maxsplit=1)[0].strip()
    pr_head = pr_head_result.stdout.strip() if pr_head_result.returncode == 0 else ""

    if local_head and remote_head and pr_head and local_head == remote_head == pr_head:
        return None

    return (
        "task branch head, pushed branch head, and PR head are not aligned.",
        {
            "branch_name": branch_name,
            "local_branch_head": local_head or None,
            "remote_branch_head": remote_head or None,
            "pr_head": pr_head or None,
        },
        [
            f"- local branch head: {local_head or '<missing>'}",
            f"- remote branch head: {remote_head or '<missing>'}",
            f"- PR head: {pr_head or '<missing>'}",
        ],
    )


__all__ = ["_branch_head_alignment_blocker", "_run_pr_scope_guard"]
