# Current Sprint

**Sprint Goal**: Narrow the active queue to the highest-impact non-human work on semantic correctness, replayability, and bounded production hardening.
**Sprint Number**: 5
**Sprint Dates**: 2026-03-17 to 2026-03-31
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- `TASK-336` Separate Story Clusters from Stable Event-Claim Identity
- `TASK-231` Extend Event Invalidation into a Compensating Restatement Ledger
- `TASK-228` Harden Trend Forecast Contracts with Explicit Horizon and Resolution Semantics
- `TASK-335` Move Trend-Impact Mapping Fully Into Deterministic Code
- `TASK-340` Split Event Epistemic State from Activity State
- `TASK-227` Make Corroboration Provenance-Aware Instead of Source-Count-Aware
- `TASK-235` Add Event Split/Merge Lineage for Evolving Stories
- `TASK-339` Version Runtime Provenance for LLM-Derived Artifacts and Scoring Math
- `TASK-337` Pin Live Trend State to Active Definition/Scoring Versions
- `TASK-341` Harden Mutable API Write Contracts with Revision Tokens, Idempotency, and Durable Audit Records

## Selection Notes

- Sprint 5 intentionally excludes human-gated work from the active queue unless a human explicitly reactivates it.
- The selected tasks were chosen for direct impact on stable identity, deterministic semantics, replay/rebuild safety, and production-facing mutation correctness.
- Open tasks not listed here remain in `tasks/BACKLOG.md` and are not considered closed or descoped by this sprint reset.

## Human Blocker Metadata

- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-190 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-288 | owner=human-operator | last_touched=2026-03-09 | next_action=2026-03-10 | escalate_after_days=7

## Telegram Launch Scope

- launch_scope: excluded_until_task_080_done
- decision_date: 2026-03-03
- rationale: Telegram ingestion remains explicitly out of launch scope until the human-gated wiring/sign-off task closes.
