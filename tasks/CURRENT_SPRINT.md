# Current Sprint

**Sprint Goal**: Tighten workflow delivery reliability, eliminate lingering source-identity correctness risk, and improve operator discovery under bounded model budget.
**Sprint Number**: 7
**Sprint Dates**: 2026-03-24 to 2026-04-06
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- `TASK-344` Surface review-gate wait state and deadlines in `horadus tasks finish`
- `TASK-345` Preflight stale review state before entering the finish review window
- `TASK-256` Enforce the task completion contract for tests, docs, and gate re-runs
- `TASK-354` Centralize repo-owned secret-scan policy and exclude rules
- `TASK-207` Use stable source identity keys for GDELT and Telegram watermarks
- `TASK-229` Add a novelty lane outside the active trend list
- `TASK-232` Strengthen operator adjudication workflow for high-risk events
- `TASK-238` Prioritize Tier-2 budget with value-of-information scheduling
- `TASK-225` Make `horadus triage collect` return task-aware search hits

## Selection Notes

- Sprint 7 opens early because Sprint 6's active queue is complete and the live sprint surface should reflect the next real execution window.
- The selected tasks emphasize workflow reliability first, then source-identity correctness, bounded discovery, and operator-facing review quality.
- Human-gated tasks remain visible below but stay out of the active lane until a human explicitly reactivates them.
- Broader model/state expansions remain in `tasks/BACKLOG.md`, but this sprint keeps the queue anchored to high-leverage, near-term execution work.
- Open tasks not listed here remain in `tasks/BACKLOG.md` and are not considered closed or descoped by this sprint reset.

## Suggested Sequence

1. `TASK-343` Add caller-aware validation packs before more shared-helper workflow changes land.
2. `TASK-344` Surface review-gate wait state so finish-loop state is operator-visible.
3. `TASK-345` Preflight stale review state once wait-state reporting is explicit.
4. `TASK-256` Tighten the remaining completion contract around tests, docs, and reruns.
5. `TASK-354` Unify secret-scan policy ownership across local and CI enforcement paths.
6. `TASK-207` Fix stable source identity first for the independently actionable GDELT watermark path.
7. `TASK-229` Add a bounded novelty lane once the workflow surfaces are tighter.
8. `TASK-232` Build the richer operator adjudication path on top of the `TASK-231` restatement model.
9. `TASK-238` Spend Tier-2 budget according to bounded value-of-information signals.
10. `TASK-225` Improve triage bundle usefulness for the next backlog review cycle.

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

- `TASK-343` Add caller-aware validation packs for shared helper changes ✅
- `TASK-361` Unblock repo-wide dependency audit for the current upstream-unfixed `pygments` CVE ✅
