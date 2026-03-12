from __future__ import annotations

from dataclasses import dataclass

TASK_ID_PLACEHOLDER = "TASK-XXX"

WORKFLOW_ESCAPE_HATCH_TEXT = (
    "Use raw `git` / `gh` commands only when the Horadus CLI does not expose "
    "the needed workflow step yet, or when the CLI explicitly tells you a "
    "manual recovery step is required."
)


@dataclass(frozen=True, slots=True)
class WorkflowCommand:
    label: str
    template: str

    def render(self, task_id: str) -> str:
        return self.template.replace(TASK_ID_PLACEHOLDER, task_id)


CANONICAL_TASK_WORKFLOW_COMMANDS: tuple[WorkflowCommand, ...] = (
    WorkflowCommand(
        label="Start preflight",
        template="uv run --no-sync horadus tasks preflight",
    ),
    WorkflowCommand(
        label="Guarded autonomous start",
        template=(
            f"uv run --no-sync horadus tasks safe-start {TASK_ID_PLACEHOLDER} --name short-name"
        ),
    ),
    WorkflowCommand(
        label="Context pack",
        template=f"uv run --no-sync horadus tasks context-pack {TASK_ID_PLACEHOLDER}",
    ),
    WorkflowCommand(
        label="Fast iteration gate",
        template="make agent-check",
    ),
    WorkflowCommand(
        label="Canonical local gate",
        template="uv run --no-sync horadus tasks local-gate --full",
    ),
    WorkflowCommand(
        label="Lifecycle verifier",
        template=f"uv run --no-sync horadus tasks lifecycle {TASK_ID_PLACEHOLDER} --strict",
    ),
    WorkflowCommand(
        label="Completion",
        template=f"uv run --no-sync horadus tasks finish {TASK_ID_PLACEHOLDER}",
    ),
)

WORKFLOW_REFERENCE_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "docs/AGENT_RUNBOOK.md",
    "ops/skills/horadus-cli/SKILL.md",
    "ops/skills/horadus-cli/references/commands.md",
)

COMPLETION_GUIDANCE_REFERENCE_PATHS: tuple[str, ...] = ("AGENTS.md",)

DEPENDENCY_AWARE_GUIDANCE_REFERENCE_PATHS: tuple[str, ...] = ("AGENTS.md",)

FALLBACK_GUIDANCE_REFERENCE_PATHS: tuple[str, ...] = ("AGENTS.md",)

WORKFLOW_POLICY_GUARDRAIL_REFERENCE_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "tasks/specs/TEMPLATE.md",
)

COMPLETION_GUIDANCE_STATEMENTS: tuple[str, ...] = (
    (
        "Treat repo-facing work as incomplete until requested deliverables, "
        "required repo updates, and required verification/gate runs are "
        "finished or explicitly reported blocked."
    ),
    (
        "Implementation, required tests/gates, and required task/doc/status "
        "updates remain part of the same task unless they are explicitly "
        "blocked."
    ),
    (
        "If a task is blocked, report the exact missing item, the blocker "
        "causing it, and the furthest completed lifecycle step rather than a "
        "vague partial-completion claim."
    ),
    (
        "Do not claim a task is complete, done, or finished until "
        "`uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` passes or "
        "`horadus tasks finish TASK-XXX` completes successfully."
    ),
    (
        "The default review-gate timeout for `horadus tasks finish` is 600 "
        "seconds (10 minutes). Agents must not override it unless a human "
        "explicitly requested a different timeout."
    ),
    (
        "Do not proactively suggest changing the `horadus tasks finish` "
        "review timeout; wait the canonical 10-minute window unless the human "
        "explicitly asked otherwise."
    ),
    (
        "A `THUMBS_UP` reaction from the configured reviewer on the PR "
        "summary counts as a positive review-gate signal; once current-head "
        "required checks are green, `horadus tasks finish` may continue early "
        "on that signal while still blocking actionable current-head review "
        "comments."
    ),
    (
        "If the PR head changes during or between finish invocations after "
        "review work starts, the CLI must immediately revalidate current-head "
        "merge readiness, auto-resolve outdated unresolved older-head review "
        "threads, request fresh review once for the new head when needed, "
        "discard the older review-window context, and start a fresh review "
        "window."
    ),
    "Local commits, local tests, and a clean working tree are checkpoints, not completion.",
    "Do not stop at a local commit boundary unless the user explicitly asked for a checkpoint.",
    "Resolve locally solvable environment blockers before reporting blocked.",
)

DEPENDENCY_AWARE_GUIDANCE_STATEMENTS: tuple[str, ...] = (
    (
        "Do not skip prerequisite workflow steps such as preflight, guarded "
        "task start, or context collection just because the likely end state "
        "looks obvious."
    ),
    (
        "Prefer Horadus workflow commands over raw `git` / `gh` when the CLI "
        "covers the step because the CLI encodes sequencing, policy, and "
        "verification dependencies rather than just style."
    ),
    (
        "Keep using the workflow until prerequisite checks, required "
        "verification reruns, and completion verification succeed; do not stop "
        "at the first plausible success signal."
    ),
)

FALLBACK_GUIDANCE_STATEMENTS: tuple[str, ...] = (
    (
        "Treat an empty, partial, or suspiciously narrow workflow result as a "
        "retrieval problem first when the missing data likely exists."
    ),
    (
        "Before concluding that no result exists, try one or two sensible "
        "recovery steps such as broader Horadus queries, alternate filters, "
        "or the documented manual recovery path."
    ),
    (
        "If a forced fallback is still required after those recovery attempts, "
        "record it with `horadus tasks record-friction`; do not log routine "
        "success cases or expected empty results."
    ),
)

WORKFLOW_POLICY_GUARDRAIL_STATEMENTS: tuple[str, ...] = (
    (
        "Apply these guardrails only when changing shared workflow helpers, "
        "shared workflow config, or review/merge policy behavior; do not "
        "inflate unrelated tasks with generic process boilerplate."
    ),
    (
        "Before changing shared workflow helpers or shared workflow config, "
        "enumerate every caller that depends on the shared behavior."
    ),
    (
        "When shared workflow behavior changes, add at least one regression "
        "test for an unaffected caller so the change does not silently break "
        "other workflow entry points."
    ),
    (
        "Before changing review, comment, or reaction handling in merge "
        "policy logic, define the current-head and current-window semantics "
        "for each signal and regression-test both the intended pass path and "
        "at least one stale or non-applicable signal path."
    ),
)


def canonical_task_workflow_command_templates() -> tuple[str, ...]:
    return tuple(command.template for command in CANONICAL_TASK_WORKFLOW_COMMANDS)


def canonical_task_workflow_commands_for_task(task_id: str) -> tuple[str, ...]:
    return tuple(command.render(task_id) for command in CANONICAL_TASK_WORKFLOW_COMMANDS)


def completion_guidance_statements() -> tuple[str, ...]:
    return COMPLETION_GUIDANCE_STATEMENTS


def dependency_aware_guidance_statements() -> tuple[str, ...]:
    return DEPENDENCY_AWARE_GUIDANCE_STATEMENTS


def fallback_guidance_statements() -> tuple[str, ...]:
    return FALLBACK_GUIDANCE_STATEMENTS


def workflow_policy_guardrail_statements() -> tuple[str, ...]:
    return WORKFLOW_POLICY_GUARDRAIL_STATEMENTS
