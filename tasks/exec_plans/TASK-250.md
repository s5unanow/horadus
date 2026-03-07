## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: Done

## Goal (1-3 lines)

Make eval artifacts trustworthy release evidence by adding enough provenance to
reproduce accepted runs exactly, while keeping timestamped exploratory outputs
ignored and limiting versioned artifacts to promoted baselines/history.

## Scope

- In scope:
  - Benchmark/audit artifact provenance for git state, prompt files, invocation config, and dataset/config scope
  - Shared helper(s) to keep benchmark/audit metadata aligned
  - Unit tests for the artifact contract
  - Docs for ignored exploratory artifacts vs committed promoted artifacts
- Out of scope:
  - Promoting a new eval baseline
  - Tracking all exploratory `ai/eval/results/*.json` artifacts in git

## Plan (Keep Updated)

1. Preflight (branch, context, current artifact contract) ✅
2. Implement shared artifact provenance helpers and wire benchmark/audit outputs ✅
3. Expand eval tests for strict provenance contract ✅
4. Update docs for promotion/commit policy ✅
5. Validate and ship in progress

## Decisions (Timestamped)

- 2026-03-07: Keep exploratory `ai/eval/results/*.json` ignored; make reproducibility come from richer metadata plus a single promotion path into committed baselines/history. (strict enough without turning the repo into an artifact dump)

## Risks / Foot-guns

- Git provenance helpers can become flaky outside a git checkout -> return explicit unavailable metadata instead of failing artifact generation.
- Benchmark and audit schemas can drift if provenance is duplicated -> centralize the shared pieces in one helper module.

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval/test_benchmark.py tests/unit/eval/test_audit.py -v`
- `uv run --no-sync ruff check src/eval/benchmark.py src/eval/audit.py src/eval/artifact_provenance.py tests/unit/eval/test_benchmark.py tests/unit/eval/test_audit.py`
- `uv run --no-sync ruff format --check src/eval/benchmark.py src/eval/audit.py src/eval/artifact_provenance.py tests/unit/eval/test_benchmark.py tests/unit/eval/test_audit.py`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `make agent-check`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-250`)
- Relevant modules: `src/eval/benchmark.py`, `src/eval/audit.py`, `docs/PROMPT_EVAL_POLICY.md`, `ai/eval/README.md`, `ai/eval/baselines/README.md`
- Validation summary:
  - `uv run --no-sync pytest tests/unit/eval/test_benchmark.py tests/unit/eval/test_audit.py -v`
  - `uv run --no-sync mypy src/`
  - `uv run --no-sync ruff check src/eval/artifact_provenance.py src/eval/benchmark.py src/eval/audit.py tests/unit/eval/test_benchmark.py tests/unit/eval/test_audit.py`
  - `uv run --no-sync ruff format --check src/eval/artifact_provenance.py src/eval/benchmark.py src/eval/audit.py tests/unit/eval/test_benchmark.py tests/unit/eval/test_audit.py`
  - `uv run --no-sync python scripts/check_docs_freshness.py`
  - `make agent-check`
