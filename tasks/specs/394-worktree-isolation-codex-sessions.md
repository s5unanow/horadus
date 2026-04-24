---
task_id: TASK-394
retrieval:
  kind: task-spec
  status: active
  canonical: true
  supersedes: []
  superseded_by: null
---

# TASK-394: Worktree Isolation for Codex App Task Sessions

## Problem Statement

Codex chat and automation sessions currently start from the canonical Horadus
checkout at `/Users/s5una/projects/horadus`. The repo now has a dirty-main
watchdog and a strict task-branch lifecycle, but those controls still assume
that the long-lived checkout is the place where an agent reads, branches, edits,
pushes, merges, and resyncs.

That works, but it leaves a containment gap: accidental tracked edits, generated
artifacts, local virtualenv/cache churn, interrupted sessions, and branch locks
can all land in the canonical checkout before a task-specific boundary exists.
The next step should be a repo-owned worktree strategy that preserves the
existing Horadus task lifecycle while moving mutable task execution into a
disposable sibling worktree.

## Inputs

- Canonical workflow and task completion policy in `AGENTS.md`
- Operator command index in `docs/AGENT_RUNBOOK.md`
- Desired-state Codex automation specs in `ops/automations/specs/`
- Current guarded task start and finish commands:
  - `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
  - `uv run --no-sync horadus tasks finish TASK-XXX`
  - `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`
- Existing cleanup rule from `TASK-384`: lifecycle completion does not
  automatically own arbitrary local worktree deletion.

## Outputs

- This concrete task spec for worktree-isolated Codex chat/task sessions
- Runbook and policy pointers that make the design discoverable during
  operator and agent work
- A staged rollout recommendation that keeps today's `safe-start` and `finish`
  behavior authoritative until a repo-owned CLI wrapper implements the
  worktree flow

## Non-Goals

- Implementing a new `horadus tasks worktree-start` command in this task
- Changing current `safe-start`, `finish`, or lifecycle verifier behavior
- Rewriting existing Codex automation desired-state TOMLs to use worktree
  execution before the repo has a cleanup-aware start wrapper
- Making Codex App hooks or host-level workspace provisioning mandatory

**Planning Gates**: Required - shared workflow/operator guidance change

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: Document the smallest safe operating model first: a sibling
  disposable worktree per task, with existing Horadus lifecycle commands still
  owning branch/PR/merge completion.
- `Anti-Abstraction Gate`: Defer any new wrapper until it removes repeated
  operator steps. The first implementation should wrap `git worktree` plus the
  existing task lifecycle, not replace task policy.
- `Integration-First Gate`:
  - Validation target: docs and desired-state guidance agree that `safe-start`,
    `finish`, and `lifecycle --strict` remain authoritative.
  - Exercises: context-pack, branch start, local gate, finish, cleanup
    ownership, and automation `cwds` implications are explicitly covered.
- `Code Shape Gate`: Not applicable - no Python hotspot is changed.
- `Determinism Gate`: Triggered - task branch, worktree path, cleanup, and
  completion-state ownership must be deterministic and recoverable.
- `LLM Budget/Safety Gate`: Not applicable - no runtime LLM path is modified.
- `Observability Gate`: Triggered - the flow must report the canonical checkout,
  task worktree path, current branch, PR URL, cleanup state, and blocker when
  automation cannot continue.

## Design

### Containment Goals

- Keep the canonical checkout on `main` except while it is syncing after a
  completed merge.
- Run implementation, validation, commits, pushes, and PR repair work inside a
  task-owned worktree.
- Keep one task per branch and one branch per worktree.
- Keep generated artifacts and untracked scratch output out of the canonical
  checkout by default.
- Make interrupted work recoverable by task id, branch name, and worktree path.
- Keep cleanup explicit. Completion proves repo lifecycle state; deleting or
  switching a local worktree remains an operator-owned cleanup step unless a
  future command explicitly owns it.

### Proposed Layout

- Canonical checkout: `/Users/s5una/projects/horadus`
- Default disposable worktree root:
  `/Users/s5una/projects/horadus-worktrees/`
- Task worktree path:
  `/Users/s5una/projects/horadus-worktrees/TASK-XXX-short-name`
- Task branch:
  `codex/task-XXX-short-name`

The worktree root should live outside the repository so gitignored scratch state
or nested worktree metadata does not appear as repo-local noise.

### Lifecycle Integration

The eventual repo-owned start wrapper should behave like this:

1. Run from the canonical checkout only.
2. Assert the canonical checkout is on `main`, clean, and synced.
3. Run `uv run --no-sync horadus tasks eligibility TASK-XXX --format json`.
4. Run `uv run --no-sync horadus tasks context-pack TASK-XXX --mode implement --format json`.
5. Create a sibling worktree at the deterministic task path from synced `main`.
6. In that worktree, create or switch to `codex/task-XXX-short-name`.
7. Run the same guarded `safe-start` checks or shared lower-level preflight
   logic used by current `safe-start`.
8. Print a machine-readable summary with:
   - canonical checkout path
   - worktree path
   - branch name
   - task id
   - context-pack planning state
   - cleanup reminder

Implementation and validation then run inside the task worktree:

1. Apply task changes.
2. Run targeted validation and the canonical local gate.
3. Run `uv run --no-sync horadus tasks finish TASK-XXX` from the task
   worktree.
4. Run `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` from the
   canonical checkout after merge sync, or teach the future wrapper to delegate
   that final verification to the canonical checkout.

### Cleanup and Ownership

The cleanup contract should be explicit and conservative:

- `finish` owns branch/PR/merge/local-main-sync policy.
- `lifecycle --strict` owns the machine-checkable completion verdict.
- The worktree-start wrapper owns only worktree creation and recovery discovery.
- A future cleanup command may remove a disposable task worktree only after it
  confirms:
  - the task reached `local-main-synced`
  - the worktree has no tracked diffs
  - untracked files are absent or intentionally disposable
  - the task branch is not still checked out anywhere else

Until that cleanup command exists, agents and automations should report the
worktree path as a cleanup item instead of deleting it implicitly.

### Automation Implications

Current desired-state automation specs continue to use the canonical checkout in
`cwds` until a repo-owned worktree start wrapper exists. For task-mutating
automations such as `horadus-sprint-autopilot`, the staged target is:

- Keep `cwds = ["/Users/s5una/projects/horadus"]` for lock acquisition,
  idle-repo checks, eligibility, and wrapper invocation.
- Let the wrapper create or recover the task worktree.
- Continue the implementation run in the task worktree.
- Return to the canonical checkout for final lifecycle verification and main
  sync checks.

The existing `execution_environment = "worktree"` field in automation desired
state should not be treated as sufficient by itself for Horadus task isolation.
It does not define the branch naming, task id, cleanup, or lifecycle-verifier
contract that this repo needs.

## Staged Rollout Recommendation

1. Phase 0 - Documentation contract:
   - Land this spec and the matching runbook/policy pointers.
   - Keep existing task execution on the current guarded branch flow.
2. Phase 1 - CLI wrapper:
   - Add `horadus tasks worktree-start TASK-XXX --name short-name`.
   - Reuse existing eligibility, context-pack, and guarded start policy.
   - Add tests for existing `safe-start` callers so the wrapper does not
     regress the current start path.
3. Phase 2 - Automation adoption:
   - Update `agents/automation/horadus-sprint-autopilot.md` to invoke the
     wrapper.
   - Keep canonical checkout lock acquisition and idle checks before creating a
     task worktree.
   - Teach failure reporting to include the task worktree path and cleanup
     state.
4. Phase 3 - Cleanup helper:
   - Add a recovery/cleanup command that lists task worktrees and removes only
     verified disposable worktrees.
   - Keep destructive cleanup opt-in and explicit.

## Acceptance Criteria

- [ ] A canonical task spec defines the worktree isolation model for Codex chat
      sessions.
- [ ] The design covers containment goals, lifecycle integration points,
      cleanup and ownership implications, automation implications, and a staged
      rollout path.
- [ ] Operator-facing docs point to the design and state that current
      `safe-start`/`finish` semantics remain authoritative until the wrapper is
      implemented.

## Validation

- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Gate Outcomes / Waivers

- Targeted test proof: N/A - this task creates the design contract and docs
  only; it does not change Python code, task workflow implementation, or
  automation sync behavior.
- Integration proof: N/A - this task does not change integration-covered or
  push/PR workflow implementation paths.
