# TASK-111 Assessment: Main Branch Merge-Completeness Audit

**Date**: 2026-02-16  
**Target branch**: `main` (`origin/main`)  
**Objective**: verify whether backlog-tracked completed task work is merged to `main`.

## Method

1. Parsed completed task IDs from `tasks/COMPLETED.md`.
2. Enumerated remote task branches `origin/codex/task-*`.
3. Audited branch status against `origin/main`:
   - direct ancestor merge (`merge-base --is-ancestor`)
   - merged via PR with non-ancestor tip (squash/rewrite)
   - unmerged (no open/merged PR and not ancestor)
4. Correlated branch status with task IDs (from branch naming + commit/PR metadata).
5. Checked open PRs targeting `main`.

Raw machine-readable artifact: `tasks/assessments/TASK-111-main-merge-audit.json`.

## Snapshot

- Completed tasks tracked: **80**
- Remote task branches audited: **55**
- Open PRs to `main`: **0**
- Branch status:
  - `merged_ancestor`: **1**
  - `merged_via_squash_or_rewrite`: **52**
  - `open_pr_unmerged`: **0**
  - `no_pr_unmerged`: **2**

## Findings

### 1) Missing task functionality on `main`

**Result: none detected.**

No completed task produced a “missing merge” signal after correlating unmerged
branches with replacement merged branches/PRs.

### 2) Stale unmerged branches found (superseded, not missing functionality)

1. `origin/codex/task-039-calibration-runbook`  
   - latest commit: `4382340`  
   - PR: [#47](https://github.com/s5unanow/horadus/pull/47) (closed, not merged)  
   - superseded by: `origin/codex/task-039-calibration-runbook-2` via [#48](https://github.com/s5unanow/horadus/pull/48) (merged)

2. `origin/codex/task-054-llm-input-safety`  
   - latest commit: `8e15b23`  
   - PR: [#60](https://github.com/s5unanow/horadus/pull/60) (closed, not merged)  
   - superseded by: `origin/codex/task-054-llm-input-safety-v2` via [#61](https://github.com/s5unanow/horadus/pull/61) (merged)

### 3) Commit-text caveat

A commit-text grep for `TASK-XXX` on `main` misses **11** completed tasks. This
is expected for older commits where task IDs were not consistently included in
commit messages. It is not, by itself, evidence of missing merges.

## Conclusion

- **All completed backlog functionality appears merged into `main`.**
- There are **2 stale remote task branches** that are unmerged but explicitly
  superseded by merged replacement branches/PRs.

## Recommended cleanup

1. Delete stale remote branches:
   - `codex/task-039-calibration-runbook`
   - `codex/task-054-llm-input-safety`
2. Keep current hard workflow guards from `TASK-110` to prevent repeat drift.
