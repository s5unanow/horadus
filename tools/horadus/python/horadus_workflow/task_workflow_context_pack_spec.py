from __future__ import annotations

from collections.abc import Mapping

from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode


def ambiguous_spec_resolution_result(
    spec_resolution: Mapping[str, object],
) -> CommandResult | None:
    if not spec_resolution.get("ambiguous"):
        return None
    task_id = spec_resolution.get("task_id")
    return CommandResult(
        exit_code=ExitCode.VALIDATION_ERROR,
        error_lines=[
            f"{task_id} has ambiguous canonical task spec candidates: "
            f"{spec_resolution.get('ambiguity_reason')}"
        ],
        data={"task_id": task_id, "spec_resolution": dict(spec_resolution)},
    )


def implement_mode_excluded_sources(include_archive: bool) -> list[dict[str, object]]:
    archive_sources: dict[bool, dict[str, object]] = {
        False: {
            "source": "archive/",
            "reason": "Archived task history is available only through explicit archive lookup.",
        },
        True: {
            "source": "archive/closed_tasks/* except requested task",
            "reason": "Archive inclusion is scoped to the explicitly requested task.",
        },
    }
    return [
        archive_sources[include_archive],
        {
            "source": "README.md",
            "reason": "Pointer/setup surface excluded from the Phase 1 implementation policy payload.",
        },
        {"source": "ops/skills/", "reason": "Caller-surface migration is deferred to TASK-383."},
        {
            "source": "policy-document front matter",
            "reason": "Policy front matter migration is deferred; the curated registry is used instead.",
        },
        {
            "source": "local or hosted retrieval index",
            "reason": "Out of scope for the Phase 1 CLI-first implementation slice.",
        },
    ]


__all__ = [
    "ambiguous_spec_resolution_result",
    "implement_mode_excluded_sources",
]
