# TASK-307: Make `horadus tasks finish` Behave Like a Stateful Review Loop

## Status

- Owner: Codex
- Started: 2026-03-12
- Current state: Done
- Planning Gates: Required — shared finish/review workflow semantics with CLI, script, and docs callers

## Goal (1-3 lines)

Make `horadus tasks finish` behave like the intended merge/review loop instead
of a single passive wait. Preserve merge safety while allowing early merge on a
qualifying positive review signal, explicit actionable-comment feedback, and a
fresh review window after PR updates. A scoped internal refactor of the
review/merge subflow into named phases/states is allowed when it is the
smallest safe way to make those transitions explicit.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-307`)
  - canonical finish/review policy in `AGENTS.md`
  - public workflow/operator guidance in `README.md`
  - operator command index in `docs/AGENT_RUNBOOK.md`
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `scripts/check_pr_review_gate.py`
  - `ops/skills/horadus-cli/SKILL.md`
  - `ops/skills/horadus-cli/references/commands.md`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/unit/scripts/test_check_pr_review_gate.py`
  - `tests/workflow/`
- Preconditions/dependencies:
  - `TASK-307` must be placed in `tasks/CURRENT_SPRINT.md` or otherwise explicitly authorized before guarded task start, because canonical `safe-start` enforces sprint eligibility
  - preserve required-check safety and stale-head protection
  - preserve the canonical 600-second default timeout unless a human explicitly changes it
  - preserve the current `REVIEW_TIMEOUT_POLICY=allow` invariant for `horadus tasks finish` unless a separate task explicitly changes that policy
  - preserve current blocking semantics for actionable current-head review feedback
  - preserve current task-close / head-alignment requirements before merge
  - preserve the documented recovery path that allows rerunning `horadus tasks finish TASK-XXX` from `main` with an explicit task id after an interrupted finish run

## Outputs

- Expected behavior/artifacts:
  - finish may merge early on a qualifying positive review signal only when required checks are green on the current PR head
  - the existing full-wait silent-timeout path remains valid: after the canonical 600-second review window expires with no actionable current-head review feedback, finish may still continue when the current head remains otherwise merge-safe
  - actionable current-head review comments stop finish with explicit next-step guidance for the agent feedback loop
  - after a mechanically detectable reviewed-head change, the canonical finish flow owns the fresh re-review request for the new PR head and starts a fresh review window rather than silently relying on the earlier wait cycle
  - the existing same-head fresh-review request path remains valid when the review gate times out and unresolved current-head review threads still block merge
  - the contract for comment response / thread resolution / re-review is explicit in code and in canonical workflow policy docs
  - review-gate success is based on current-head review semantics, not merely the absence of inline comments
  - malformed or incomplete required-check / review payloads fail closed on the merge path instead of silently allowing merge
  - the `pr_review_gate.py` to `finish` interface is explicit and machine-consumable enough that finish does not depend on brittle stdout wording
  - interrupted finish runs may still be resumed canonically from `main` by rerunning `horadus tasks finish TASK-XXX`
  - already-merged PR convergence and `gh pr merge --auto` fallback behavior remain intact
- Validation evidence:
  - regression coverage for the early thumbs-up path on a green PR
  - regression coverage for actionable current-head review comment blocking
  - regression coverage for the post-update fresh-review-window path
  - regression coverage for the preserved same-head timeout/thread re-review path
  - unaffected-caller regression for the shared review-gate script surface

## Non-Goals

- Explicitly excluded work:
  - changing the default 600-second review timeout
  - changing the current `REVIEW_TIMEOUT_POLICY=allow` contract for finish
  - bypassing required checks, stale-head protection, or merge policy
  - fully autonomous code-change generation inside `finish` itself
  - rewriting all of `finish_task_data()` into a general-purpose FSM framework
  - redesigning unrelated PR creation or task-start behavior

## Scope

- In scope:
  - define the exact conditions for an early positive-review merge fast-path
  - define how actionable review comments are surfaced back into the canonical agent loop
  - define how an updated PR re-enters review and restarts the canonical wait window
  - define whether reply / thread-resolution behavior remains an agent step or becomes a first-class CLI capability
  - refresh and revalidate the PR head across the review-wait / merge boundary
  - tighten review success semantics so current-head `CHANGES_REQUESTED` or equivalent negative review signals cannot pass as “clean”
  - require truly green required checks for the early-merge path and the post-review merge step
  - keep required-check and unresolved-thread parsing fail-closed on the merge path
  - update docs and tests to match the final finish-loop contract
- Out of scope:
  - unrelated `horadus tasks` commands
  - broad GitHub review UX redesign outside finish/review-gate semantics
  - changes to wrapper scripts that do not participate in finish or review-gate behavior

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: keep `finish` as the canonical orchestrator, but make its review gate stateful enough to merge early on a green positive signal and to restart the review window after PR updates
- Preserved existing behavior: the full-wait silent-timeout-allow path remains part of canonical finish semantics when the current head is still merge-safe after the review window expires
- Accepted internal refactor shape: the review/merge subflow may be rewritten into explicit named phases/states inside the existing finish implementation if that is the smallest safe way to remove hidden transitions and duplicated guard logic
- Accepted boundary rule: the `pr_review_gate.py` -> `finish` boundary must have an explicit stable contract (structured output and/or stable exit-code mapping), not ad hoc phrase parsing
- Rejected simpler alternative: keep the current full-timeout-only behavior and rely on humans to infer when to rerun `finish`; that preserves the known workflow gap
- First integration proof: current `TASK-306` behavior proves stale-thread cleanup works, but thumbs-up still waits the full timeout and re-review is still a manual rerun convention rather than an explicit finish-loop contract
- Additional accepted safety rule: an early thumbs-up fast path is only valid if the command has revalidated the current PR head and confirmed that required checks are still green for that same head
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - run canonical sequencing/context commands before implementation:
     - `uv run --no-sync horadus tasks preflight`
     - `uv run --no-sync horadus tasks safe-start TASK-307 --name <short-name>`
     - `uv run --no-sync horadus tasks context-pack TASK-307`
   - enumerate every caller that depends on shared finish/review-gate behavior before changing it, including:
     - `horadus tasks finish`
     - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
     - `tools/horadus/python/horadus_workflow/repo_workflow.py`
     - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
     - `scripts/check_pr_review_gate.py`
     - `tests/unit/scripts/test_check_pr_review_gate.py`
     - finish-path tests in `tests/horadus_cli/v2/test_cli.py`
     - workflow review-gate tests in `tests/workflow/`
     - the “resume from main with explicit task id” recovery path and its CLI regression coverage
   - inventory the current `pr_review_gate.py` -> `finish` contract:
     - exit codes
     - stdout phrases currently parsed by `finish`
     - any wrapper-script expectations around the same outputs
   - define current-head semantics for:
     - qualifying positive review signal
     - actionable review comments
     - review state / summary-only negative feedback
     - outdated vs current unresolved review threads
     - mechanically detectable “reviewed head changed after a blocking review cycle”
   - define how the existing silent-timeout-allow path coexists with the new early positive-signal path so the task does not accidentally narrow finish semantics
   - inventory every place that snapshots or validates PR head/check state today, including:
     - initial branch/PR head alignment before waiting
     - `pr_review_gate.py` head resolution
     - post-review required-check validation
   - decide the explicit contract for comment response / thread resolution:
     - agent-only step
     - CLI-assisted step
     - or mixed model
   - define the exact fresh-review trigger after PR updates and how the new review window begins
   - express the fresh-review trigger in mechanically detectable terms, not intent language:
     - e.g. a previous blocking review cycle tied to reviewed head `A`, followed by a later run where the PR head is `B != A`
   - define the existing same-head fresh-review trigger explicitly:
     - review gate timed out on head `A`
     - unresolved current-head review threads still block merge on the same head `A`
     - `finish` may request fresh review again without requiring a head change
   - define a single owner for re-review requests after PR updates:
      - canonical rule: `horadus tasks finish` owns the fresh re-review request for a new reviewed head
      - agent responsibility stops at addressing feedback, pushing, and rerunning `horadus tasks finish TASK-XXX`
   - define the dedupe contract for fresh review requests so the CLI does not ask twice for the same PR head
   - choose the durable source of truth for dedupe across separate CLI invocations, keyed by PR head SHA
   - decide the fail-closed contract for:
      - malformed `gh pr checks --json` payloads
      - incomplete or failed review-thread queries on the merge path
      - incomplete or failed `/reviews` and `/comments` queries used for current-head review semantics
      - incomplete or failed reactions queries used for the positive-signal fast path
   - decide the completeness contract for review-thread queries:
      - explicit pagination strategy
      - explicit handling when GitHub returns only a partial thread/comment window
   - decide the completeness contract for `/reviews` and `/comments` queries as well:
     - explicit pagination strategy
     - explicit handling when GitHub returns only a partial review/comment window
   - decide the completeness contract for reactions queries as well:
     - explicit pagination strategy
     - explicit handling when GitHub returns only a partial reactions window
   - define which pre-merge validations must be rerun after any PR-head refresh, including:
      - branch/PR head alignment
      - task-close-state presence on the refreshed PR head
      - required-check state for the refreshed PR head
   - decide whether the review/merge segment should remain sequential imperative code or be expressed as named phases/states; if the latter is chosen, keep the phase set narrow and local to finish behavior only
   - define reviewer-scope behavior explicitly:
     - default configured reviewer is `chatgpt-codex-connector[bot]`
     - if custom `REVIEW_BOT_LOGIN` is set, define whether fresh re-review requests are supported, skipped, or fail closed with explicit operator guidance
   - confirm that the task preserves:
     - the current timeout-policy invariant (`allow` only)
     - the current “resume from main with explicit task id” recovery path
     - the existing “already merged” convergence path
     - the existing `--auto` fallback when direct merge is not permitted by branch policy
   - inventory the Horadus CLI skill surfaces that describe `finish` today so the task updates only finish-specific behavior deltas and does not expand the skill into a second workflow-policy owner

2. Implement
   - if needed for safety/clarity, refactor the review/merge subflow into explicit named phases/states such as:
     - await-checks
     - await-review
     - blocked-on-feedback
     - refresh-head
     - verify-merge-readiness
     - merge
     - sync-main
   - keep that refactor scoped to the review/merge subflow rather than introducing a general FSM framework for unrelated finish behavior
   - update review-gate logic so a qualifying positive review signal may pass immediately when the current head already has green required checks
   - preserve the existing silent-timeout-allow path after the full canonical review window when no actionable current-head review feedback appears and the current head remains merge-safe
   - keep actionable current-head review comments as immediate blockers
   - make review-gate success depend on current-head review semantics, not only the absence of inline comments:
      - summary-only negative review state must still block
      - `CHANGES_REQUESTED` on the current head must still block
   - replace brittle stdout phrase parsing between `pr_review_gate.py` and `finish` with an explicit contract:
     - stable exit-code mapping plus structured output, or
     - a machine-readable JSON result consumed by `finish`
   - refresh or re-resolve PR head state after the wait window and before merge so the command cannot merge a different head than the one it validated
   - rerun the pre-merge task-close-state / head-alignment validations after any PR-head refresh so merge still targets a head that already contains the required task-close ledger/archive state
   - make finish output explicit about the current feedback loop when comments block:
      - review comments found
      - agent must address or dismiss them
      - rerun `horadus tasks finish TASK-XXX` after pushing updates
   - make the post-update path explicit:
     - `horadus tasks finish` requests fresh review when the mechanically defined reviewed-head-change condition is met
     - start a fresh 600-second review window for the new head
     - dedupe fresh review requests per PR head so rerunning `finish` does not emit duplicate asks for the same head
     - store or discover that dedupe state from a durable source visible across separate CLI invocations
     - do not require the agent to separately request re-review in the canonical path
     - define the fallback/no-op contract for custom non-Codex reviewers explicitly
   - preserve the existing same-head fresh-review path when:
     - the review gate timed out
     - unresolved current-head threads still block merge
     - a fresh review request is still needed even though the PR head did not change
   - if thread resolution remains an agent step, document that clearly; if CLI support is added, make it first-class and tested
   - keep stale-thread handling from `TASK-306` compatible with the new loop semantics
   - preserve the existing recovery path that allows the operator/agent to rerun `horadus tasks finish TASK-XXX` from `main` with an explicit task id
   - update canonical workflow policy text in `AGENTS.md` to match the final finish-loop behavior:
     - early positive-signal merge contract
     - actionable review-feedback contract
     - fresh re-review ownership / dedupe contract
   - update `README.md` anywhere it still carries workflow-facing finish guidance so it stays aligned with the final finish-loop behavior
   - update the thin Horadus CLI skill surfaces to reflect the new finish behavior only:
     - early-merge fast path on a green current head
     - preserved full-wait silent-timeout-allow path
     - CLI-owned fresh re-review request after PR updates
     - agent responsibility to address feedback, push, and rerun `horadus tasks finish TASK-XXX`
   - keep the skill/rule split intact:
     - `AGENTS.md` remains the canonical workflow-policy owner
     - the skill stays a thin procedural helper and command reference
   - tighten required-check handling so:
     - the fast path requires green, not merely non-red
     - malformed/non-list checks payloads do not pass open
     - post-review merge does not proceed while required checks are still pending on the current head
   - tighten unresolved-thread handling on the merge path so GraphQL/query failure does not silently erase blockers when finish is about to merge
   - require explicit pagination/completeness handling for review-thread queries so merge-path blocker detection does not silently miss threads outside the first response window
   - require explicit pagination/completeness handling for `/reviews` and `/comments` queries so current-head review semantics are not based on partial data
   - require explicit pagination/completeness handling for reactions queries so the early positive-signal path is not based on partial data
   - preserve the existing “already merged” convergence behavior and branch-policy `--auto` fallback when direct merge is rejected

3. Validate
   - add regression coverage for:
      - green PR + qualifying thumbs-up -> early merge fast-path
      - current-head thumbs-up with pending checks -> no early merge
      - full review window expires with no actionable current-head feedback and green checks -> merge may still continue
      - actionable current-head review comments -> immediate block with explicit next-step guidance
      - current-head `CHANGES_REQUESTED` or summary-only negative review -> block
      - PR head changes during the review wait -> fresh head must be revalidated before merge
      - PR head changes during the review wait -> refreshed head must still contain task-close state before merge
      - mechanically detected reviewed-head change -> CLI-owned fresh review request / fresh timeout window
      - rerunning `finish` on the same updated PR head -> no duplicate fresh review request
      - silent-timeout + unresolved current-head threads on the same head -> fresh review request still occurs
      - default reviewer path vs custom reviewer path follows the documented contract
      - stale-thread-only path remains non-blocking
      - malformed required-check payload on merge path -> fail closed
      - incomplete or paginated review-thread results -> finish does not silently treat the PR as unblocked
      - incomplete or paginated `/reviews` or `/comments` results -> finish does not silently treat the PR as reviewed/unblocked
      - incomplete or paginated reactions results -> finish does not silently trigger or skip the positive-signal fast path incorrectly
      - `pr_review_gate.py` output/exit-code contract remains consumable by `finish`
      - interrupted finish run resumed from `main` with explicit task id still works
      - invalid/non-allow timeout policy is still rejected on the finish path
      - already merged PR still converges cleanly
      - `gh pr merge --auto` fallback still works when direct merge is rejected by branch policy
      - if phases/states are introduced, at least one test proves the expected state progression on a representative happy path and one blocker path
   - add at least one unaffected-caller regression for the shared review-gate script surface:
     - `tests/unit/scripts/test_check_pr_review_gate.py`
   - verify canonical policy/docs are updated and aligned:
      - `AGENTS.md`
      - `README.md`
      - `docs/AGENT_RUNBOOK.md`
      - `tools/horadus/python/horadus_workflow/repo_workflow.py`
      - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
      - `ops/skills/horadus-cli/SKILL.md`
      - `ops/skills/horadus-cli/references/commands.md`
   - rerun finish/review-gate workflow tests and the canonical local gate

4. Ship (PR, checks, merge, main sync)
   - close task ledgers on-branch
   - open ready PR with canonical metadata
   - complete merge through `horadus tasks finish TASK-307`
   - verify `uv run --no-sync horadus tasks lifecycle TASK-307 --strict`

## Decisions (Timestamped)

- 2026-03-12: Treat this as a finish-loop behavior task, not just a review-gate micro-fix, because the missing semantics span early positive-signal merge, actionable comment handoff, and fresh review windows after PR updates
- 2026-03-12: Early merge on thumbs-up is allowed only when required checks are already green on the current PR head

## Risks / Foot-guns

- Early positive-signal merge can bypass actionable feedback if current-head semantics are sloppy -> define current-head matching explicitly and regression-test both pass and block paths
- A fresh-review loop can become ambiguous after PR updates -> define the exact rerun/request-review contract in code and docs
- Changing shared review-gate behavior can silently break wrapper/script callers -> enumerate callers and keep an unaffected-caller regression
- Over-automating comment response or thread resolution can hide real review discussion -> make the contract explicit and narrow
- PR head can drift during the wait window -> refresh/revalidate head + checks before merge
- Fail-open parsing of checks or thread payloads can merge unsafe PRs -> fail closed on malformed/incomplete merge-path data
- Partial review-thread pagination can hide unresolved blockers -> make completeness explicit and fail closed when the thread view is not authoritative
- Ambiguous re-review ownership can produce duplicate asks or no ask at all -> make `finish` the single owner and dedupe requests per PR head
- A short-lived CLI cannot dedupe re-review asks without durable state -> choose an explicit PR-visible or otherwise durable source of truth keyed by head SHA
- Supporting custom reviewers can silently diverge from the Codex-only path -> define and test the non-default reviewer contract explicitly
- Partial `/reviews` or `/comments` data can misclassify review state -> treat review-signal completeness the same way as thread completeness
- Partial reactions data can misclassify the early positive-signal path -> treat reaction completeness explicitly and fail closed
- Intent language around “updated in response to review” is not observable -> define the trigger in head-SHA and prior-blocking-run terms
- Over-focusing on head-change re-review can regress the existing same-head timeout/thread retry path -> preserve and test both re-review triggers explicitly

## Validation Commands

- `uv run --no-sync python scripts/check_docs_freshness.py`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_cli.py -k "finish or review_gate" -q`
- `uv run --no-sync pytest tests/unit/scripts/test_check_pr_review_gate.py -q`
- `uv run --no-sync pytest tests/workflow -q -k "finish or review_gate"`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `scripts/check_pr_review_gate.py`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/unit/scripts/test_check_pr_review_gate.py`
  - `AGENTS.md`
  - `README.md`
  - `docs/AGENT_RUNBOOK.md`
  - `ops/skills/horadus-cli/SKILL.md`
  - `ops/skills/horadus-cli/references/commands.md`
