from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

SUPPORTED_LOCAL_REVIEW_PROVIDERS: tuple[str, ...] = ("claude", "codex", "gemini")
VALID_LOCAL_REVIEW_USEFULNESS: tuple[str, ...] = (
    "pending",
    "follow-up-changes",
    "not-useful",
)
DEFAULT_LOCAL_REVIEW_PROVIDER = "claude"
DEFAULT_LOCAL_REVIEW_BASE_BRANCH = "main"
LOCAL_REVIEW_PROVIDER_ENV = "HORADUS_LOCAL_REVIEW_PROVIDER"
LOCAL_REVIEW_HARNESS_PATH = Path(".env.harness")
LOCAL_REVIEW_DIRECTORY = Path("artifacts/agent/local-review")
LOCAL_REVIEW_LOG_FILENAME = "entries.jsonl"
LOCAL_REVIEW_RUNS_DIRECTORY = LOCAL_REVIEW_DIRECTORY / "runs"
LOCAL_REVIEW_STATUS_PATTERN = re.compile(
    r"^HORADUS-LOCAL-REVIEW:\s*(?P<status>findings|no-findings)\s*$",
    re.IGNORECASE,
)
_PROVIDER_INTERFACE_KIND = {
    "claude": "prompt",
    "codex": "review",
    "gemini": "prompt",
}
_PROVIDER_BINARIES = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
}


@dataclass(slots=True)
class LocalReviewContext:
    current_branch: str
    task_id: str | None
    base_branch: str
    review_target_kind: str
    review_target_value: str
    diff_text: str
    diff_stat: str
    changed_files: list[str]
    working_tree_dirty: bool


@dataclass(slots=True)
class LocalReviewParsedOutput:
    findings_reported: bool
    review_body: str


@dataclass(slots=True)
class LocalReviewProviderRun:
    provider: str
    interface_kind: str
    command: list[str]
    prompt: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


def _local_review_log_path() -> Path:
    return task_repo.repo_root() / LOCAL_REVIEW_DIRECTORY / LOCAL_REVIEW_LOG_FILENAME


def _local_review_runs_dir() -> Path:
    return task_repo.repo_root() / LOCAL_REVIEW_RUNS_DIRECTORY


def _harness_value(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is not None and raw.strip():
        return raw.strip()
    env_path = task_repo.repo_root() / LOCAL_REVIEW_HARNESS_PATH
    if not env_path.exists():
        return None
    value = dotenv_values(env_path).get(name)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _resolve_provider_selection(
    explicit_provider: str | None,
) -> tuple[str, str] | tuple[int, dict[str, object], list[str]]:
    if explicit_provider is not None:
        return explicit_provider, "cli"

    configured_provider = _harness_value(LOCAL_REVIEW_PROVIDER_ENV)
    if configured_provider is None:
        return DEFAULT_LOCAL_REVIEW_PROVIDER, "default"

    provider = configured_provider.strip().lower()
    if provider not in SUPPORTED_LOCAL_REVIEW_PROVIDERS:
        return (
            ExitCode.VALIDATION_ERROR,
            {
                "configured_provider": configured_provider,
                "supported_providers": list(SUPPORTED_LOCAL_REVIEW_PROVIDERS),
            },
            [
                "Local review configuration failed.",
                f"{LOCAL_REVIEW_PROVIDER_ENV}={configured_provider!r} is unsupported.",
                "Supported providers: "
                + ", ".join(
                    f"`{provider_name}`" for provider_name in SUPPORTED_LOCAL_REVIEW_PROVIDERS
                ),
            ],
        )
    return provider, "env"


def _provider_attempt_order(
    primary_provider: str,
    *,
    selection_source: str,
    allow_provider_fallback: bool,
) -> list[str]:
    if selection_source == "cli" and not allow_provider_fallback:
        return [primary_provider]
    return [
        primary_provider,
        *[
            provider
            for provider in SUPPORTED_LOCAL_REVIEW_PROVIDERS
            if provider != primary_provider
        ],
    ]


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    git_bin = shared.getenv("GIT_BIN") or "git"
    return shared._run_command([git_bin, *args])


def _review_context(
    *,
    base_branch: str,
) -> LocalReviewContext | tuple[int, dict[str, object], list[str]]:
    branch_result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {},
            ["Local review failed: unable to determine the current branch."],
        )

    current_branch = branch_result.stdout.strip()
    if current_branch == "HEAD":
        return (
            ExitCode.VALIDATION_ERROR,
            {"current_branch": current_branch},
            [
                "Local review selection failed.",
                "A local review target requires a checked-out branch; detached HEAD is unsupported.",
            ],
        )

    base_result = _run_git(["rev-parse", "--verify", base_branch])
    if base_result.returncode != 0:
        return (
            ExitCode.VALIDATION_ERROR,
            {"base_branch": base_branch},
            [
                "Local review selection failed.",
                f"Base branch `{base_branch}` is not available locally.",
            ],
        )

    diff_result = _run_git(["diff", "--no-ext-diff", "--find-renames", f"{base_branch}...HEAD"])
    if diff_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"base_branch": base_branch, "current_branch": current_branch},
            [
                "Local review failed: unable to compute the branch diff.",
            ],
        )

    diff_text = diff_result.stdout.strip()
    if not diff_text:
        return (
            ExitCode.VALIDATION_ERROR,
            {
                "base_branch": base_branch,
                "current_branch": current_branch,
                "review_target_kind": "branch_diff",
                "review_target_value": f"{base_branch}...{current_branch}",
            },
            [
                "Local review selection failed.",
                f"No branch diff exists for `{base_branch}...{current_branch}`.",
            ],
        )

    diff_stat_result = _run_git(["diff", "--stat", "--no-ext-diff", f"{base_branch}...HEAD"])
    name_only_result = _run_git(["diff", "--name-only", "--no-ext-diff", f"{base_branch}...HEAD"])
    status_result = _run_git(["status", "--short"])
    changed_files = [line.strip() for line in name_only_result.stdout.splitlines() if line.strip()]
    task_id = shared._task_id_from_branch_name(current_branch)
    return LocalReviewContext(
        current_branch=current_branch,
        task_id=task_id,
        base_branch=base_branch,
        review_target_kind="branch_diff",
        review_target_value=f"{base_branch}...{current_branch}",
        diff_text=diff_text,
        diff_stat=diff_stat_result.stdout.strip(),
        changed_files=changed_files,
        working_tree_dirty=bool(status_result.stdout.strip()),
    )


def _render_prompt_contract(*, instructions: str | None) -> str:
    lines = [
        "Return the first non-empty line exactly as one of:",
        "- HORADUS-LOCAL-REVIEW: findings",
        "- HORADUS-LOCAL-REVIEW: no-findings",
        "After the marker line:",
        "- If there are findings, report concise bullets ordered by severity and include file paths when possible.",
        "- If there are no findings, write one short sentence only.",
        "Prioritize bugs, regressions, behavior changes, missing tests, and contract drift.",
    ]
    if instructions is not None and instructions.strip():
        lines.extend(["Additional review instructions:", instructions.strip()])
    return "\n".join(lines)


def _render_prompt_only_provider_prompt(
    *,
    context: LocalReviewContext,
    instructions: str | None,
) -> str:
    files_block = "\n".join(f"- {path}" for path in context.changed_files) or "- (none)"
    diff_stat = context.diff_stat or "(no diff stat available)"
    contract = _render_prompt_contract(instructions=instructions)
    task_line = context.task_id or "unknown"
    return (
        "You are running an opt-in local pre-push code review for the Horadus repository.\n"
        f"Task id: {task_line}\n"
        f"Base branch: {context.base_branch}\n"
        f"Current branch: {context.current_branch}\n"
        f"Review target: {context.review_target_value}\n"
        f"Working tree dirty: {'yes' if context.working_tree_dirty else 'no'}\n\n"
        f"{contract}\n\n"
        "Changed files:\n"
        f"{files_block}\n\n"
        "Diff stat:\n"
        f"{diff_stat}\n\n"
        "Git diff:\n"
        f"{context.diff_text}\n"
    )


def _render_codex_review_prompt(
    *,
    context: LocalReviewContext,
    instructions: str | None,
) -> str:
    task_line = context.task_id or "unknown"
    contract = _render_prompt_contract(instructions=instructions)
    return (
        "Review the current repository changes against the provided base branch.\n"
        f"Task id: {task_line}\n"
        f"Base branch: {context.base_branch}\n"
        f"Current branch: {context.current_branch}\n"
        f"Review target: {context.review_target_value}\n"
        f"Working tree dirty: {'yes' if context.working_tree_dirty else 'no'}\n\n"
        f"{contract}\n"
    )


def _provider_command(
    provider: str,
    *,
    context: LocalReviewContext,
    instructions: str | None,
) -> tuple[list[str], str]:
    if provider == "claude":
        prompt = _render_prompt_only_provider_prompt(context=context, instructions=instructions)
        return (
            [
                "claude",
                "--print",
                "--output-format",
                "text",
                "--permission-mode",
                "plan",
                prompt,
            ],
            prompt,
        )
    if provider == "gemini":
        prompt = _render_prompt_only_provider_prompt(context=context, instructions=instructions)
        return (
            [
                "gemini",
                "--prompt",
                prompt,
                "--approval-mode",
                "plan",
                "--output-format",
                "text",
            ],
            prompt,
        )
    prompt = _render_codex_review_prompt(context=context, instructions=instructions)
    return (
        [
            "codex",
            "exec",
            "review",
            "--base",
            context.base_branch,
            prompt,
        ],
        prompt,
    )


def _execute_provider(
    provider: str,
    *,
    context: LocalReviewContext,
    instructions: str | None,
) -> LocalReviewProviderRun:
    command, prompt = _provider_command(provider, context=context, instructions=instructions)
    started = time.monotonic()
    completed = subprocess.run(  # nosec B603
        command,
        cwd=task_repo.repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_seconds = time.monotonic() - started
    return LocalReviewProviderRun(
        provider=provider,
        interface_kind=_PROVIDER_INTERFACE_KIND[provider],
        command=command,
        prompt=prompt,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        duration_seconds=duration_seconds,
    )


def _parse_provider_output(output_text: str) -> LocalReviewParsedOutput | None:
    lines = output_text.splitlines()
    first_non_empty_index = None
    first_non_empty_line = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            first_non_empty_index = index
            first_non_empty_line = stripped
            break
    if first_non_empty_line is None:
        return None
    match = LOCAL_REVIEW_STATUS_PATTERN.match(first_non_empty_line)
    if match is None:
        return None
    remainder = (
        "\n".join(lines[first_non_empty_index + 1 :]).strip()
        if first_non_empty_index is not None
        else ""
    )
    return LocalReviewParsedOutput(
        findings_reported=match.group("status").lower() == "findings",
        review_body=remainder,
    )


def _write_raw_output(
    *,
    provider: str,
    stdout: str,
    stderr: str,
) -> Path:
    runs_dir = _local_review_runs_dir()
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    path = runs_dir / f"{timestamp}-{provider}.txt"
    path.write_text(
        "\n".join(
            [
                f"provider={provider}",
                "",
                "stdout:",
                stdout.rstrip(),
                "",
                "stderr:",
                stderr.rstrip(),
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    return path


def _append_local_review_entry(payload: dict[str, object]) -> None:
    log_path = _local_review_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def _entry_payload(
    *,
    context: LocalReviewContext,
    selection_source: str,
    attempted_provider: str,
    executed_provider: str | None,
    fallback_provider: str | None,
    instructions: str | None,
    outcome: str,
    duration_seconds: float,
    findings_reported: bool | None,
    usefulness: str,
    raw_output_path: Path | None,
) -> dict[str, object]:
    return {
        "timestamp": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "task_id": context.task_id,
        "executed_provider": executed_provider,
        "provider_selection_source": selection_source,
        "review_target_kind": context.review_target_kind,
        "review_target_value": context.review_target_value,
        "custom_instructions_supplied": bool(instructions and instructions.strip()),
        "run_outcome": outcome,
        "duration_seconds": round(duration_seconds, 3),
        "attempted_provider": attempted_provider,
        "fallback_provider": fallback_provider,
        "findings_reported": findings_reported,
        "follow_up_changes": usefulness == "follow-up-changes",
        "judged_not_useful": usefulness == "not-useful",
        "raw_output_path": (
            str(raw_output_path.relative_to(task_repo.repo_root()))
            if raw_output_path is not None
            else None
        ),
    }


def local_review_data(
    *,
    provider: str | None,
    base_branch: str,
    instructions: str | None,
    allow_provider_fallback: bool,
    save_raw_output: bool,
    usefulness: str,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    selection = _resolve_provider_selection(provider)
    if not isinstance(selection[0], str):
        return selection
    selected_provider, selection_source = selection

    context = _review_context(base_branch=base_branch)
    if not isinstance(context, LocalReviewContext):
        exit_code, data, lines = context
        fallback_provider = None
        payload = {
            **data,
            "attempted_provider": selected_provider,
            "provider_selection_source": selection_source,
        }
        return exit_code, payload, lines

    provider_order = _provider_attempt_order(
        selected_provider,
        selection_source=selection_source,
        allow_provider_fallback=allow_provider_fallback,
    )
    lines = [
        "Local review configuration:",
        f"- provider: {selected_provider} (source={selection_source})",
        f"- provider order: {', '.join(provider_order)}",
        f"- base branch: {context.base_branch}",
        f"- target: {context.review_target_value}",
        f"- instructions supplied: {'yes' if instructions and instructions.strip() else 'no'}",
        f"- usefulness: {usefulness}",
        f"- raw output: {'keep' if save_raw_output else 'discard on success'}",
    ]

    if dry_run:
        preview_commands = []
        for provider_name in provider_order:
            command, _prompt = _provider_command(
                provider_name,
                context=context,
                instructions=instructions,
            )
            preview_commands.append({"provider": provider_name, "command": command})
        lines.append("Dry run: validated the review target and provider command plan.")
        return (
            ExitCode.OK,
            {
                "provider": selected_provider,
                "provider_selection_source": selection_source,
                "provider_order": provider_order,
                "base_branch": context.base_branch,
                "current_branch": context.current_branch,
                "task_id": context.task_id,
                "review_target_kind": context.review_target_kind,
                "review_target_value": context.review_target_value,
                "working_tree_dirty": context.working_tree_dirty,
                "commands": preview_commands,
            },
            lines,
        )

    if not provider_order:
        payload = _entry_payload(
            context=context,
            selection_source=selection_source,
            attempted_provider=selected_provider,
            executed_provider=None,
            fallback_provider=None,
            instructions=instructions,
            outcome="blocked",
            duration_seconds=0.0,
            findings_reported=None,
            usefulness=usefulness,
            raw_output_path=None,
        )
        _append_local_review_entry(payload)
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {
                **payload,
                "provider": selected_provider,
                "provider_order": provider_order,
            },
            [*lines, "Local review blocked: no supported provider CLI was available."],
        )

    attempted_provider = provider_order[0]
    last_run: LocalReviewProviderRun | None = None
    raw_output_path: Path | None = None
    started = time.monotonic()

    for index, provider_name in enumerate(provider_order):
        binary_name = _PROVIDER_BINARIES[provider_name]
        if shared._ensure_command_available(binary_name) is None:
            lines.append(f"Provider `{provider_name}` is unavailable on PATH.")
            if index + 1 < len(provider_order):
                lines.append(f"Falling back to `{provider_order[index + 1]}`.")
                continue
            duration_seconds = time.monotonic() - started
            payload = _entry_payload(
                context=context,
                selection_source=selection_source,
                attempted_provider=attempted_provider,
                executed_provider=None,
                fallback_provider=None,
                instructions=instructions,
                outcome="blocked",
                duration_seconds=duration_seconds,
                findings_reported=None,
                usefulness=usefulness,
                raw_output_path=None,
            )
            _append_local_review_entry(payload)
            return (
                ExitCode.ENVIRONMENT_ERROR,
                {
                    **payload,
                    "provider": selected_provider,
                    "provider_order": provider_order,
                    "missing_provider": provider_name,
                },
                [
                    *lines,
                    f"Local review blocked: `{provider_name}` is not installed or not on PATH.",
                ],
            )

        last_run = _execute_provider(provider_name, context=context, instructions=instructions)
        lines.append(
            f"Ran `{provider_name}` local review ({last_run.interface_kind} adapter, "
            f"{last_run.duration_seconds:.2f}s)."
        )

        parsed_output = _parse_provider_output(last_run.stdout)
        if last_run.returncode == 0 and parsed_output is not None:
            if save_raw_output:
                raw_output_path = _write_raw_output(
                    provider=provider_name,
                    stdout=last_run.stdout,
                    stderr=last_run.stderr,
                )
            duration_seconds = time.monotonic() - started
            fallback_provider = provider_name if provider_name != attempted_provider else None
            payload = _entry_payload(
                context=context,
                selection_source=selection_source,
                attempted_provider=attempted_provider,
                executed_provider=provider_name,
                fallback_provider=fallback_provider,
                instructions=instructions,
                outcome="ok",
                duration_seconds=duration_seconds,
                findings_reported=parsed_output.findings_reported,
                usefulness=usefulness,
                raw_output_path=raw_output_path,
            )
            _append_local_review_entry(payload)
            summary_lines = [
                *lines,
                f"Local review completed via `{provider_name}`.",
                f"Findings reported: {'yes' if parsed_output.findings_reported else 'no'}",
            ]
            if raw_output_path is not None:
                summary_lines.append(
                    "Raw output: " + str(raw_output_path.relative_to(task_repo.repo_root()))
                )
            if parsed_output.review_body:
                summary_lines.extend(parsed_output.review_body.splitlines())
            return (
                ExitCode.OK,
                {
                    **payload,
                    "provider": selected_provider,
                    "provider_order": provider_order,
                    "base_branch": context.base_branch,
                    "current_branch": context.current_branch,
                    "review_body": parsed_output.review_body,
                },
                summary_lines,
            )

        should_fallback = allow_provider_fallback and index + 1 < len(provider_order)
        if last_run.returncode != 0:
            lines.append(f"`{provider_name}` exited with status {last_run.returncode}.")
        else:
            lines.append(
                f"`{provider_name}` returned unreadable output for the repo-owned contract."
            )

        if should_fallback:
            lines.append(f"Falling back to `{provider_order[index + 1]}`.")
            continue

        raw_output_path = _write_raw_output(
            provider=provider_name,
            stdout=last_run.stdout,
            stderr=last_run.stderr,
        )
        duration_seconds = time.monotonic() - started
        fallback_provider = provider_name if provider_name != attempted_provider else None
        payload = _entry_payload(
            context=context,
            selection_source=selection_source,
            attempted_provider=attempted_provider,
            executed_provider=provider_name,
            fallback_provider=fallback_provider,
            instructions=instructions,
            outcome="failed",
            duration_seconds=duration_seconds,
            findings_reported=None,
            usefulness=usefulness,
            raw_output_path=raw_output_path,
        )
        _append_local_review_entry(payload)
        output_lines = shared._summarize_output_lines(
            [*last_run.stdout.splitlines(), *last_run.stderr.splitlines()]
        )
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {
                **payload,
                "provider": selected_provider,
                "provider_order": provider_order,
                "command": last_run.command,
            },
            [
                *lines,
                "Local review failed: the provider command did not produce a usable result.",
                f"Raw output: {raw_output_path.relative_to(task_repo.repo_root())}",
                *output_lines,
            ],
        )

    raise AssertionError("provider review loop exited without returning")  # pragma: no cover


def handle_local_review(args: Any) -> CommandResult:
    exit_code, data, lines = local_review_data(
        provider=getattr(args, "provider", None),
        base_branch=getattr(args, "base", DEFAULT_LOCAL_REVIEW_BASE_BRANCH),
        instructions=getattr(args, "instructions", None),
        allow_provider_fallback=bool(getattr(args, "allow_provider_fallback", False)),
        save_raw_output=bool(getattr(args, "save_raw_output", False)),
        usefulness=getattr(args, "usefulness", "pending"),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "DEFAULT_LOCAL_REVIEW_BASE_BRANCH",
    "DEFAULT_LOCAL_REVIEW_PROVIDER",
    "LOCAL_REVIEW_DIRECTORY",
    "LOCAL_REVIEW_HARNESS_PATH",
    "LOCAL_REVIEW_LOG_FILENAME",
    "LOCAL_REVIEW_PROVIDER_ENV",
    "LOCAL_REVIEW_RUNS_DIRECTORY",
    "LOCAL_REVIEW_STATUS_PATTERN",
    "SUPPORTED_LOCAL_REVIEW_PROVIDERS",
    "VALID_LOCAL_REVIEW_USEFULNESS",
    "LocalReviewContext",
    "LocalReviewParsedOutput",
    "LocalReviewProviderRun",
    "_append_local_review_entry",
    "_entry_payload",
    "_execute_provider",
    "_harness_value",
    "_local_review_log_path",
    "_local_review_runs_dir",
    "_parse_provider_output",
    "_provider_attempt_order",
    "_provider_command",
    "_render_codex_review_prompt",
    "_render_prompt_contract",
    "_render_prompt_only_provider_prompt",
    "_resolve_provider_selection",
    "_review_context",
    "_run_git",
    "_write_raw_output",
    "handle_local_review",
    "local_review_data",
]
