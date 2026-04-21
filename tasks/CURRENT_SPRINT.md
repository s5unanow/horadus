# Current Sprint

**Sprint Goal**: Strengthen evaluation and code-health guardrails, improve review/authoring ergonomics, and carry forward the held RFC-001 planning blocker without forcing it into autonomous work.
**Sprint Number**: 9
**Sprint Dates**: 2026-04-21 to 2026-05-04
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

## Selection Notes

- Sprint 9 opened immediately after Sprint 8 with a nine-task queue from the live backlog plus one carried-forward human blocker.
- `TASK-376`, `TASK-377`, and `TASK-378` were promoted from current-head review follow-ups on `TASK-369`, `TASK-255`, and `TASK-368`; keep them in Sprint 9 so those repo-workflow fixes stay adjacent to the work that surfaced them.
- The selected queue focuses first on behavior evals and deterministic code-health guardrails, then on review/authoring workflow polish.
- `TASK-373` is an in-sprint blocker-clear task added after the sprint reset because the repo-wide dependency audit now fails on an upstream-fixed `cryptography` CVE and prevents strict local-gate completion for active work.
- `TASK-366` should land before `TASK-367`, `TASK-369` should reuse the changed-file/code-health output once it exists, and `TASK-376` should ship after `TASK-369` because it reports that enriched-review behavior accurately.
- `TASK-288` received in-thread human approval on 2026-04-19 for amended RFC-001 Option A; the resulting Phase 1 queue is now the autonomous implementation lane.
- RFC-001 Phase 1 remains CLI-first: implement mode lands before metadata extraction, evals land before workflow callers switch, and policy-doc front matter remains deferred.
- Open tasks not listed here remain in `tasks/BACKLOG.md` and are not considered closed or descoped by this sprint reset.

## Suggested Sequence

1. `TASK-363` Add behavior-oriented eval suites for high-risk LLM safety paths.
2. `TASK-364` Build a runtime-to-eval regression intake loop.
3. `TASK-366` Add a code-health erosion eval for changed Python surfaces.
4. `TASK-373` Bump cryptography to 46.0.7 for dependency audit.
5. `TASK-367` Ratchet changed-file code-health regressions in local gates.
6. `TASK-368` Enforce hotspot-touch debt capture for allowlisted production files.
7. `TASK-369` Make local pre-push review slop-aware for changed files.
8. `TASK-255` Add a targeted docstring quality gate for high-value surfaces.
9. `TASK-377` Close docstring-policy gap in make check.
10. `TASK-378` Accept completed hotspot follow-up task references.
11. `TASK-376` Align local-review telemetry with prompt enrichment.
12. `TASK-334` Align Gemini local-review approval-mode flags with installed CLI.
13. `TASK-288` Finalize the amended RFC-001 Option A implementation queue.
14. `TASK-380` Add implement-mode context-pack contract while preserving broad default output.
15. `TASK-381` Add task-spec retrieval metadata and deterministic canonical spec resolution.
16. `TASK-365` Add retrieval behavior evals for the implement-mode context surfaces.
17. `TASK-383` Switch canonical agent workflow callers to implement-mode context-pack after caller audit and eval coverage.

## Human Blocker Metadata

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
- `TASK-366` Add a Code-Health Erosion Eval for Changed Python Surfaces ✅
- `TASK-373` Bump cryptography to 46.0.7 for dependency audit ✅
- `TASK-367` Ratchet Changed-File Code-Health Regressions in Local Gates ✅
- `TASK-368` Enforce Hotspot-Touch Debt Capture for Allowlisted Production Files ✅
- `TASK-374` Add /ship-it task completion workflow ✅
- `TASK-375` Bump pytest to 9.0.3 for dependency audit ✅
- `TASK-369` Make Local Pre-Push Review Slop-Aware for Changed Files ✅
- `TASK-255` Add a Targeted Docstring Quality Gate for High-Value Surfaces ✅
- `TASK-379` Sync newly created review follow-up tasks into Sprint 9 ✅
- `TASK-376` Align local-review telemetry with prompt enrichment ✅
- `TASK-377` Close docstring-policy gap in make check ✅
- `TASK-378` Accept completed hotspot follow-up task references ✅
- `TASK-334` Align Gemini local-review approval-mode flags with installed CLI ✅
- `TASK-288` Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue [REQUIRES_HUMAN] ✅
- `TASK-380` Add Implement-Mode Context-Pack Contract ✅
- `TASK-381` Add Retrieval Metadata and Canonical Spec Resolution ✅
- `TASK-382` Add Task-Scoped Sprint Orientation and Test Candidates ✅
- `TASK-365` Add Retrieval Behavior Evals for RFC-001 Context Surfaces ✅
- `TASK-383` Switch Agent Workflow Surfaces to Implement Context-Pack Mode ✅
