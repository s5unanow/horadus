# Current Sprint

**Sprint Goal**: Concentrate the active queue on high-leverage runtime correctness, replay resilience, and audited mutation semantics.
**Sprint Number**: 6
**Sprint Dates**: 2026-03-22 to 2026-04-05
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- `TASK-201` Preserve audited, atomic manual trend overrides
- `TASK-206` Keep event recency monotonic under late and backfilled mentions
- `TASK-209` Restore `canonical_summary` alignment with `primary_item_id` after Tier-2
- `TASK-202` Make degraded replay queue retryable instead of fail-once terminal

## Selection Notes

- Sprint 6 intentionally keeps the active queue small and excludes human-gated work unless a human explicitly reactivates it.
- The selected tasks were chosen for direct impact on audited write correctness, monotonic event semantics, summary identity integrity, and replay/rebuild resilience.
- Workflow and repo-health follow-ups remain in `tasks/BACKLOG.md`, but Sprint 6 shifts the active lane back to runtime correctness and production-facing behavior.
- Open tasks not listed here remain in `tasks/BACKLOG.md` and are not considered closed or descoped by this sprint reset.

## Suggested Sequence

1. `TASK-201` Close the live-probability mutation hole first so manual overrides always use the audited atomic path.
2. `TASK-206` Restore monotonic event recency next because late/backfilled mentions can currently corrupt clustering and lifecycle semantics.
3. `TASK-209` Re-align `canonical_summary` with `primary_item_id` after Tier-2 so event identity semantics stop drifting again.
4. `TASK-202` Harden degraded replay retries last because it is the broadest queue-state change in the selected set.

## Human Blocker Metadata

- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-190 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-288 | owner=human-operator | last_touched=2026-03-09 | next_action=2026-03-10 | escalate_after_days=7

## Telegram Launch Scope

- launch_scope: excluded_until_task_080_done
- decision_date: 2026-03-03
- rationale: Telegram ingestion remains explicitly out of launch scope until the human-gated wiring/sign-off task closes.

## Completed This Sprint

- Sprint opened on 2026-03-22 with carry-over work only; no Sprint 6 tasks are complete yet.
