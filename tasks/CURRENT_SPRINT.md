# Current Sprint

**Sprint Goal**: Strengthen evaluation and code-health guardrails, improve review/authoring ergonomics, and carry forward the held RFC-001 planning blocker without forcing it into autonomous work.
**Sprint Number**: 9
**Sprint Dates**: 2026-04-21 to 2026-05-04
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- `TASK-366` Add a Code-Health Erosion Eval for Changed Python Surfaces
- `TASK-367` Ratchet Changed-File Code-Health Regressions in Local Gates
- `TASK-368` Enforce Hotspot-Touch Debt Capture for Allowlisted Production Files
- `TASK-369` Make Local Pre-Push Review Slop-Aware for Changed Files
- `TASK-255` Add a Targeted Docstring Quality Gate for High-Value Surfaces
- `TASK-334` Align Gemini local-review approval-mode flags with installed CLI
- `TASK-288` Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue [REQUIRES_HUMAN]

## Selection Notes

- Sprint 9 opens immediately after Sprint 8 and seeds a nine-task queue from the live backlog based on the next relevant autonomous work plus one carried-forward human blocker.
- The selected queue focuses first on behavior evals and deterministic code-health guardrails, then on review/authoring workflow polish.
- `TASK-366` should land before `TASK-367`, and `TASK-369` should reuse the changed-file/code-health output once it exists.
- `TASK-288` is carried into Sprint 9 as a tracked hold item only; it remains human-gated and is not part of the autonomous implementation lane unless the human explicitly reactivates it.
- Open tasks not listed here remain in `tasks/BACKLOG.md` and are not considered closed or descoped by this sprint reset.

## Suggested Sequence

1. `TASK-363` Add behavior-oriented eval suites for high-risk LLM safety paths.
2. `TASK-364` Build a runtime-to-eval regression intake loop.
3. `TASK-366` Add a code-health erosion eval for changed Python surfaces.
4. `TASK-367` Ratchet changed-file code-health regressions in local gates.
5. `TASK-368` Enforce hotspot-touch debt capture for allowlisted production files.
6. `TASK-369` Make local pre-push review slop-aware for changed files.
7. `TASK-255` Add a targeted docstring quality gate for high-value surfaces.
8. `TASK-334` Align Gemini local-review approval-mode flags with installed CLI.
9. `TASK-288` Keep as a carried human-blocked planning item; do not start autonomously.

## Human Blocker Metadata

- TASK-288 | owner=human-operator | last_touched=2026-04-06 | next_action=2026-05-05 | escalate_after_days=28
- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7

## Telegram Launch Scope

- launch_scope: excluded_until_task_080_done
- decision_date: 2026-03-03
- rationale: Telegram ingestion remains explicitly out of launch scope until the human-gated wiring/sign-off task closes.

## Completed This Sprint

- `TASK-371` Close Sprint 8 and seed Sprint 9 from the live backlog ✅
- `TASK-363` Add Behavior-Oriented Eval Suites for High-Risk LLM Safety Paths ✅
- `TASK-372` Tighten behavior eval restore/cache coverage ✅
- `TASK-364` Build a Runtime-to-Eval Regression Intake Loop ✅
