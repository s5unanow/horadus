from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, cast

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_ledgers as ledgers
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode


@dataclass(slots=True)
class LocalGateStep:
    name: str
    command: str


@dataclass(slots=True)
class TaskPullRequest:
    number: int
    url: str
    state: str
    is_draft: bool
    head_ref_name: str
    head_ref_oid: str | None
    merge_commit_oid: str | None
    check_state: str


@dataclass(slots=True)
class TaskLifecycleSnapshot:
    task_id: str
    current_branch: str
    branch_name: str | None
    local_branch_names: list[str]
    remote_branch_names: list[str]
    remote_branch_exists: bool
    working_tree_clean: bool
    pr: TaskPullRequest | None
    local_main_sha: str | None
    remote_main_sha: str | None
    local_main_synced: bool | None
    merge_commit_available_locally: bool | None
    merge_commit_on_main: bool | None
    lifecycle_state: str
    strict_complete: bool


def _task_closure_blocker_lines(closure_state: task_repo.TaskClosureState) -> list[str]:
    lines: list[str] = []
    if closure_state.present_in_backlog:
        lines.append("- tasks/BACKLOG.md still contains the task as open.")
    if closure_state.present_in_active_sprint:
        lines.append("- tasks/CURRENT_SPRINT.md still lists the task under Active Tasks:")
        lines.extend(f"  {line}" for line in closure_state.active_sprint_lines)
    if not closure_state.present_in_completed:
        lines.append("- tasks/COMPLETED.md is missing the compact completion entry.")
    if not closure_state.present_in_closed_archive:
        lines.append("- archive/closed_tasks/*.md is missing the full archived task body.")
    return lines


def _git_file_text_at_ref(
    *, git_ref: str, relative_path: str, config: shared.FinishConfig
) -> tuple[bool, str]:
    result = shared._run_command([config.git_bin, "show", f"{git_ref}:{relative_path}"])
    if result.returncode != 0:
        return (False, "")
    return (True, result.stdout)


def _task_closure_state_for_ref(
    *, task_id: str, git_ref: str, config: shared.FinishConfig
) -> task_repo.TaskClosureState:
    normalized = task_repo.normalize_task_id(task_id)
    backlog_exists, backlog_text = _git_file_text_at_ref(
        git_ref=git_ref,
        relative_path="tasks/BACKLOG.md",
        config=config,
    )
    sprint_exists, sprint_text = _git_file_text_at_ref(
        git_ref=git_ref,
        relative_path="tasks/CURRENT_SPRINT.md",
        config=config,
    )
    completed_exists, completed_text = _git_file_text_at_ref(
        git_ref=git_ref,
        relative_path="tasks/COMPLETED.md",
        config=config,
    )

    present_in_backlog = (
        backlog_exists
        and __import__("re").search(
            rf"^###\s+{__import__('re').escape(normalized)}:\s+",
            backlog_text,
            __import__("re").MULTILINE,
        )
        is not None
    )

    active_sprint_lines: list[str] = []
    if sprint_exists:
        try:
            active_body = ledgers._extract_h2_section_body(sprint_text, "Active Tasks")
        except ValueError:
            active_body = ""
        active_pattern = __import__("re").compile(
            rf"^-\s+`{__import__('re').escape(normalized)}`(?:\s|$)"
        )
        active_sprint_lines = [
            line.strip()
            for line in active_body.splitlines()
            if active_pattern.match(line.strip()) is not None
        ]

    present_in_completed = (
        completed_exists
        and __import__("re").search(
            rf"^-\s+{__import__('re').escape(normalized)}:\s+.+?\s+✅(?:\s|$)",
            completed_text,
            __import__("re").MULTILINE,
        )
        is not None
    )

    archive_listing_result = shared._run_command(
        [config.git_bin, "ls-tree", "-r", "--name-only", git_ref, "archive/closed_tasks"]
    )
    archive_paths = [
        line.strip()
        for line in archive_listing_result.stdout.splitlines()
        if line.strip().endswith(".md")
    ]
    closed_archive_path: str | None = None
    for archive_path in archive_paths:
        archive_exists, archive_text = _git_file_text_at_ref(
            git_ref=git_ref,
            relative_path=archive_path,
            config=config,
        )
        if not archive_exists:
            continue
        if (
            __import__("re").search(
                rf"^###\s+{__import__('re').escape(normalized)}:\s+",
                archive_text,
                __import__("re").MULTILINE,
            )
            is not None
        ):
            closed_archive_path = archive_path
            break

    return task_repo.TaskClosureState(
        task_id=normalized,
        present_in_backlog=present_in_backlog,
        active_sprint_lines=active_sprint_lines,
        present_in_completed=present_in_completed,
        present_in_closed_archive=closed_archive_path is not None,
        closed_archive_path=closed_archive_path,
    )


def _pre_merge_task_closure_blocker(
    task_id: str,
    *,
    branch_name: str | None = None,
    config: shared.FinishConfig | None = None,
) -> tuple[str, dict[str, Any], list[str]] | None:
    closure_state = (
        _task_closure_state_for_ref(task_id=task_id, git_ref=branch_name, config=config)
        if branch_name is not None and config is not None
        else shared._compat_attr("task_closure_state", task_repo)(task_id)
    )
    if closure_state.ready_for_merge:
        return None
    return (
        "primary task closure state is not present on the PR head.",
        {"task_closure": asdict(closure_state)},
        _task_closure_blocker_lines(closure_state),
    )


def _find_task_pull_request(
    *, task_id: str, config: shared.FinishConfig
) -> tuple[int, dict[str, object], list[str]] | TaskPullRequest | None:
    search_result = shared._run_command(
        [
            config.gh_bin,
            "pr",
            "list",
            "--state",
            "all",
            "--search",
            f"Primary-Task: {task_id} in:body",
            "--limit",
            "20",
            "--json",
            "number",
        ]
    )
    if search_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to query GitHub pull requests."],
        )

    search_payload = json.loads(search_result.stdout or "[]")
    if not isinstance(search_payload, list) or not search_payload:
        return None

    pr_number = max(
        int(entry.get("number", 0))
        for entry in search_payload
        if isinstance(entry, dict) and entry.get("number") is not None
    )
    pr_result = shared._run_command(
        [
            config.gh_bin,
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,url,state,isDraft,headRefName,headRefOid,mergeCommit,statusCheckRollup",
        ]
    )
    if pr_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id, "pr_number": pr_number},
            ["Task lifecycle failed.", f"Unable to read GitHub PR #{pr_number}."],
        )

    payload = json.loads(pr_result.stdout or "{}")
    merge_commit = payload.get("mergeCommit")
    merge_commit_oid = None
    if isinstance(merge_commit, dict):
        raw_oid = merge_commit.get("oid")
        if raw_oid:
            merge_commit_oid = str(raw_oid)
    return TaskPullRequest(
        number=int(payload.get("number", pr_number)),
        url=str(payload.get("url") or ""),
        state=str(payload.get("state") or ""),
        is_draft=bool(payload.get("isDraft")),
        head_ref_name=str(payload.get("headRefName") or ""),
        head_ref_oid=str(payload.get("headRefOid") or "") or None,
        merge_commit_oid=merge_commit_oid,
        check_state=shared._check_rollup_state(payload.get("statusCheckRollup")),
    )


def task_lifecycle_state(snapshot: TaskLifecycleSnapshot) -> str:
    if snapshot.pr is not None:
        if snapshot.pr.state == "MERGED":
            if (
                snapshot.current_branch in {"main", "HEAD"}
                and snapshot.working_tree_clean
                and snapshot.local_main_synced
                and snapshot.merge_commit_on_main
            ):
                return "local-main-synced"
            return "merged"
        if snapshot.pr.state == "OPEN":
            if not snapshot.pr.is_draft and snapshot.pr.check_state == "pass":
                return "ci-green"
            return "pr-open"

    if snapshot.remote_branch_exists:
        return "pushed"
    return "local-only"


def resolve_task_lifecycle(
    task_input: str | None, *, config: shared.FinishConfig
) -> tuple[int, dict[str, object], list[str]] | TaskLifecycleSnapshot:
    branch_result = shared._run_command([config.git_bin, "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {},
            ["Task lifecycle failed.", "Unable to determine current branch."],
        )

    current_branch = branch_result.stdout.strip()
    if task_input is None:
        if current_branch == "HEAD":
            return (
                ExitCode.VALIDATION_ERROR,
                {"current_branch": current_branch},
                [
                    "Task lifecycle failed.",
                    "A task id is required when running from detached HEAD.",
                ],
            )
        inferred_task_id = shared._task_id_from_branch_name(current_branch)
        if inferred_task_id is None:
            return (
                ExitCode.VALIDATION_ERROR,
                {"current_branch": current_branch},
                [
                    "Task lifecycle failed.",
                    "A task id is required when the current branch is not a canonical task branch.",
                ],
            )
        task_id = inferred_task_id
    else:
        try:
            task_id = task_repo.normalize_task_id(task_input)
        except ValueError as exc:
            return (ExitCode.VALIDATION_ERROR, {}, [str(exc)])

    branch_pattern = shared._task_branch_pattern(task_id)
    local_branch_result = shared._run_command([config.git_bin, "branch", "--list", branch_pattern])
    if local_branch_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to inspect local task branches."],
        )
    local_branch_names = shared._parse_git_branch_lines(local_branch_result.stdout)

    remote_branch_result = shared._run_command(
        [config.git_bin, "ls-remote", "--heads", "origin", branch_pattern]
    )
    if remote_branch_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to inspect remote task branches."],
        )
    remote_branch_names = shared._parse_remote_branch_lines(remote_branch_result.stdout)

    pr_result = _find_task_pull_request(task_id=task_id, config=config)
    if isinstance(pr_result, tuple):
        return pr_result
    pr = pr_result

    current_branch_task_id = shared._task_id_from_branch_name(current_branch)
    branch_name = None
    if current_branch_task_id == task_id:
        branch_name = current_branch
    elif pr is not None and pr.head_ref_name:
        branch_name = pr.head_ref_name
    elif local_branch_names:
        branch_name = local_branch_names[0]
    elif remote_branch_names:
        branch_name = remote_branch_names[0]

    if branch_name is None and pr is None:
        return (
            ExitCode.NOT_FOUND,
            {"task_id": task_id},
            [f"No local, remote, or PR lifecycle state found for {task_id}."],
        )

    status_result = shared._run_command([config.git_bin, "status", "--porcelain"])
    if status_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to inspect working tree state."],
        )
    working_tree_clean = not status_result.stdout.strip()

    fetch_main_result = shared._run_command([config.git_bin, "fetch", "origin", "main", "--quiet"])
    if fetch_main_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to refresh origin/main before verification."],
        )

    local_main_result = shared._run_command([config.git_bin, "rev-parse", "main"])
    remote_main_result = shared._run_command([config.git_bin, "rev-parse", "origin/main"])
    local_main_sha = local_main_result.stdout.strip() if local_main_result.returncode == 0 else None
    remote_main_sha = (
        remote_main_result.stdout.strip() if remote_main_result.returncode == 0 else None
    )
    local_main_synced = None
    if local_main_sha and remote_main_sha:
        local_main_synced = local_main_sha == remote_main_sha

    merge_commit_available_locally = None
    merge_commit_on_main = None
    if pr is not None and pr.merge_commit_oid:
        merge_commit_available_locally = (
            shared._run_command([config.git_bin, "cat-file", "-e", pr.merge_commit_oid]).returncode
            == 0
        )
        merge_commit_on_main = (
            merge_commit_available_locally
            and shared._run_command(
                [config.git_bin, "merge-base", "--is-ancestor", pr.merge_commit_oid, "main"]
            ).returncode
            == 0
        )

    remote_branch_exists = (
        branch_name in remote_branch_names if branch_name else bool(remote_branch_names)
    )
    snapshot = TaskLifecycleSnapshot(
        task_id=task_id,
        current_branch=current_branch,
        branch_name=branch_name,
        local_branch_names=local_branch_names,
        remote_branch_names=remote_branch_names,
        remote_branch_exists=remote_branch_exists,
        working_tree_clean=working_tree_clean,
        pr=pr,
        local_main_sha=local_main_sha,
        remote_main_sha=remote_main_sha,
        local_main_synced=local_main_synced,
        merge_commit_available_locally=merge_commit_available_locally,
        merge_commit_on_main=merge_commit_on_main,
        lifecycle_state="",
        strict_complete=False,
    )
    snapshot.lifecycle_state = task_lifecycle_state(snapshot)
    snapshot.strict_complete = snapshot.lifecycle_state == "local-main-synced"
    return snapshot


def full_local_gate_steps() -> list[LocalGateStep]:
    uv_bin = shlex.quote(shared.getenv("UV_BIN") or "uv")
    return [
        LocalGateStep(
            name="check-tracked-artifacts", command="./scripts/check_no_tracked_artifacts.sh"
        ),
        LocalGateStep(
            name="docs-freshness",
            command=f"{uv_bin} run --no-sync python scripts/check_docs_freshness.py",
        ),
        LocalGateStep(
            name="code-shape",
            command=f"{uv_bin} run --no-sync python scripts/check_code_shape.py",
        ),
        LocalGateStep(
            name="ruff-format-check",
            command=f"{uv_bin} run --no-sync ruff format src/ tools/ tests/ --check",
        ),
        LocalGateStep(
            name="ruff-check", command=f"{uv_bin} run --no-sync ruff check src/ tools/ tests/"
        ),
        LocalGateStep(
            name="mypy", command=f"{uv_bin} run --no-sync mypy src/ tools/horadus/python"
        ),
        LocalGateStep(
            name="validate-taxonomy",
            command=(
                f"{uv_bin} run --no-sync horadus eval validate-taxonomy "
                "--gold-set ai/eval/gold_set.jsonl "
                "--trend-config-dir config/trends "
                "--output-dir ai/eval/results "
                "--max-items 200 "
                "--tier1-trend-mode subset "
                "--signal-type-mode warn "
                "--unknown-trend-mode warn"
            ),
        ),
        LocalGateStep(name="pytest-unit-cov", command="./scripts/run_unit_coverage_gate.sh"),
        LocalGateStep(name="secret-scan", command="./scripts/run_secret_scan.sh"),
        LocalGateStep(
            name="bandit",
            command=f"{uv_bin} run --no-sync bandit -c pyproject.toml -r src/ tools/horadus/python",
        ),
        LocalGateStep(name="dependency-audit", command="./scripts/run_dependency_audit.sh"),
        LocalGateStep(name="lockfile-check", command=f"{uv_bin} lock --check"),
        LocalGateStep(name="integration-docker", command="./scripts/test_integration_docker.sh"),
        LocalGateStep(
            name="build-package",
            command=(
                "rm -rf dist build *.egg-info && "
                f"{uv_bin} run --no-sync python -m build --no-isolation && "
                f"{uv_bin} run --no-sync twine check dist/*"
            ),
        ),
    ]


def local_gate_data(*, full: bool, dry_run: bool) -> tuple[int, dict[str, object], list[str]]:
    if not full:
        return (
            ExitCode.VALIDATION_ERROR,
            {"full": False},
            [
                "Local gate selection failed.",
                "Use `horadus tasks local-gate --full` for the canonical post-task local gate.",
            ],
        )

    if shared._ensure_command_available(shared.getenv("UV_BIN") or "uv") is None:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_command": shared.getenv("UV_BIN") or "uv"},
            ["Local gate failed: uv is required to run the canonical full local gate."],
        )

    steps = full_local_gate_steps()
    lines = [
        "Running canonical full local gate:",
        *[f"- {step.name}: {step.command}" for step in steps],
    ]
    if dry_run:
        lines.append("Dry run: validated the canonical step list without executing it.")
        return (
            ExitCode.OK,
            {"mode": "full", "dry_run": True, "steps": [asdict(step) for step in steps]},
            lines,
        )

    progress_lines = ["Running canonical full local gate:"]
    for index, step in enumerate(steps, start=1):
        progress_lines.append(f"[{index}/{len(steps)}] RUN {step.name}")
        if step.name == "integration-docker":
            docker_readiness = shared.ensure_docker_ready(
                reason="the integration-docker local gate step"
            )
            progress_lines.extend(docker_readiness.lines)
            if not docker_readiness.ready:
                return (
                    ExitCode.ENVIRONMENT_ERROR,
                    {
                        "mode": "full",
                        "failed_step": step.name,
                        "command": step.command,
                        "steps": [asdict(item) for item in steps],
                        "docker_ready": False,
                    },
                    [
                        *progress_lines,
                        "Local gate failed because Docker is not ready for the integration step.",
                    ],
                )
        result = shared._run_shell(step.command)
        if result.returncode != 0:
            output_lines = shared._summarize_output_lines(shared._output_lines(result))
            return (
                ExitCode.ENVIRONMENT_ERROR,
                {
                    "mode": "full",
                    "failed_step": step.name,
                    "command": step.command,
                    "steps": [asdict(item) for item in steps],
                },
                [
                    *progress_lines,
                    f"Local gate failed at step `{step.name}`.",
                    f"Command: {step.command}",
                    *output_lines,
                ],
            )
        progress_lines.append(f"[{index}/{len(steps)}] PASS {step.name}")

    progress_lines.append("Full local gate passed.")
    return (
        ExitCode.OK,
        {"mode": "full", "dry_run": False, "steps": [asdict(step) for step in steps]},
        progress_lines,
    )


def task_lifecycle_data(
    task_input: str | None, *, strict: bool, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
    try:
        config = shared._finish_config(enforce_review_timeout_override_policy=False)
    except ValueError as exc:
        return (ExitCode.ENVIRONMENT_ERROR, {}, [str(exc)])

    for command_name in (config.gh_bin, config.git_bin):
        if shared._ensure_command_available(command_name) is None:
            return (
                ExitCode.ENVIRONMENT_ERROR,
                {"missing_command": command_name},
                [f"Task lifecycle failed: missing required command '{command_name}'."],
            )

    resolve_task_lifecycle_fn = cast(
        "Callable[..., tuple[int, dict[str, object], list[str]] | TaskLifecycleSnapshot]",
        shared._compat_attr("resolve_task_lifecycle", sys.modules[__name__]),
    )
    task_closure_state_fn = cast(
        "Callable[[str], task_repo.TaskClosureState]",
        shared._compat_attr("task_closure_state", task_repo),
    )
    snapshot = resolve_task_lifecycle_fn(task_input, config=config)
    if not isinstance(snapshot, TaskLifecycleSnapshot):
        return snapshot
    closure_state = task_closure_state_fn(snapshot.task_id)
    snapshot.lifecycle_state = task_lifecycle_state(snapshot)
    snapshot.strict_complete = (
        snapshot.lifecycle_state == "local-main-synced" and closure_state.ready_for_merge
    )

    lines = [
        f"Task lifecycle: {snapshot.task_id}",
        f"- state: {snapshot.lifecycle_state}",
        f"- current branch: {snapshot.current_branch}",
        f"- working tree clean: {'yes' if snapshot.working_tree_clean else 'no'}",
    ]
    if snapshot.branch_name:
        lines.append(f"- task branch: {snapshot.branch_name}")
    if snapshot.pr is None:
        lines.append("- PR: none")
    else:
        lines.append(
            f"- PR: {snapshot.pr.url} ({snapshot.pr.state}{' draft' if snapshot.pr.is_draft else ''})"
        )
        lines.append(f"- checks: {snapshot.pr.check_state}")
        if snapshot.pr.merge_commit_oid:
            lines.append(f"- merge commit: {snapshot.pr.merge_commit_oid}")
    if snapshot.local_main_synced is not None:
        lines.append(f"- local main synced: {'yes' if snapshot.local_main_synced else 'no'}")
    if snapshot.merge_commit_on_main is not None:
        lines.append(
            "- local main contains merge commit: "
            f"{'yes' if snapshot.merge_commit_on_main else 'no'}"
        )
    lines.append(f"- closure backlog open: {'yes' if closure_state.present_in_backlog else 'no'}")
    lines.append(
        f"- closure active sprint open: {'yes' if closure_state.present_in_active_sprint else 'no'}"
    )
    lines.append(
        f"- closure completed ledger: {'yes' if closure_state.present_in_completed else 'no'}"
    )
    lines.append(
        f"- closure archived body: {'yes' if closure_state.present_in_closed_archive else 'no'}"
    )
    lines.append(f"- strict complete: {'yes' if snapshot.strict_complete else 'no'}")
    if dry_run:
        lines.append("Dry run: lifecycle inspection is read-only; returned live state.")

    exit_code = ExitCode.OK
    if strict and not snapshot.strict_complete:
        exit_code = ExitCode.VALIDATION_ERROR
        if not closure_state.ready_for_merge:
            lines.extend(_task_closure_blocker_lines(closure_state))
        lines.append(
            "Strict verification failed: repo-policy completion requires state `local-main-synced` "
            "with the task removed from live ledgers and recorded in tasks/COMPLETED.md plus "
            "archive/closed_tasks/."
        )

    return (exit_code, {**asdict(snapshot), "task_closure": asdict(closure_state)}, lines)


def handle_lifecycle(args: Any) -> CommandResult:
    try:
        task_input = task_repo.normalize_task_id(args.task_id) if args.task_id is not None else None
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = task_lifecycle_data(
        task_input,
        strict=bool(getattr(args, "strict", False)),
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_local_gate(args: Any) -> CommandResult:
    exit_code, data, lines = local_gate_data(full=bool(args.full), dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "LocalGateStep",
    "TaskLifecycleSnapshot",
    "TaskPullRequest",
    "_find_task_pull_request",
    "_git_file_text_at_ref",
    "_pre_merge_task_closure_blocker",
    "_task_closure_blocker_lines",
    "_task_closure_state_for_ref",
    "full_local_gate_steps",
    "handle_lifecycle",
    "handle_local_gate",
    "local_gate_data",
    "resolve_task_lifecycle",
    "task_lifecycle_data",
    "task_lifecycle_state",
]
