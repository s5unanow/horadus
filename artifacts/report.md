# Horadus Workflow Friction Summary - 2026-03-08

- Report date (UTC): `2026-03-08`
- Summary window: `2026-03-08T00:00:00Z` to `2026-03-09T00:00:00Z`
- Source log: `artifacts/agent/horadus-cli-feedback/entries.jsonl`
- Summary path: `artifacts/report.md`
- Entries summarized: `9`
- Distinct grouped patterns: `9`

## Highlights
- Most common friction type: `forced_fallback` (`8` entries).
- Candidate CLI/skill improvements surfaced: `9`.
- Human review is required before turning any candidate below into a backlog task.

## Grouped Patterns
### 1. `forced_fallback` x1
- Candidate improvement: Allow safe-start/task eligibility to consume an explicit context pack or staged sprint intake without requiring unrelated planning commits
- Command attempted: `uv run --no-sync horadus tasks safe-start TASK-268 --name detached-head-lifecycle`
- Fallback used: `git switch -c codex/task-268-detached-head-lifecycle after stashing pre-existing sprint/backlog intake edits`
- Affected tasks: `TASK-268`
- Observed notes: safe-start rejected TASK-268 because the sprint intake existed only as uncommitted planning edits, so the CLI could not see the active task on clean main
### 2. `forced_fallback` x1
- Candidate improvement: Let finish reuse a shorter allow-timeout for the review gate when no actionable current-head review comments exist, or surface a non-blocking prompt instead of idling for the full timeout.
- Command attempted: `uv run --no-sync horadus tasks finish TASK-271`
- Fallback used: `gh pr merge 205 --squash --delete-branch`
- Affected tasks: `TASK-271`
- Observed notes: finish waited on the review gate for a full 600s timeout even though checks were green and the standalone review gate with timeout-policy=allow immediately allowed continuation because no bot review existed
### 3. `forced_fallback` x1
- Candidate improvement: Teach finish to short-circuit the allow-timeout review-gate path when no actionable current-head review comments exist, so it can merge immediately after checks are green.
- Command attempted: `uv run --no-sync horadus tasks finish TASK-272`
- Fallback used: `gh pr merge 206 --squash --delete-branch`
- Affected tasks: `TASK-272`
- Observed notes: reused the manual merge fallback because finish currently spends the full review-gate timeout waiting for a bot review even when timeout-policy=allow would permit immediate continuation after checks pass
### 4. `forced_fallback` x1
- Candidate improvement: Have finish treat the allow-timeout review gate as an immediate non-blocking check when no actionable current-head review comments exist, so merge can proceed once checks are green.
- Command attempted: `uv run --no-sync horadus tasks finish TASK-274`
- Fallback used: `gh pr merge 207 --squash --delete-branch`
- Affected tasks: `TASK-274`
- Observed notes: continued using the manual merge fallback because finish still waits on the review gate's full bot-review timeout even after required checks pass and the allow-timeout policy would permit immediate continuation
### 5. `forced_fallback` x1
- Candidate improvement: Allow finish to short-circuit the review gate immediately when timeout-policy=allow and there are no actionable current-head review comments.
- Command attempted: `uv run --no-sync horadus tasks finish TASK-251`
- Fallback used: `gh pr merge 208 --squash --delete-branch`
- Affected tasks: `TASK-251`
- Observed notes: kept using the manual merge fallback because finish still idles through the full review-gate bot timeout after checks are green
### 6. `unexpected_blocker` x1
- Candidate improvement: Treat clean Codex issue comments for the current head as satisfying the finish review gate, or trigger an actual review event before timing out.
- Command attempted: `uv run --no-sync horadus tasks finish TASK-275`
- Fallback used: `none (blocked on clean Codex issue comment)`
- Affected tasks: `TASK-275`
- Observed notes: Codex posted a clean issue comment instead of a current-head PR review, so the finish review gate timed out.
### 7. `forced_fallback` x1
- Candidate improvement: Support a documented staged-intake workflow or an override path for newly queued tasks that must carry their intake edits on the first implementation branch.
- Command attempted: `uv run --no-sync horadus tasks safe-start TASK-277 --name workflow-completeness`
- Fallback used: `uv run --no-sync horadus tasks start TASK-277 --name workflow-completeness`
- Affected tasks: `TASK-277`
- Observed notes: Canonical safe-start could not see TASK-277 because the sprint/backlog intake existed only as uncommitted local edits that needed to travel with the first task branch.
### 8. `forced_fallback` x1
- Candidate improvement: fail fast after the configured review timeout window elapses, surface the blocking step, and only continue waiting when a concrete in-progress action is detected
- Command attempted: `uv run --no-sync horadus tasks finish TASK-282`
- Fallback used: `manual gh pr merge and local main sync`
- Affected tasks: `TASK-282`
- Observed notes: finish exceeded the default 600-second review gate with PR #216 still OPEN, checks green, and no reviews/comments
### 9. `forced_fallback` x1
- Candidate improvement: make the finish command transition deterministically from review-timeout allow to merge-or-blocked-exit instead of idling after the timeout window elapses
- Command attempted: `uv run --no-sync horadus tasks finish TASK-283`
- Fallback used: `manual gh pr merge and local main sync after repeated post-timeout hang`
- Affected tasks: `TASK-283`
- Observed notes: finish remained running for more than 10 minutes after the silent-timeout allow window on PR #217 even though checks were green, the PR was clean, and current-head review comments were resolved

## Candidate Improvements
1. Allow finish to short-circuit the review gate immediately when timeout-policy=allow and there are no actionable current-head review comments.
Seen in `1` entries across `TASK-251`.
Friction mix: `forced_fallback` x1
Related commands: `uv run --no-sync horadus tasks finish TASK-251`
2. Allow safe-start/task eligibility to consume an explicit context pack or staged sprint intake without requiring unrelated planning commits
Seen in `1` entries across `TASK-268`.
Friction mix: `forced_fallback` x1
Related commands: `uv run --no-sync horadus tasks safe-start TASK-268 --name detached-head-lifecycle`
3. fail fast after the configured review timeout window elapses, surface the blocking step, and only continue waiting when a concrete in-progress action is detected
Seen in `1` entries across `TASK-282`.
Friction mix: `forced_fallback` x1
Related commands: `uv run --no-sync horadus tasks finish TASK-282`
4. Have finish treat the allow-timeout review gate as an immediate non-blocking check when no actionable current-head review comments exist, so merge can proceed once checks are green.
Seen in `1` entries across `TASK-274`.
Friction mix: `forced_fallback` x1
Related commands: `uv run --no-sync horadus tasks finish TASK-274`
5. Let finish reuse a shorter allow-timeout for the review gate when no actionable current-head review comments exist, or surface a non-blocking prompt instead of idling for the full timeout.
Seen in `1` entries across `TASK-271`.
Friction mix: `forced_fallback` x1
Related commands: `uv run --no-sync horadus tasks finish TASK-271`
6. make the finish command transition deterministically from review-timeout allow to merge-or-blocked-exit instead of idling after the timeout window elapses
Seen in `1` entries across `TASK-283`.
Friction mix: `forced_fallback` x1
Related commands: `uv run --no-sync horadus tasks finish TASK-283`
7. Support a documented staged-intake workflow or an override path for newly queued tasks that must carry their intake edits on the first implementation branch.
Seen in `1` entries across `TASK-277`.
Friction mix: `forced_fallback` x1
Related commands: `uv run --no-sync horadus tasks safe-start TASK-277 --name workflow-completeness`
8. Teach finish to short-circuit the allow-timeout review-gate path when no actionable current-head review comments exist, so it can merge immediately after checks are green.
Seen in `1` entries across `TASK-272`.
Friction mix: `forced_fallback` x1
Related commands: `uv run --no-sync horadus tasks finish TASK-272`
9. Treat clean Codex issue comments for the current head as satisfying the finish review gate, or trigger an actual review event before timing out.
Seen in `1` entries across `TASK-275`.
Friction mix: `unexpected_blocker` x1
Related commands: `uv run --no-sync horadus tasks finish TASK-275`

## Triage Guidance
- Review this summary before proposing workflow follow-up work.
- Do not auto-create backlog tasks from this report; backlog creation requires explicit human review.
- Use the raw JSONL log only when deeper evidence is needed for a reviewed follow-up.

## Proposed Follow-Up Seeds (Human Review Required)
- Candidate task seed: Investigate Horadus workflow friction around Allow finish to short-circuit the review gate immediately when timeout-policy=allow and there are no actionable current-head review comments..
- Candidate task seed: Investigate Horadus workflow friction around Allow safe-start/task eligibility to consume an explicit context pack or staged sprint intake without requiring unrelated planning commits.
- Candidate task seed: Investigate Horadus workflow friction around fail fast after the configured review timeout window elapses, surface the blocking step, and only continue waiting when a concrete in-progress action is detected.
- Candidate task seed: Investigate Horadus workflow friction around Have finish treat the allow-timeout review gate as an immediate non-blocking check when no actionable current-head review comments exist, so merge can proceed once checks are green..
- Candidate task seed: Investigate Horadus workflow friction around Let finish reuse a shorter allow-timeout for the review gate when no actionable current-head review comments exist, or surface a non-blocking prompt instead of idling for the full timeout..
- Candidate task seed: Investigate Horadus workflow friction around make the finish command transition deterministically from review-timeout allow to merge-or-blocked-exit instead of idling after the timeout window elapses.
- Candidate task seed: Investigate Horadus workflow friction around Support a documented staged-intake workflow or an override path for newly queued tasks that must carry their intake edits on the first implementation branch..
- Candidate task seed: Investigate Horadus workflow friction around Teach finish to short-circuit the allow-timeout review-gate path when no actionable current-head review comments exist, so it can merge immediately after checks are green..
- Candidate task seed: Investigate Horadus workflow friction around Treat clean Codex issue comments for the current head as satisfying the finish review gate, or trigger an actual review event before timing out..
