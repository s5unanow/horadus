from __future__ import annotations

import re
import subprocess  # nosec B404
import time
from typing import Final

from tools.horadus.python.horadus_workflow import task_repo

from ._task_workflow_local_review_constants import (
    LOCAL_REVIEW_STATUS_PATTERN,
    PROVIDER_INTERFACE_KIND,
)
from ._task_workflow_local_review_models import (
    LocalReviewContext,
    LocalReviewParsedOutput,
    LocalReviewProviderRun,
)

_STDIN_PROMPT_PROVIDERS: Final[frozenset[str]] = frozenset({"claude", "gemini"})
_CODEX_NO_FINDINGS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"no\s+(?:findings|issues)(?:\s+found)?"
    r"|did\s+not\s+(?:find|identify)(?:\s+any)?\s+issues"
    r"|didn't\s+(?:find|identify)(?:\s+any)?\s+issues"
    r"|no\s+blocking\s+issues"
    r"|looks\s+good\s+to\s+me"
    r")\b",
    re.IGNORECASE,
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
            ],
            prompt,
        )
    if provider == "gemini":
        prompt = _render_prompt_only_provider_prompt(context=context, instructions=instructions)
        return (
            [
                "gemini",
                "--prompt",
                "Review the full stdin payload and follow its contract exactly.",
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
        ],
        prompt,
    )


def _provider_stdin_text(provider: str, prompt: str) -> str | None:
    if provider in _STDIN_PROMPT_PROVIDERS:
        return prompt
    return None


def _execute_provider(
    provider: str,
    *,
    context: LocalReviewContext,
    instructions: str | None,
) -> LocalReviewProviderRun:
    command, prompt = _provider_command(provider, context=context, instructions=instructions)
    started = time.monotonic()
    try:
        completed = subprocess.run(  # nosec B603
            command,
            cwd=task_repo.repo_root(),
            input=_provider_stdin_text(provider, prompt),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        duration_seconds = time.monotonic() - started
        return LocalReviewProviderRun(
            provider=provider,
            interface_kind=PROVIDER_INTERFACE_KIND[provider],
            command=command,
            prompt=prompt,
            returncode=1,
            stdout="",
            stderr=str(exc),
            duration_seconds=duration_seconds,
        )
    duration_seconds = time.monotonic() - started
    return LocalReviewProviderRun(
        provider=provider,
        interface_kind=PROVIDER_INTERFACE_KIND[provider],
        command=command,
        prompt=prompt,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        duration_seconds=duration_seconds,
    )


def _parse_repo_contract_output(output_text: str) -> LocalReviewParsedOutput | None:
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


def _parse_codex_review_output(output_text: str) -> LocalReviewParsedOutput | None:
    stripped = output_text.strip()
    if not stripped:
        return None
    return LocalReviewParsedOutput(
        findings_reported=_CODEX_NO_FINDINGS_PATTERN.search(stripped) is None,
        review_body=stripped,
    )


def _parse_provider_output(provider: str, output_text: str) -> LocalReviewParsedOutput | None:
    parsed = _parse_repo_contract_output(output_text)
    if parsed is not None:
        return parsed
    if provider == "codex":
        return _parse_codex_review_output(output_text)
    return None
