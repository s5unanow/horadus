# Baseline Benchmarks

Store accepted benchmark baselines here as committed JSON artifacts.

Suggested convention:
- `current.json` - latest accepted baseline used for prompt-change comparison
- `history/<date>-<tag>.json` - optional archived prior baselines

Source artifacts come from:
- `ai/eval/results/benchmark-*.json`

When promoting a prompt change:
1. Run audit + benchmark.
2. Approve candidate results.
3. Copy accepted benchmark JSON into this folder and commit it.
