# TASK-076: Trend Taxonomy Contract and Gold-Set Validation Gate

## Objective

Prevent silent drift between trend configuration and evaluation datasets by
introducing a deterministic taxonomy-validation gate.

## Scope

- Trend taxonomy validation for `config/trends/*.yaml`
- Gold-set compatibility validation for `tier1` and `tier2` labels
- CI/local quality-gate integration
- Tests and operator documentation

## Deliverables

1. Taxonomy validator
- Load and validate all trend YAML files via `TrendConfig`
- Build canonical configured trend-ID set from YAML `id`
- Fail on duplicate or missing trend IDs

2. Gold-set compatibility checks
- Validate every `tier2.trend_id` is in configured trend IDs
- Validate `tier1.trend_scores` keys match configured trend IDs in strict mode
- Provide a documented lenient/subset mode for partial datasets when needed

3. Signal-type alignment checks
- Validate `tier2.signal_type` exists in `indicators` for its `trend_id`
- Support strict-fail or warning mode (default and rationale documented)

4. Tooling integration
- Add a reusable command/script (and optional Make target)
- Integrate into local/CI quality-gate flow

5. Test coverage
- Unit tests for success path
- Unit tests for duplicate/missing trend IDs
- Unit tests for unknown `tier2.trend_id`
- Unit tests for `tier1.trend_scores` key mismatch
- Unit tests for unknown signal types

## Out of Scope

- Human judgment on trend quality/content (`[REQUIRES_HUMAN]` domains)
- Automatic rewriting of trend IDs in existing datasets
- Automatic migration/backfill of historical evidence rows

## Acceptance Criteria

- Validation gate deterministically fails on taxonomy or schema-drift conditions.
- Unknown `trend_id` values cannot pass silently in gold-set checks.
- Trend-score key mismatches are surfaced with actionable diagnostics.
- Signal-type mismatches are surfaced and configurable as strict/warn.
- Gate is runnable locally and in CI with documented commands.
