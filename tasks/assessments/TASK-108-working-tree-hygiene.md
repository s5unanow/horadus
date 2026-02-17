# TASK-108 Working Tree Hygiene Audit and Disposition Plan

## Snapshot
- Date: 2026-02-17
- Branch at audit start: `main` (dirty state restored from `codex/stash-recovery-20260217`)
- Task branch for cleanup work: `codex/task-108-working-tree-hygiene`

## Inventory (Grouped)

### 1) Runtime / test / docs implementation deltas (tracked, modified)
**Files (25):**
- `.github/workflows/ci.yml`
- `Makefile`
- `README.md`
- `ai/eval/README.md`
- `config/sources/gdelt_queries.yaml`
- `config/sources/rss_feeds.yaml`
- `docs/DATA_MODEL.md`
- `docs/RELEASING.md`
- `pyproject.toml`
- `src/api/main.py`
- `src/api/routes/reports.py`
- `src/api/routes/trends.py`
- `src/eval/benchmark.py`
- `src/eval/vector_benchmark.py`
- `src/processing/deduplication_service.py`
- `src/processing/embedding_service.py`
- `tests/unit/api/test_reports.py`
- `tests/unit/api/test_trends.py`
- `tests/unit/core/test_report_generator.py`
- `tests/unit/core/test_retrospective_analyzer.py`
- `tests/unit/eval/test_benchmark.py`
- `tests/unit/eval/test_vector_benchmark.py`
- `tests/unit/processing/test_deduplication_service.py`
- `tests/unit/processing/test_embedding_service.py`
- `uv.lock`

**Likely provenance:** deferred post-recovery implementation for `TASK-113`, `TASK-114`, `TASK-115`.

**Recommended action:** `defer` (split into dedicated task branches and PRs by task scope; do not bulk-commit in TASK-108 branch).

---

### 2) Generated benchmark artifacts (untracked)
**Files (7):**
- `ai/eval/results/*.json` (timestamped benchmark/vector/audit outputs)

**Likely provenance:** local eval runs.

**Recommended action:** `drop` from working tree, keep outputs reproducible via CLI commands.

---

### 3) Human-supervised trend curation drafts (untracked)
**Files (26):**
- `config/trends/*.yaml` (16 files)
- `TODO_MINE_TRENDS.md`, `TODO_EXPERT_TRENDS.md`, `TODO_EXPERT_TRENDS_EN.md`
- `assess_human/*` (7 files)

**Likely provenance:** manual trend authoring and gold-set/trend research.

**Recommended action:** `defer` as human-gated content (`[REQUIRES_HUMAN]` adjacent scope); do not auto-commit without manual review/sign-off.

---

### 4) Product exploration notes (untracked)
**Files (8):**
- `docs/frontend-eval/*` (6 files)
- `frontend/README.md`
- `mobile/README.md`

**Likely provenance:** exploratory frontend/mobile planning.

**Recommended action:** `archive` unless there is an explicit backlog task to track this scope; if needed, reintroduce under a dedicated docs task.

## Root Causes
1. **Long-lived mixed-scope branch history** (`task-061` recovery tail + local carryover) reintroduced multi-task WIP into one tree.
2. **Generated outputs not cleaned post-run** left timestamped eval result files in repo.
3. **Human research drafts and exploratory notes** accumulated without explicit task/PR boundaries.
4. **Deferred implementation bundles** from recovery follow-up tasks (`TASK-113..115`) remained local instead of task-branch isolation.

## Risky Mismatches Flagged
- Task docs show `TASK-113`, `TASK-114`, and `TASK-115` as ready/open, while large portions of candidate implementation exist only in local unstaged state.
- Human-gated trend artifacts are present locally but not task-reviewed; committing them blindly would violate `[REQUIRES_HUMAN]` policy.
- Mixed runtime/docs/test changes in one dirty tree increase accidental cross-task commits.

## Cleanup Sequence (Concrete)
1. Keep safety checkpoint via named stash/branch backup before destructive cleanup.
2. Remove generated eval outputs (`ai/eval/results/*.json`) from working tree.
3. Keep `TASK-108` branch limited to hygiene artifacts only (this audit + minimal guard updates).
4. Split runtime implementation deltas into dedicated branches in priority order:
   - `TASK-113` eval/vector recovery
   - `TASK-114` docs freshness gate recovery
   - `TASK-115` tracing/lineage/grounding recovery
5. Keep trend-draft and human-assessment files blocked pending manual decision/sign-off.
6. Archive or drop exploratory frontend/mobile notes unless promoted to a scheduled backlog task.
7. Return to clean `main`, then continue one-task-per-branch execution.

## Actions Executed in This Task Branch
1. Captured non-TASK-108 mixed work into stash `task108-deferred-wip-split-2026-02-17` for safe later task-scope extraction.
2. Removed local `ai/eval/results/*.json` run artifacts from repo working tree and archived copies under `/tmp/horadus-task108-eval-results`.
3. Added `.gitignore` rule for `ai/eval/results/*.json` to reduce repeat artifact buildup.
