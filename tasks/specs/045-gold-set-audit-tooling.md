# TASK-045: Gold-Set Quality Audit Tooling

## Objective

Add a deterministic quality audit for `ai/eval/gold_set.jsonl` to detect
provenance and data-quality issues before benchmarking.

## Scope

- Dataset-level checks:
  - label provenance distribution (`label_verification`)
  - human-verified coverage
  - Tier-2 label coverage
  - duplicate content concentration
  - max-relevance label distribution
- JSON artifact output in `ai/eval/results/`.
- CLI entrypoint and Make target for routine operator use.

## Non-Goals

- Human labeling itself (covered by `TASK-044 [REQUIRES_HUMAN]`).
- Automatically rewriting dataset rows.

## Success Criteria

- Audit runs deterministically without external network access.
- Warning conditions are clearly listed and machine-readable.
- Optional fail mode supports gating workflows (`--fail-on-warnings`).
