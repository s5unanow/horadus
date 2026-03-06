#!/usr/bin/env python3
"""Gate assessment publication for PO/BA under fully human-gated queues."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

RE_ACTIVE_TASK = re.compile(r"^-\s+`(TASK-\d{3})`\s+(.*)$")
RE_BLOCKER_METADATA = re.compile(r"^-\s+(TASK-\d{3})\s+\|\s+(.+)$")
RE_KEY_VALUE = re.compile(r"^([a-z_]+)=(.+)$")


@dataclass(frozen=True)
class ActiveTask:
    task_id: str
    title: str
    requires_human: bool


@dataclass(frozen=True)
class GateDecision:
    role: str
    decision: str
    reason: str
    blocker_state_hash: str
    previous_blocker_state_hash: str | None
    fully_human_gated: bool
    active_task_ids: tuple[str, ...]


def _parse_current_sprint(
    path: Path,
) -> tuple[list[ActiveTask], dict[str, dict[str, str]], dict[str, str]]:
    active_tasks: list[ActiveTask] = []
    blocker_metadata: dict[str, dict[str, str]] = {}
    launch_scope: dict[str, str] = {}
    section: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped == "## Active Tasks":
            section = "active"
            continue
        if stripped == "## Human Blocker Metadata":
            section = "blockers"
            continue
        if stripped == "## Telegram Launch Scope":
            section = "launch_scope"
            continue
        if stripped.startswith("## "):
            section = None
            continue
        if not stripped.startswith("- "):
            continue

        if section == "active":
            match = RE_ACTIVE_TASK.match(stripped)
            if not match:
                continue
            title = match.group(2).strip()
            active_tasks.append(
                ActiveTask(
                    task_id=match.group(1),
                    title=title,
                    requires_human="[REQUIRES_HUMAN]" in title,
                )
            )
            continue

        if section == "blockers":
            match = RE_BLOCKER_METADATA.match(stripped)
            if not match:
                continue
            metadata: dict[str, str] = {}
            for item in match.group(2).split("|"):
                field_match = RE_KEY_VALUE.match(item.strip())
                if field_match:
                    metadata[field_match.group(1)] = field_match.group(2)
            blocker_metadata[match.group(1)] = metadata
            continue

        if section == "launch_scope":
            key, _, value = stripped[2:].partition(":")
            if key and value:
                launch_scope[key.strip()] = value.strip()

    return active_tasks, blocker_metadata, launch_scope


def _compute_blocker_state_hash(
    active_tasks: list[ActiveTask],
    blocker_metadata: dict[str, dict[str, str]],
    launch_scope: dict[str, str],
) -> str:
    payload = {
        "active_tasks": [asdict(task) for task in active_tasks],
        "blocker_metadata": {
            task.task_id: blocker_metadata.get(task.task_id, {}) for task in active_tasks
        },
        "launch_scope": launch_scope,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_previous_hash(memory_file: Path) -> str | None:
    if not memory_file.exists():
        return None

    for line in reversed(memory_file.read_text(encoding="utf-8").splitlines()):
        if line.startswith("- blocker_state_hash: "):
            return line.split(": ", 1)[1].strip()
    return None


def _append_memory_entry(memory_file: Path, decision: GateDecision) -> None:
    parent = memory_file.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not os.access(parent, os.W_OK):
        raise PermissionError(f"memory directory is not writable: {parent}")

    local_now = datetime.now().astimezone()
    timestamp = local_now.isoformat(timespec="seconds")
    active_task_ids = ", ".join(decision.active_task_ids) or "(none)"
    lines = [
        "",
        f"## {local_now.date()} publish gate",
        f"- role: {decision.role}",
        f"- decision: {decision.decision}",
        f"- reason: {decision.reason}",
        f"- blocker_state_hash: {decision.blocker_state_hash}",
        f"- previous_blocker_state_hash: {decision.previous_blocker_state_hash or 'none'}",
        f"- fully_human_gated: {'yes' if decision.fully_human_gated else 'no'}",
        f"- active_task_ids: {active_task_ids}",
        f"- evaluated_at: {timestamp}",
    ]
    with memory_file.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def decide_gate(
    *,
    role: str,
    sprint_file: Path,
    memory_file: Path,
) -> GateDecision:
    active_tasks, blocker_metadata, launch_scope = _parse_current_sprint(sprint_file)
    blocker_state_hash = _compute_blocker_state_hash(active_tasks, blocker_metadata, launch_scope)
    previous_hash = _load_previous_hash(memory_file)
    fully_human_gated = bool(active_tasks) and all(task.requires_human for task in active_tasks)

    if fully_human_gated and previous_hash == blocker_state_hash:
        return GateDecision(
            role=role,
            decision="skip",
            reason="unchanged_human_gated_queue",
            blocker_state_hash=blocker_state_hash,
            previous_blocker_state_hash=previous_hash,
            fully_human_gated=True,
            active_task_ids=tuple(task.task_id for task in active_tasks),
        )

    reason = "human_gated_queue_changed" if fully_human_gated else "queue_not_fully_human_gated"

    return GateDecision(
        role=role,
        decision="publish",
        reason=reason,
        blocker_state_hash=blocker_state_hash,
        previous_blocker_state_hash=previous_hash,
        fully_human_gated=fully_human_gated,
        active_task_ids=tuple(task.task_id for task in active_tasks),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, help="Assessment role (for memory logging).")
    parser.add_argument(
        "--sprint-file",
        default="tasks/CURRENT_SPRINT.md",
        help="Path to the current sprint ledger.",
    )
    parser.add_argument(
        "--memory-file",
        required=True,
        help="Automation memory file to append decisions to.",
    )
    args = parser.parse_args(argv)

    decision = decide_gate(
        role=args.role,
        sprint_file=Path(args.sprint_file),
        memory_file=Path(args.memory_file),
    )
    _append_memory_entry(Path(args.memory_file), decision)

    print(f"decision={decision.decision}")
    print(f"reason={decision.reason}")
    print(f"blocker_state_hash={decision.blocker_state_hash}")
    print(f"previous_blocker_state_hash={decision.previous_blocker_state_hash or 'none'}")
    print(f"fully_human_gated={'true' if decision.fully_human_gated else 'false'}")
    print(f"active_task_ids={','.join(decision.active_task_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
