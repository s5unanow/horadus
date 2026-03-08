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


def canonical_task_workflow_command_templates() -> tuple[str, ...]:
    return tuple(command.template for command in CANONICAL_TASK_WORKFLOW_COMMANDS)


def canonical_task_workflow_commands_for_task(task_id: str) -> tuple[str, ...]:
    return tuple(command.render(task_id) for command in CANONICAL_TASK_WORKFLOW_COMMANDS)
