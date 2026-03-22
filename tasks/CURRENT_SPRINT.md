# Current Sprint

**Sprint Goal**: Concentrate the active queue on high-leverage runtime correctness, replay resilience, and audited mutation semantics.
**Sprint Number**: 6
**Sprint Dates**: 2026-03-22 to 2026-04-05
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- `TASK-206` Keep event recency monotonic under late and backfilled mentions
- `TASK-209` Restore `canonical_summary` alignment with `primary_item_id` after Tier-2
- `TASK-272` Keep Active Reasoning Metadata Consistent Across Mixed-Route Runs
- `TASK-202` Make degraded replay queue retryable instead of fail-once terminal
- `TASK-338` Separate Provisional and Canonical Extraction State in Degraded Mode
- `TASK-230` Add Coverage Observability Beyond Source Freshness

## Selection Notes

- Sprint 6 intentionally keeps the active queue small and excludes human-gated work unless a human explicitly reactivates it.
- The selected tasks were chosen for direct impact on audited write correctness, API-surface hardening, monotonic event semantics, summary identity integrity, mixed-route metadata correctness, replay/degraded-mode resilience, and coverage visibility.
- Workflow and repo-health follow-ups remain in `tasks/BACKLOG.md`, but Sprint 6 shifts the active lane back to runtime correctness and production-facing behavior.
- Open tasks not listed here remain in `tasks/BACKLOG.md` and are not considered closed or descoped by this sprint reset.

## Suggested Sequence

1. `TASK-206` Restore monotonic event recency because late/backfilled mentions can currently corrupt clustering and lifecycle semantics.
2. `TASK-209` Re-align `canonical_summary` with `primary_item_id` after Tier-2 so event identity semantics stop drifting again.
3. `TASK-272` Fix mixed-route reasoning metadata drift while the Tier-1/Tier-2 runtime semantics are under active review.
4. `TASK-202` Harden degraded replay retries before broader degraded-mode state work lands.
5. `TASK-338` Separate provisional and canonical degraded-mode extraction state so provisional output cannot silently become durable truth.
6. `TASK-230` Add coverage observability last to expose remaining blind spots after the higher-risk runtime-correctness fixes are in flight.

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

- `TASK-208` Restrict API docs and schema exposure outside development ✅
- `TASK-201` Preserve audited, atomic manual trend overrides ✅
