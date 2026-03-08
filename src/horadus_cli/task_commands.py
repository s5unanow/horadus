from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.horadus_cli.result import CommandResult, ExitCode
from src.horadus_cli.task_repo import (
    active_section_text,
    backlog_path,
    current_sprint_path,
    normalize_task_id,
    parse_active_tasks,
    parse_human_blockers,
    repo_root,
    search_task_records,
    slugify_name,
    task_record,
)

TASK_BRANCH_PATTERN = re.compile(r"^codex/task-(?P<number>\d{3})-[a-z0-9][a-z0-9._-]*$")
DEFAULT_CHECKS_TIMEOUT_SECONDS = 1800
DEFAULT_CHECKS_POLL_SECONDS = 10
DEFAULT_REVIEW_TIMEOUT_SECONDS = 600
DEFAULT_REVIEW_POLL_SECONDS = 10
DEFAULT_REVIEW_BOT_LOGIN = "chatgpt-codex-connector[bot]"
DEFAULT_REVIEW_TIMEOUT_POLICY = "allow"


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        args,
        cwd=cwd or repo_root(),
        capture_output=True,
        text=True,
        check=check,
    )


def _run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        ["/bin/bash", "-lc", command],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )


@dataclass(slots=True)
class FinishContext:
    branch_name: str
    branch_task_id: str
    task_id: str


@dataclass(slots=True)
class FinishConfig:
    gh_bin: str
    git_bin: str
    python_bin: str
    checks_timeout_seconds: int
    checks_poll_seconds: int
    review_timeout_seconds: int
    review_poll_seconds: int
    review_bot_login: str
    review_timeout_policy: str


@dataclass(slots=True)
class LocalGateStep:
    name: str
    command: str


def _result_message(result: subprocess.CompletedProcess[str], fallback: str) -> str:
    return result.stderr.strip() or result.stdout.strip() or fallback


def _output_lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    text = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part is not None and part.strip()
    )
    return text.splitlines() if text else []


def _task_blocked(
    message: str,
    *,
    next_action: str,
    data: dict[str, Any] | None = None,
    exit_code: int = ExitCode.VALIDATION_ERROR,
    extra_lines: list[str] | None = None,
) -> tuple[int, dict[str, Any], list[str]]:
    lines = [f"Task finish blocked: {message}", f"Next action: {next_action}"]
    if extra_lines:
        lines.extend(extra_lines)
    return (exit_code, data or {}, lines)


def _read_int_env(name: str, default: int) -> int:
    raw = getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")
    return value


def _finish_config() -> FinishConfig:
    return FinishConfig(
        gh_bin=getenv("GH_BIN") or "gh",
        git_bin=getenv("GIT_BIN") or "git",
        python_bin=getenv("PYTHON_BIN") or sys.executable or "python3",
        checks_timeout_seconds=_read_int_env(
            "CHECKS_TIMEOUT_SECONDS", DEFAULT_CHECKS_TIMEOUT_SECONDS
        ),
        checks_poll_seconds=_read_int_env("CHECKS_POLL_SECONDS", DEFAULT_CHECKS_POLL_SECONDS),
        review_timeout_seconds=_read_int_env(
            "REVIEW_TIMEOUT_SECONDS", DEFAULT_REVIEW_TIMEOUT_SECONDS
        ),
        review_poll_seconds=_read_int_env("REVIEW_POLL_SECONDS", DEFAULT_REVIEW_POLL_SECONDS),
        review_bot_login=getenv("REVIEW_BOT_LOGIN") or DEFAULT_REVIEW_BOT_LOGIN,
        review_timeout_policy=getenv("REVIEW_TIMEOUT_POLICY") or DEFAULT_REVIEW_TIMEOUT_POLICY,
    )


def _ensure_command_available(command: str) -> str | None:
    return shutil.which(command)


def _resolve_finish_context(
    task_input: str | None, config: FinishConfig
) -> tuple[int, dict[str, Any], list[str]] | FinishContext:
    branch_result = _run_command([config.git_bin, "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode != 0:
        return _task_blocked(
            _result_message(branch_result, "Unable to determine current branch."),
            next_action="Resolve local git issues, then re-run `horadus tasks finish`.",
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    current_branch = branch_result.stdout.strip()
    if current_branch == "HEAD":
        return _task_blocked(
            "detached HEAD is not allowed.",
            next_action="Check out the task branch you want to finish, then re-run `horadus tasks finish`.",
            data={"current_branch": current_branch},
        )
    if current_branch == "main":
        return _task_blocked(
            "refusing to run on 'main'.",
            next_action="Switch to the task branch that owns the PR lifecycle you want to finish.",
            data={"current_branch": current_branch},
        )

    match = TASK_BRANCH_PATTERN.match(current_branch)
    if match is None:
        return _task_blocked(
            (
                "branch does not match the required task pattern "
                f"`codex/task-XXX-short-name`: {current_branch}"
            ),
            next_action="Switch to a canonical task branch before running `horadus tasks finish`.",
            data={"current_branch": current_branch},
        )

    branch_task_id = f"TASK-{match.group('number')}"
    requested_task_id = branch_task_id
    if task_input is not None:
        requested_task_id = normalize_task_id(task_input)
        if requested_task_id != branch_task_id:
            return _task_blocked(
                (f"branch {current_branch} maps to {branch_task_id}, not {requested_task_id}."),
                next_action=(
                    f"Run `horadus tasks finish {branch_task_id}` on this branch, or switch to the "
                    f"branch for {requested_task_id}."
                ),
                data={
                    "current_branch": current_branch,
                    "branch_task_id": branch_task_id,
                    "task_id": requested_task_id,
                },
            )

    status_result = _run_command([config.git_bin, "status", "--porcelain"])
    if status_result.returncode != 0:
        return _task_blocked(
            _result_message(status_result, "Unable to determine working tree state."),
            next_action="Resolve local git issues, then re-run `horadus tasks finish`.",
            data={"branch_name": current_branch, "task_id": requested_task_id},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    if status_result.stdout.strip():
        return _task_blocked(
            "working tree must be clean.",
            next_action=(
                "Commit or stash local changes, then re-run "
                f"`horadus tasks finish {requested_task_id}`."
            ),
            data={"branch_name": current_branch, "task_id": requested_task_id},
        )

    return FinishContext(
        branch_name=current_branch,
        branch_task_id=branch_task_id,
        task_id=requested_task_id,
    )


def _run_pr_scope_guard(*, branch_name: str, pr_body: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PR_BRANCH"] = branch_name
    env["PR_BODY"] = pr_body
    return subprocess.run(  # nosec B603
        ["./scripts/check_pr_task_scope.sh"],
        cwd=repo_root(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_review_gate(*, pr_url: str, config: FinishConfig) -> subprocess.CompletedProcess[str]:
    return _run_command(
        [
            config.python_bin,
            "./scripts/check_pr_review_gate.py",
            "--pr-url",
            pr_url,
            "--reviewer-login",
            config.review_bot_login,
            "--timeout-seconds",
            str(config.review_timeout_seconds),
            "--poll-seconds",
            str(config.review_poll_seconds),
            "--timeout-policy",
            config.review_timeout_policy,
        ]
    )


def _wait_for_required_checks(*, pr_url: str, config: FinishConfig) -> tuple[bool, list[str]]:
    deadline = time.time() + config.checks_timeout_seconds
    while True:
        result = _run_command([config.gh_bin, "pr", "checks", pr_url, "--required"])
        if result.returncode == 0:
            return (True, [])
        if time.time() >= deadline:
            return (
                False,
                _output_lines(result)
                or ["`gh pr checks --required` did not report success before timeout."],
            )
        if config.checks_poll_seconds:
            time.sleep(config.checks_poll_seconds)


def _wait_for_pr_state(
    *, pr_url: str, expected_state: str, config: FinishConfig
) -> tuple[bool, list[str]]:
    deadline = time.time() + config.checks_timeout_seconds
    while True:
        result = _run_command(
            [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
        )
        if result.returncode == 0 and result.stdout.strip() == expected_state:
            return (True, [])
        if time.time() >= deadline:
            return (
                False,
                _output_lines(result)
                or [f"PR did not reach state {expected_state!r} before timeout."],
            )
        if config.checks_poll_seconds:
            time.sleep(config.checks_poll_seconds)


def _summarize_output_lines(lines: list[str], *, max_lines: int = 80) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    head_count = 30
    tail_count = 30
    omitted = len(lines) - head_count - tail_count
    return [
        *lines[:head_count],
        f"... ({omitted} lines omitted) ...",
        *lines[-tail_count:],
    ]


def full_local_gate_steps() -> list[LocalGateStep]:
    uv_bin = getenv("UV_BIN") or "uv"
    return [
        LocalGateStep(
            name="check-tracked-artifacts",
            command="./scripts/check_no_tracked_artifacts.sh",
        ),
        LocalGateStep(
            name="docs-freshness",
            command=f"{uv_bin} run --no-sync python scripts/check_docs_freshness.py",
        ),
        LocalGateStep(
            name="ruff-format-check",
            command=f"{uv_bin} run --no-sync ruff format src/ tests/ --check",
        ),
        LocalGateStep(
            name="ruff-check",
            command=f"{uv_bin} run --no-sync ruff check src/ tests/",
        ),
        LocalGateStep(
            name="mypy",
            command=f"{uv_bin} run --no-sync mypy src/",
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
        LocalGateStep(
            name="pytest-unit-cov",
            command=(
                f"{uv_bin} run --no-sync pytest tests/unit/ -v "
                "--cov=src --cov-report=term-missing:skip-covered"
            ),
        ),
        LocalGateStep(
            name="bandit",
            command=f"{uv_bin} run --no-sync bandit -c pyproject.toml -r src/",
        ),
        LocalGateStep(
            name="lockfile-check",
            command=f"{uv_bin} lock --check",
        ),
        LocalGateStep(
            name="integration-docker",
            command="./scripts/test_integration_docker.sh",
        ),
        LocalGateStep(
            name="build-package",
            command="rm -rf dist build *.egg-info && uvx --from build pyproject-build && uvx twine check dist/*",
        ),
    ]


def local_gate_data(*, full: bool, dry_run: bool) -> tuple[int, dict[str, Any], list[str]]:
    if not full:
        return (
            ExitCode.VALIDATION_ERROR,
            {"full": False},
            [
                "Local gate selection failed.",
                "Use `horadus tasks local-gate --full` for the canonical post-task local gate.",
            ],
        )

    if _ensure_command_available(getenv("UV_BIN") or "uv") is None:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_command": getenv("UV_BIN") or "uv"},
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
            {
                "mode": "full",
                "dry_run": True,
                "steps": [asdict(step) for step in steps],
            },
            lines,
        )

    progress_lines = ["Running canonical full local gate:"]
    for index, step in enumerate(steps, start=1):
        progress_lines.append(f"[{index}/{len(steps)}] RUN {step.name}")
        result = _run_shell(step.command)
        if result.returncode != 0:
            output_lines = _summarize_output_lines(_output_lines(result))
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
        {
            "mode": "full",
            "dry_run": False,
            "steps": [asdict(step) for step in steps],
        },
        progress_lines,
    )


def _ensure_required_hooks() -> tuple[bool, list[str]]:
    hooks_dir = repo_root() / ".git" / "hooks"
    required = ("pre-commit", "pre-push", "commit-msg")
    missing: list[str] = []
    for hook_name in required:
        hook_path = hooks_dir / hook_name
        if (
            not hook_path.exists()
            or not hook_path.is_file()
            or not hook_path.stat().st_mode & 0o111
        ):
            missing.append(hook_name)
    return (not missing, missing)


def _open_task_prs() -> tuple[bool, list[str] | str]:
    result = _run_command(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--base",
            "main",
            "--author",
            "@me",
            "--search",
            "head:codex/task-",
            "--limit",
            "100",
            "--json",
            "number,headRefName,url",
        ]
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        return (False, message)
    import json

    payload = json.loads(result.stdout or "[]")
    open_prs = [
        f"#{entry['number']} {entry['headRefName']} {entry['url']}"
        for entry in payload
        if str(entry.get("headRefName", "")).startswith("codex/task-")
    ]
    return (True, open_prs)


def task_preflight_data() -> tuple[int, dict[str, Any], list[str]]:
    if getenv("SKIP_TASK_SEQUENCE_GUARD") == "1":
        data = {"skipped": True}
        return (ExitCode.OK, data, ["Task sequencing guard skipped (SKIP_TASK_SEQUENCE_GUARD=1)."])

    gh_path = shutil.which("gh")
    if gh_path is None:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_command": "gh"},
            ["Task sequencing guard failed.", "GitHub CLI (gh) is required for open-PR checks."],
        )

    hooks_ok, missing_hooks = _ensure_required_hooks()
    if not hooks_ok:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_hooks": missing_hooks},
            [
                "Task sequencing guard failed.",
                f"Required local git hooks are missing: {', '.join(missing_hooks)}.",
            ],
        )

    branch_result = _run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = branch_result.stdout.strip()
    if current_branch != "main":
        return (
            ExitCode.VALIDATION_ERROR,
            {"current_branch": current_branch},
            [
                "Task sequencing guard failed.",
                f"You must start tasks from 'main'. Current branch: {current_branch}",
            ],
        )

    status_result = _run_command(["git", "status", "--porcelain"])
    if status_result.stdout.strip():
        return (
            ExitCode.VALIDATION_ERROR,
            {"working_tree_clean": False},
            [
                "Task sequencing guard failed.",
                "Working tree must be clean before starting a new task branch.",
            ],
        )

    fetch_result = _run_command(["git", "fetch", "origin", "main", "--quiet"])
    if fetch_result.returncode != 0:
        message = fetch_result.stderr.strip() or fetch_result.stdout.strip() or "git fetch failed"
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"fetch_error": message},
            ["Task sequencing guard failed.", message],
        )

    local_sha = _run_command(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_sha = _run_command(["git", "rev-parse", "origin/main"]).stdout.strip()
    if local_sha != remote_sha:
        return (
            ExitCode.VALIDATION_ERROR,
            {"local_main_sha": local_sha, "remote_main_sha": remote_sha},
            ["Task sequencing guard failed.", "Local main is not synced to origin/main."],
        )

    if getenv("ALLOW_OPEN_TASK_PRS") != "1":
        ok, pr_result = _open_task_prs()
        if not ok:
            return (
                ExitCode.ENVIRONMENT_ERROR,
                {"open_pr_query_error": pr_result},
                ["Task sequencing guard failed.", "Unable to query open PRs via GitHub CLI."],
            )
        if pr_result:
            return (
                ExitCode.VALIDATION_ERROR,
                {"open_task_prs": pr_result},
                [
                    "Task sequencing guard failed.",
                    "Open non-merged task PR(s) already exist for current user:",
                    *list(pr_result),
                ],
            )

    return (
        ExitCode.OK,
        {
            "gh_path": gh_path,
            "working_tree_clean": True,
            "local_main_sha": local_sha,
            "remote_main_sha": remote_sha,
        },
        ["Task sequencing guard passed: main is clean/synced and no open task PRs."],
    )


def getenv(name: str) -> str | None:
    import os

    return os.environ.get(name)


def _preflight_result() -> CommandResult:
    exit_code, data, lines = task_preflight_data()
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def eligibility_data(task_input: str) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)
    sprint_file = Path(getenv("TASK_ELIGIBILITY_SPRINT_FILE") or current_sprint_path())
    if not sprint_file.exists():
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"sprint_file": str(sprint_file)},
            [f"Missing sprint file: {sprint_file}"],
        )

    try:
        _ = active_section_text(sprint_file)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {"sprint_file": str(sprint_file)}, [str(exc)])

    matched_task = next(
        (task for task in parse_active_tasks(sprint_file) if task.task_id == task_id), None
    )
    if matched_task is None:
        return (
            ExitCode.VALIDATION_ERROR,
            {"task_id": task_id, "sprint_file": str(sprint_file)},
            [f"{task_id} is not listed in Active Tasks ({sprint_file})"],
        )
    if matched_task.requires_human:
        return (
            ExitCode.VALIDATION_ERROR,
            {"task_id": task_id, "requires_human": True},
            [f"{task_id} is marked [REQUIRES_HUMAN] and is not eligible for autonomous start"],
        )

    preflight_override = getenv("TASK_ELIGIBILITY_PREFLIGHT_CMD")
    if preflight_override and preflight_override != "./scripts/check_task_start_preflight.sh":
        preflight_result = _run_shell(preflight_override)
        if preflight_result.returncode != 0:
            return (
                ExitCode.VALIDATION_ERROR,
                {"task_id": task_id, "preflight_cmd": preflight_override},
                [f"Task sequencing preflight failed for {task_id}."],
            )
    else:
        preflight_exit, preflight_data, preflight_lines = task_preflight_data()
        if preflight_exit != ExitCode.OK:
            return (
                preflight_exit,
                {"task_id": task_id, "preflight": preflight_data},
                [*preflight_lines, f"Task sequencing preflight failed for {task_id}."],
            )

    return (
        ExitCode.OK,
        {"task_id": task_id, "sprint_file": str(sprint_file), "requires_human": False},
        [f"Agent task eligibility passed: {task_id}"],
    )


def start_task_data(
    task_input: str, raw_name: str, *, dry_run: bool
) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)
    slug = slugify_name(raw_name)
    branch_name = f"codex/task-{task_id[5:]}-{slug}"

    preflight_exit, preflight_data, preflight_lines = task_preflight_data()
    if preflight_exit != ExitCode.OK:
        return (
            preflight_exit,
            {"branch_name": branch_name, "preflight": preflight_data},
            preflight_lines,
        )

    local_exists = (
        _run_command(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"]
        ).returncode
        == 0
    )
    if local_exists:
        return (
            ExitCode.VALIDATION_ERROR,
            {"branch_name": branch_name},
            [f"Branch already exists locally: {branch_name}"],
        )

    remote_exists = (
        _run_command(
            ["git", "ls-remote", "--exit-code", "--heads", "origin", branch_name]
        ).returncode
        == 0
    )
    if remote_exists:
        return (
            ExitCode.VALIDATION_ERROR,
            {"branch_name": branch_name},
            [f"Branch already exists on origin: {branch_name}"],
        )

    lines = ["Task sequencing guard passed: main is clean/synced and no open task PRs."]
    if dry_run:
        lines.append(f"Dry run: would create task branch {branch_name}")
        return (
            ExitCode.OK,
            {"task_id": task_id, "branch_name": branch_name, "dry_run": True},
            lines,
        )

    switch_result = _run_command(["git", "switch", "-c", branch_name])
    if switch_result.returncode != 0:
        message = (
            switch_result.stderr.strip() or switch_result.stdout.strip() or "git switch failed"
        )
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id, "branch_name": branch_name, "error": message},
            [message],
        )

    lines.extend(
        [
            f"Switched to a new branch '{branch_name}'",
            f"Created task branch: {branch_name}",
        ]
    )
    return (
        ExitCode.OK,
        {"task_id": task_id, "branch_name": branch_name, "dry_run": False},
        lines,
    )


def finish_task_data(
    task_input: str | None, *, dry_run: bool
) -> tuple[int, dict[str, Any], list[str]]:
    try:
        config = _finish_config()
    except ValueError as exc:
        return _task_blocked(
            str(exc),
            next_action="Fix the invalid environment override and re-run `horadus tasks finish`.",
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    for command_name in (config.gh_bin, config.git_bin, config.python_bin):
        if _ensure_command_available(command_name) is None:
            return _task_blocked(
                f"missing required command '{command_name}'.",
                next_action=f"Install or expose `{command_name}` on PATH, then re-run `horadus tasks finish`.",
                data={"missing_command": command_name},
                exit_code=ExitCode.ENVIRONMENT_ERROR,
            )

    context = _resolve_finish_context(task_input, config)
    if not isinstance(context, FinishContext):
        return context

    remote_branch_result = _run_command(
        [config.git_bin, "ls-remote", "--exit-code", "--heads", "origin", context.branch_name]
    )
    remote_branch_exists = remote_branch_result.returncode == 0

    pr_url_result = _run_command([config.gh_bin, "pr", "view", "--json", "url", "--jq", ".url"])
    pr_url = pr_url_result.stdout.strip()
    if pr_url_result.returncode != 0 or not pr_url:
        next_action = (
            f"Run `git push -u origin {context.branch_name}` and open a PR for {context.task_id}."
            if not remote_branch_exists
            else (
                f"Open a PR for `{context.branch_name}` with `Primary-Task: {context.task_id}` in the body, "
                "then re-run `horadus tasks finish`."
            )
        )
        return _task_blocked(
            f"unable to locate a PR for branch `{context.branch_name}`.",
            next_action=next_action,
            data={"task_id": context.task_id, "branch_name": context.branch_name},
        )

    pr_body_result = _run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "body", "--jq", ".body"]
    )
    if pr_body_result.returncode != 0:
        return _task_blocked(
            _result_message(pr_body_result, "Unable to read the PR body."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    scope_result = _run_pr_scope_guard(
        branch_name=context.branch_name, pr_body=pr_body_result.stdout
    )
    if scope_result.returncode != 0:
        return _task_blocked(
            "PR scope validation failed.",
            next_action=(
                f"Fix the PR body so it contains exactly `Primary-Task: {context.task_id}`, "
                "then re-run `horadus tasks finish`."
            ),
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            extra_lines=_output_lines(scope_result),
        )

    lines = [f"Finishing {context.task_id} from {context.branch_name}", f"PR: {pr_url}"]

    pr_state_result = _run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
    )
    if pr_state_result.returncode != 0:
        return _task_blocked(
            _result_message(pr_state_result, "Unable to determine PR state."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    pr_state = pr_state_result.stdout.strip()

    if pr_state != "MERGED" and not remote_branch_exists:
        return _task_blocked(
            f"branch `{context.branch_name}` is not pushed to origin.",
            next_action=f"Run `git push -u origin {context.branch_name}` and re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
        )

    draft_result = _run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "isDraft", "--jq", ".isDraft"]
    )
    if draft_result.returncode != 0:
        return _task_blocked(
            _result_message(draft_result, "Unable to determine PR draft status."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    if draft_result.stdout.strip() == "true":
        return _task_blocked(
            "PR is draft; refusing to merge.",
            next_action="Mark the PR ready for review, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
        )

    if dry_run:
        lines.append(
            "Dry run: scope and PR preconditions passed; would wait for checks, merge, and sync main."
        )
        return (
            ExitCode.OK,
            {
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "dry_run": True,
            },
            lines,
        )

    if pr_state == "MERGED":
        lines.append("PR already merged; skipping merge step.")
    else:
        lines.append(f"Waiting for PR checks to pass (timeout={config.checks_timeout_seconds}s)...")
        checks_ok, check_lines = _wait_for_required_checks(pr_url=pr_url, config=config)
        if not checks_ok:
            return _task_blocked(
                "required PR checks did not pass before timeout.",
                next_action="Inspect the failing required checks, fix them, and re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                extra_lines=check_lines,
            )

        lines.append(
            "Waiting for review gate "
            f"(reviewer={config.review_bot_login}, timeout={config.review_timeout_seconds}s)..."
        )
        review_result = _run_review_gate(pr_url=pr_url, config=config)
        if review_result.returncode != 0:
            return _task_blocked(
                "review gate did not pass.",
                next_action=(
                    "Address the current-head review feedback or reviewer timeout blocker, "
                    "then re-run `horadus tasks finish`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                exit_code=review_result.returncode,
                extra_lines=_output_lines(review_result),
            )
        lines.extend(_output_lines(review_result))

        lines.append("Merging PR (squash, delete branch)...")
        merge_result = _run_command(
            [config.gh_bin, "pr", "merge", pr_url, "--squash", "--delete-branch"]
        )
        if merge_result.returncode != 0:
            state_after_result = _run_command(
                [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
            )
            state_after = (
                state_after_result.stdout.strip() if state_after_result.returncode == 0 else ""
            )
            if state_after != "MERGED":
                merge_lines = _output_lines(merge_result)
                merge_message = "\n".join(merge_lines)
                if "--auto" in merge_message or "prohibits the merge" in merge_message:
                    lines.append(
                        "Base branch policy requires auto-merge; enabling auto-merge and waiting for merge completion."
                    )
                    auto_merge_result = _run_command(
                        [
                            config.gh_bin,
                            "pr",
                            "merge",
                            pr_url,
                            "--auto",
                            "--squash",
                            "--delete-branch",
                        ]
                    )
                    if auto_merge_result.returncode != 0:
                        auto_state_after_result = _run_command(
                            [
                                config.gh_bin,
                                "pr",
                                "view",
                                pr_url,
                                "--json",
                                "state",
                                "--jq",
                                ".state",
                            ]
                        )
                        auto_state_after = (
                            auto_state_after_result.stdout.strip()
                            if auto_state_after_result.returncode == 0
                            else ""
                        )
                        if auto_state_after != "MERGED":
                            return _task_blocked(
                                "merge failed.",
                                next_action="Resolve the merge blocker in GitHub, then re-run `horadus tasks finish`.",
                                data={
                                    "task_id": context.task_id,
                                    "branch_name": context.branch_name,
                                    "pr_url": pr_url,
                                },
                                exit_code=ExitCode.ENVIRONMENT_ERROR,
                                extra_lines=_output_lines(auto_merge_result),
                            )
                    merged_ok, merged_lines = _wait_for_pr_state(
                        pr_url=pr_url, expected_state="MERGED", config=config
                    )
                    if not merged_ok:
                        return _task_blocked(
                            "auto-merge did not complete before timeout.",
                            next_action="Wait for the PR to merge in GitHub, then re-run `horadus tasks finish`.",
                            data={
                                "task_id": context.task_id,
                                "branch_name": context.branch_name,
                                "pr_url": pr_url,
                            },
                            exit_code=ExitCode.ENVIRONMENT_ERROR,
                            extra_lines=merged_lines,
                        )
                else:
                    return _task_blocked(
                        "merge failed.",
                        next_action="Resolve the merge blocker in GitHub, then re-run `horadus tasks finish`.",
                        data={
                            "task_id": context.task_id,
                            "branch_name": context.branch_name,
                            "pr_url": pr_url,
                        },
                        exit_code=ExitCode.ENVIRONMENT_ERROR,
                        extra_lines=merge_lines,
                    )
            lines.append("Merge step reported failure, but PR is already MERGED; continuing.")

    merge_commit_result = _run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "mergeCommit", "--jq", ".mergeCommit.oid"]
    )
    merge_commit = merge_commit_result.stdout.strip()
    if merge_commit_result.returncode != 0 or not merge_commit or merge_commit == "null":
        return _task_blocked(
            "could not determine merge commit.",
            next_action="Inspect the merged PR state in GitHub, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    lines.append("Syncing main...")
    switch_main_result = _run_command([config.git_bin, "switch", "main"])
    if switch_main_result.returncode != 0:
        return _task_blocked(
            _result_message(switch_main_result, "Failed to switch to main."),
            next_action="Resolve the local git state and switch to `main`, then re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    pull_result = _run_command([config.git_bin, "pull", "--ff-only"])
    if pull_result.returncode != 0:
        return _task_blocked(
            _result_message(pull_result, "Failed to fast-forward local main."),
            next_action="Resolve the local `main` sync issue and re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    cat_file_result = _run_command([config.git_bin, "cat-file", "-e", merge_commit])
    if cat_file_result.returncode != 0:
        return _task_blocked(
            f"merge commit {merge_commit} is not available locally after syncing main.",
            next_action="Fetch/pull `main` successfully, then re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    branch_exists_result = _run_command(
        [config.git_bin, "show-ref", "--verify", f"refs/heads/{context.branch_name}"]
    )
    if branch_exists_result.returncode == 0:
        delete_branch_result = _run_command([config.git_bin, "branch", "-d", context.branch_name])
        if delete_branch_result.returncode != 0:
            return _task_blocked(
                f"merged branch `{context.branch_name}` still exists locally and could not be deleted.",
                next_action=f"Delete `{context.branch_name}` locally after syncing main, then re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                    "merge_commit": merge_commit,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=_output_lines(delete_branch_result),
            )

    lines.append(f"Task finish passed: merged {merge_commit} and synced main.")
    return (
        ExitCode.OK,
        {
            "task_id": context.task_id,
            "branch_name": context.branch_name,
            "pr_url": pr_url,
            "merge_commit": merge_commit,
            "dry_run": False,
        },
        lines,
    )


def _task_record_payload(record: Any, *, include_raw: bool = True) -> dict[str, Any]:
    payload = asdict(record)
    if not include_raw:
        payload.pop("raw_block", None)
    payload["backlog_path"] = str(backlog_path().relative_to(repo_root()))
    payload["current_sprint_path"] = str(current_sprint_path().relative_to(repo_root()))
    return payload


def handle_list_active(_args: Any) -> CommandResult:
    tasks = parse_active_tasks()
    active_task_ids = {task.task_id for task in tasks}
    blockers = parse_human_blockers(task_ids=active_task_ids)
    blockers_by_task = {blocker.task_id: blocker for blocker in blockers}
    overdue_blockers = [
        blocker
        for blocker in blockers
        if blocker.urgency is not None and blocker.urgency.is_overdue
    ]
    lines = ["Active tasks:"]
    for task in tasks:
        suffix = " [REQUIRES_HUMAN]" if task.requires_human else ""
        note = f" — {task.note}" if task.note else ""
        urgency_note = ""
        blocker = blockers_by_task.get(task.task_id)
        if blocker is not None and blocker.urgency is not None:
            if blocker.urgency.is_overdue:
                overdue_days = abs(blocker.urgency.days_until_next_action or 0)
                urgency_note = f" [OVERDUE by {overdue_days}d]"
            elif blocker.urgency.is_due_today:
                urgency_note = " [DUE TODAY]"
        lines.append(f"- {task.task_id}: {task.title}{suffix}{urgency_note}{note}")
    if overdue_blockers:
        lines.append(
            "- overdue_human_blockers="
            f"{len(overdue_blockers)} ({', '.join(blocker.task_id for blocker in overdue_blockers)})"
        )
    return CommandResult(
        lines=lines,
        data={
            "tasks": [asdict(task) for task in tasks],
            "human_blockers": [asdict(item) for item in blockers],
            "overdue_human_blockers": [asdict(item) for item in overdue_blockers],
        },
    )


def handle_show(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])

    record = task_record(task_id)
    if record is None:
        return CommandResult(
            exit_code=ExitCode.NOT_FOUND,
            error_lines=[f"{task_id} not found in tasks/BACKLOG.md"],
            data={"task_id": task_id},
        )

    lines = [
        f"# {record.task_id}: {record.title}",
        f"Status: {record.status}",
        f"Priority: {record.priority or 'unknown'}",
        f"Estimate: {record.estimate or 'unknown'}",
    ]
    if record.description:
        lines.append("Description:")
        lines.extend(f"- {item}" for item in record.description)
    if record.files:
        lines.append("Files:")
        lines.extend(f"- {item}" for item in record.files)
    if record.acceptance_criteria:
        lines.append("Acceptance Criteria:")
        lines.extend(record.acceptance_criteria)
    if record.spec_paths:
        lines.append("Specs:")
        lines.extend(f"- {item}" for item in record.spec_paths)
    return CommandResult(lines=lines, data=_task_record_payload(record))


def handle_search(args: Any) -> CommandResult:
    if args.limit is not None and args.limit < 1:
        return CommandResult(
            exit_code=ExitCode.VALIDATION_ERROR,
            error_lines=["--limit must be a positive integer"],
        )

    query = " ".join(args.query).strip()
    matches = search_task_records(query, status=args.status, limit=args.limit)
    lines = [f"Task search: {query}"]
    lines.append(
        f"- status={args.status}, limit={args.limit if args.limit is not None else 'none'}, "
        f"results={len(matches)}"
    )
    if not matches:
        lines.append("(no matches)")
    else:
        for record in matches:
            lines.append(
                f"- {record.task_id}: {record.title} [{record.status}] "
                f"(priority={record.priority or 'unknown'}, estimate={record.estimate or 'unknown'})"
            )
        if args.include_raw:
            for record in matches:
                lines.extend(["", f"## {record.task_id}", record.raw_block])
    return CommandResult(
        lines=lines,
        data={
            "query": query,
            "status_filter": args.status,
            "limit": args.limit,
            "include_raw": bool(args.include_raw),
            "matches": [
                _task_record_payload(item, include_raw=bool(args.include_raw)) for item in matches
            ],
        },
    )


def handle_context_pack(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])

    record = task_record(task_id)
    if record is None:
        return CommandResult(
            exit_code=ExitCode.NOT_FOUND,
            error_lines=[f"{task_id} not found in tasks/BACKLOG.md"],
            data={"task_id": task_id},
        )

    lines = [
        f"# Context Pack: {task_id}",
        "",
        "## Backlog Entry",
        record.raw_block,
        "",
        "## Sprint Status",
    ]
    lines.extend(record.sprint_lines or ["(not listed in current sprint)"])
    lines.extend(
        [
            "",
            "## Matching Spec",
        ]
    )
    lines.extend(record.spec_paths or ["(none)"])
    lines.extend(
        [
            "",
            "## Likely Code Areas",
        ]
    )
    lines.extend(record.files or ["(not specified in backlog entry)"])
    lines.extend(
        [
            "",
            "## Suggested Validation Commands",
            "make agent-check",
            "uv run --no-sync horadus tasks local-gate --full",
        ]
    )
    return CommandResult(
        lines=lines,
        data={
            "task": _task_record_payload(record),
            "sprint_lines": record.sprint_lines,
            "spec_paths": record.spec_paths,
            "suggested_validation_commands": [
                "make agent-check",
                "uv run --no-sync horadus tasks local-gate --full",
            ],
        },
    )


def handle_preflight(_args: Any) -> CommandResult:
    return _preflight_result()


def handle_eligibility(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = eligibility_data(task_id)
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_start(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = start_task_data(task_id, args.name, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_finish(args: Any) -> CommandResult:
    try:
        task_input = normalize_task_id(args.task_id) if args.task_id is not None else None
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = finish_task_data(task_input, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_local_gate(args: Any) -> CommandResult:
    exit_code, data, lines = local_gate_data(full=bool(args.full), dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def add_leaf_cli_options(parser: Any) -> None:
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default=argparse.SUPPRESS,
        help="Output format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Validate and describe the command without making changes.",
    )


def register_task_commands(subparsers: Any) -> None:
    tasks_parser = subparsers.add_parser("tasks", help="Repo task and sprint workflow helpers.")
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command")

    list_active_parser = tasks_subparsers.add_parser(
        "list-active",
        help="List active tasks from the current sprint.",
    )
    add_leaf_cli_options(list_active_parser)
    list_active_parser.set_defaults(handler=handle_list_active)

    show_parser = tasks_subparsers.add_parser("show", help="Show a backlog task record.")
    add_leaf_cli_options(show_parser)
    show_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    show_parser.set_defaults(handler=handle_show)

    search_parser = tasks_subparsers.add_parser("search", help="Search backlog tasks by text.")
    add_leaf_cli_options(search_parser)
    search_parser.add_argument("query", nargs="+", help="Query text.")
    search_parser.add_argument(
        "--status",
        choices=["active", "backlog", "completed", "all"],
        default="all",
        help="Filter search results by task status.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of results to return.",
    )
    search_parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include the raw backlog block for each matching task.",
    )
    search_parser.set_defaults(handler=handle_search)

    context_pack_parser = tasks_subparsers.add_parser(
        "context-pack",
        help="Show the task backlog/spec/sprint context pack.",
    )
    add_leaf_cli_options(context_pack_parser)
    context_pack_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    context_pack_parser.set_defaults(handler=handle_context_pack)

    preflight_parser = tasks_subparsers.add_parser(
        "preflight",
        help="Validate task-start sequencing preflight on main.",
    )
    add_leaf_cli_options(preflight_parser)
    preflight_parser.set_defaults(handler=handle_preflight)

    eligibility_parser = tasks_subparsers.add_parser(
        "eligibility",
        help="Validate whether a task can be started autonomously.",
    )
    add_leaf_cli_options(eligibility_parser)
    eligibility_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    eligibility_parser.set_defaults(handler=handle_eligibility)

    start_parser = tasks_subparsers.add_parser(
        "start",
        help="Start a task branch with sequencing guards.",
    )
    add_leaf_cli_options(start_parser)
    start_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    start_parser.add_argument("--name", required=True, help="Short branch suffix.")
    start_parser.set_defaults(handler=handle_start)

    finish_parser = tasks_subparsers.add_parser(
        "finish",
        help="Complete the current task PR lifecycle and sync local main.",
    )
    add_leaf_cli_options(finish_parser)
    finish_parser.add_argument(
        "task_id",
        nargs="?",
        help="Optional task id (TASK-XXX or XXX) to verify against the current task branch.",
    )
    finish_parser.set_defaults(handler=handle_finish)

    local_gate_parser = tasks_subparsers.add_parser(
        "local-gate",
        help="Run the canonical post-task local validation gate.",
    )
    add_leaf_cli_options(local_gate_parser)
    local_gate_parser.add_argument(
        "--full",
        action="store_true",
        help="Run the full CI-parity local gate.",
    )
    local_gate_parser.set_defaults(handler=handle_local_gate)
