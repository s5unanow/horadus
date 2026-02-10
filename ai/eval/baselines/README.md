# Baseline Benchmarks

Store accepted benchmark baselines here as committed JSON artifacts.

Suggested convention:
- `current.json` - latest accepted baseline used for prompt-change comparison
- `history/<date>-<tag>.json` - optional archived prior baselines

Source artifacts come from:
- `ai/eval/results/benchmark-*.json`

When promoting a prompt change:
1. Run audit + benchmark.
2. Verify dataset metadata compatibility (`dataset_scope`, `gold_set_fingerprint_sha256`, `gold_set_item_ids_sha256`).
3. Approve candidate results.
4. Move the previous `current.json` into `history/`.
5. Copy accepted benchmark JSON into this folder as `current.json` and commit it.

When gold-set rows/labels change:
- Previous baseline comparisons are superseded for pass/fail gating.
- Keep older baseline files in `history/` for historical reference only.
