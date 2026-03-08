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
    "README.md",
    "docs/AGENT_RUNBOOK.md",
    "ops/skills/horadus-cli/SKILL.md",
    "ops/skills/horadus-cli/references/commands.md",
)

COMPLETION_GUIDANCE_REFERENCE_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "README.md",
    "docs/AGENT_RUNBOOK.md",
    "ops/skills/horadus-cli/SKILL.md",
    "tasks/BACKLOG.md",
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
    "Local commits, local tests, and a clean working tree are checkpoints, not completion.",
    "Do not stop at a local commit boundary unless the user explicitly asked for a checkpoint.",
    "Resolve locally solvable environment blockers before reporting blocked.",
)


def canonical_task_workflow_command_templates() -> tuple[str, ...]:
    return tuple(command.template for command in CANONICAL_TASK_WORKFLOW_COMMANDS)


def canonical_task_workflow_commands_for_task(task_id: str) -> tuple[str, ...]:
    return tuple(command.render(task_id) for command in CANONICAL_TASK_WORKFLOW_COMMANDS)


def completion_guidance_statements() -> tuple[str, ...]:
    return COMPLETION_GUIDANCE_STATEMENTS
