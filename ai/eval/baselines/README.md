# Baseline Benchmarks

Store accepted benchmark baselines here as committed JSON artifacts.

Suggested convention:
- `current.json` - latest accepted baseline used for prompt-change comparison
- `history/<date>-<tag>.json` - archived prior baselines and intentional milestone snapshots worth keeping in git

Source artifacts come from:
- `ai/eval/results/benchmark-*.json`
- `ai/eval/results/*.json` remains ignored by git; promotion into this directory is the only supported path for committing eval artifacts.

When promoting a prompt change:
1. Run audit + benchmark.
2. Verify dataset metadata compatibility (`dataset_scope`, `gold_set_fingerprint_sha256`, `gold_set_item_ids_sha256`).
3. Verify provenance compatibility (`source_control`, `prompt_provenance`, `trend_config_provenance`, and per-config invocation metadata).
4. Approve candidate results.
5. Move the previous `current.json` into `history/`.
6. Copy accepted benchmark JSON into this folder as `current.json` and commit it.

When gold-set rows/labels change:
- Previous baseline comparisons are superseded for pass/fail gating.
- Keep older baseline files in `history/` for historical reference only.
