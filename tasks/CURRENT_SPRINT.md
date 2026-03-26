# Current Sprint

**Sprint Goal**: Close overdue security and workflow-context gaps, then extend trend state and operator intelligence surfaces with horizon-aware semantics and stronger source/entity understanding.
**Sprint Number**: 8
**Sprint Dates**: 2026-04-07 to 2026-04-20
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- `TASK-189` Restrict `/health` and `/metrics` exposure outside development [REQUIRES_HUMAN]
- `TASK-190` Harden admin-key compare + API key store file permissions [REQUIRES_HUMAN]
- `TASK-288` Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue [REQUIRES_HUMAN]

## Selection Notes

- Sprint 8 opens immediately after Sprint 7 closes and keeps the active lane capped to eight tasks.
- The selected queue starts with overdue security and workflow-context asks before moving into deeper trend-state and analytical model upgrades.
- `TASK-189`, `TASK-190`, and `TASK-288` are explicitly reactivated for this sprint by human request, but they still require human review/sign-off before completion.
- `TASK-237` remains in the same sprint because bounded dynamic source diagnostics compounds the operator value of the upgraded trend state.
- Open tasks not listed here remain in `tasks/BACKLOG.md` and are not considered closed or descoped by this sprint reset.

## Suggested Sequence

1. `TASK-189` Restrict `/health` and `/metrics` exposure outside development.
2. `TASK-190` Harden admin-key compare and API key store file permissions.
3. `TASK-288` Convert RFC-001 into a human-approved implementation queue.
4. `TASK-234` Make uncertainty and momentum first-class trend state.
5. `TASK-237` Add dynamic reliability diagnostics and time-varying source credibility.

## Human Blocker Metadata

- TASK-189 | owner=human-operator | last_touched=2026-03-26 | next_action=2026-04-07 | escalate_after_days=7
- TASK-190 | owner=human-operator | last_touched=2026-03-26 | next_action=2026-04-07 | escalate_after_days=7
- TASK-288 | owner=human-operator | last_touched=2026-03-26 | next_action=2026-04-07 | escalate_after_days=7
- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7

## Telegram Launch Scope

- launch_scope: excluded_until_task_080_done
- decision_date: 2026-03-03
- rationale: Telegram ingestion remains explicitly out of launch scope until the human-gated wiring/sign-off task closes.

## Completed This Sprint

- `TASK-226` Add Compact Assessment Summaries to `horadus triage collect`
- `TASK-233` Support Multi-Horizon Trend Variants for the Same Underlying Theme
- `TASK-234` Make Uncertainty and Momentum First-Class Trend State ✅
- `TASK-236` Add Canonical Entity Registry for Actors, Organizations, and Locations ✅
- `TASK-237` Add Dynamic Reliability Diagnostics and Time-Varying Source Credibility ✅
