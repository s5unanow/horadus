# TASK-248: Evaluate `gpt-5-nano` with Minimal Reasoning for Tier-1

## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: Done

## Goal (1-3 lines)

Decide whether Tier-1 should move from `gpt-4.1-nano` to `gpt-5-nano`, and
specifically whether `minimal` or `low` reasoning is the better fit for
high-volume routing.

## Scope

- In scope:
  - Reuse the shared GPT-5 benchmark artifact from `TASK-247`
  - Record Tier-1-specific recommendation and caveats
- Out of scope:
  - New benchmark harness features beyond what landed in `TASK-247`
  - Runtime rollout plumbing (`TASK-249`)

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-07: Close this task from the cache-disabled `TASK-247` artifact instead of rerunning a duplicate benchmark, because the artifact already compares `gpt-5-nano` `minimal` vs `low` on the same human-verified slice against the current Tier-2 baseline.
- 2026-03-07: Recommend `gpt-5-nano` with `minimal` reasoning as the Tier-1 target after `TASK-249`; it beat both `gpt-4.1-nano` and `gpt-5-nano` `low` on failure rate and queue accuracy in the sampled benchmark.

## Risks / Foot-guns

- Tier-1 cost numbers for failure-heavy configs remain lower bounds because current benchmark usage accounting does not capture spend after parse/alignment failures.
- Runtime switch still depends on first-class reasoning/temperature controls landing in `TASK-249`.

## Validation Commands

- `uv run --no-sync python scripts/check_docs_freshness.py`

## Notes / Links

- Shared artifact: `ai/eval/results/benchmark-20260307T155840Z-a166f992.json`
- Tier-1 summary from that artifact:
  - baseline `gpt-4.1-nano`: `failures=10`, `queue_accuracy=0.0`, `elapsed_seconds=116.424501`
  - `gpt-5-nano` `minimal`: `failures=1`, `queue_accuracy=0.9`, `elapsed_seconds=166.944487`
  - `gpt-5-nano` `low`: `failures=2`, `queue_accuracy=0.8`, `elapsed_seconds=203.411731`
