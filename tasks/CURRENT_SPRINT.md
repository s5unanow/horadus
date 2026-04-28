# Current Sprint

**Sprint Goal**: Convert vetted intake into concrete workflow hardening, type-safety cleanup, and docs/runtime alignment while keeping speculative chat-hook work out of the active lane.
**Sprint Number**: 10
**Sprint Dates**: 2026-04-21 to 2026-05-04
**Source-of-truth policy**: See `AGENTS.md` -> `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

## Selection Notes

- Sprint 10 opens immediately after Sprint 9 drained, using a fresh review of the local intake queue instead of carrying forward already-completed work.
- Promoted intake focused on reproduced issues across ledger integrity, intake concurrency, planning validation, privileged-write type safety, Decimal typing, chat-session guardrails, and operator/docs drift.
- `INTAKE-0006` remains pending as an umbrella concern because `TASK-390` and `TASK-394` capture the concrete mitigation and design work first.
- `INTAKE-0007` remains pending because Codex hook enforcement is still speculative and not yet backed by a stable repo-owned contract.
- `INTAKE-0022` remains pending as second-order regression hardening behind the reproduced workflow drift already scheduled here.
- The sequence front-loads repo-truth and fail-closed workflow fixes, then narrower typing and guardrail tasks, then operator/docs alignment, and leaves the worktree-isolation design task last so it can reuse what the earlier guardrail work clarifies.

## Suggested Sequence

1. `TASK-396` Upgrade python-dotenv to 1.2.2 for dependency audit parity.
2. `TASK-386` Fix task intake id allocation under concurrent writes.
3. `TASK-387` Fail closed on spec files missing Planning Gates.
4. `TASK-388` Remove Any erasure from trend-write mutations.
5. `TASK-389` Align Numeric ORM typing with Decimal semantics.
6. `TASK-390` Add dirty-main watchdog for agent sessions.
7. `TASK-391` Close nested-helper docstring policy gap.
8. `TASK-392` Fix root horadus help and runbook freshness drift.
9. `TASK-393` Sync API docs with runtime contracts.
10. `TASK-394` Design worktree isolation for Codex App task sessions.

## Human Blocker Metadata

## Completed This Sprint

- `TASK-395` Close Sprint 9 and seed Sprint 10 from vetted intake ✅
- `TASK-385` Reconcile task ledger lifecycle drift ✅
- `TASK-396` Upgrade python-dotenv to 1.2.2 for dependency audit parity ✅
- `TASK-386` Fix task intake id allocation under concurrent writes ✅
- `TASK-397` Clear local-gate blockers surfaced by TASK-387 ✅
- `TASK-387` Fail closed on spec files missing Planning Gates ✅
- `TASK-388` Remove Any erasure from trend-write mutations ✅
- `TASK-389` Align Numeric ORM typing with Decimal semantics ✅
- `TASK-390` Add dirty-main watchdog for agent sessions ✅
- `TASK-391` Close nested-helper docstring policy gap ✅
- `TASK-392` Fix root horadus help and runbook freshness drift ✅
- `TASK-393` Sync API docs with runtime contracts ✅
- `TASK-394` Design worktree isolation for Codex App task sessions ✅
- `TASK-398` Fix eval benchmark noop session contract ✅
- `TASK-399` Prevent integration Docker volume leaks ✅
- `TASK-400` Correct golden-set factual and taxonomy drift ✅
- `TASK-401` Resolve pip dependency-audit CVE blocker ✅
- `TASK-402` Widen golden-set coverage for weak trends ✅
