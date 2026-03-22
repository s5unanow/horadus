# Current Sprint

**Sprint Goal**: Narrow the active queue to the highest-impact non-human work on semantic correctness, replayability, and bounded production hardening.
**Sprint Number**: 5
**Sprint Dates**: 2026-03-17 to 2026-03-31
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- `TASK-337` Pin Live Trend State to Active Definition/Scoring Versions
- `TASK-341` Harden Mutable API Write Contracts with Revision Tokens, Idempotency, and Durable Audit Records

## Selection Notes

- Sprint 5 intentionally excludes human-gated work from the active queue unless a human explicitly reactivates it.
- The selected tasks were chosen for direct impact on stable identity, deterministic semantics, replay/rebuild safety, and production-facing mutation correctness.
- Sprint 5 now also carries a stricter repo-health lane focused on enforcing architecture, static-analysis, and CI guardrails earlier rather than allowing quality debt to accumulate.
- Open tasks not listed here remain in `tasks/BACKLOG.md` and are not considered closed or descoped by this sprint reset.

## Suggested Sequence

1. `TASK-352` Enforce server-side secret and dependency-vulnerability scanning first to close the easiest server-side security gaps with limited repo churn.
2. `TASK-350` Add the cyclomatic-complexity ratchet early so new and modified code starts paying the stricter control-flow budget immediately.
3. `TASK-349` Add repo-wide dependency-direction gates after the lighter gate expansions, with planning first because this is the most likely task to expose existing architectural drift.
4. `TASK-353` Align canonical release/local gates last so the stricter analyzer set above becomes one authoritative enforced contract instead of several partially overlapping paths.

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

- `TASK-336` Separate Story Clusters from Stable Event-Claim Identity
- `TASK-231` Extend Event Invalidation into a Compensating Restatement Ledger ✅
- `TASK-347` Investigate and stabilize hanging `horadus tasks local-review` runs ✅
- `TASK-228` Harden Trend Forecast Contracts with Explicit Horizon and Resolution Semantics ✅
- `TASK-348` Make `horadus tasks finish` fail loudly and recover cleanly in the review window ✅
- `TASK-352` Enforce server-side secret and dependency vulnerability scanning in CI ✅
- `TASK-351` Bring `scripts/` Under the Main Lint, Type, Security, and Coverage Posture ✅
- `TASK-350` Add a cyclomatic-complexity ratchet for tracked Python surfaces ✅
- `TASK-349` Add repo-wide dependency direction gates for `src/` and tooling adapter seams ✅
- `TASK-353` Align canonical release and local gates with the full repo-owned analyzer set ✅
- `TASK-355` Add repo-owned sprint autopilot automation with external locking ✅
- `TASK-356` Move autopilot lock into the automation-owned Codex path ✅
- `TASK-357` Version a repo-owned Codex rules baseline for autopilot workflow commands ✅
- `TASK-335` Move Trend-Impact Mapping Fully Into Deterministic Code ✅
- `TASK-358` Replace autopilot `flock` dependency with a repo-owned automation lock helper ✅
- `TASK-340` Split Event Epistemic State from Activity State ✅
- `TASK-227` Make Corroboration Provenance-Aware Instead of Source-Count-Aware ✅
- `TASK-339` Version Runtime Provenance for LLM-Derived Artifacts and Scoring Math ✅
- `TASK-235` Add Event Split/Merge Lineage for Evolving Stories ✅
- `TASK-346` Front-load adversarial review guidance for high-risk cross-surface tasks ✅
