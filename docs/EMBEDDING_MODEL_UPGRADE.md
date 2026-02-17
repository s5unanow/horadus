# Embedding Model Upgrade Runbook

## Goal

Upgrade `EMBEDDING_MODEL` without silently mixing vector spaces across
deduplication and clustering.

## Safety Guarantees

- Every stored embedding now carries lineage metadata:
  - `embedding_model`
  - `embedding_generated_at`
- Similarity comparisons run only when model identifiers match.
- Cross-model comparisons are skipped fail-safe.

## Operator Check Command

Run:

```bash
uv run horadus eval embedding-lineage --target-model text-embedding-3-small
```

Optional CI/gate mode:

```bash
uv run horadus eval embedding-lineage --fail-on-mixed
```

The command reports:
- per-entity vector counts (`raw_items`, `events`)
- vectors already on target model
- vectors with other models
- vectors missing lineage
- estimated re-embed scope

## Upgrade Procedure

1. **Prepare**
   - Choose new embedding model.
   - Set `EMBEDDING_MODEL` in environment.
   - Deploy code that includes lineage fields and cross-model safety checks.
2. **Baseline audit**
   - Run `horadus eval embedding-lineage` and capture counts.
3. **Backfill `raw_items` first**
   - Re-embed source items to target model in controlled batches.
   - Keep existing dedup logic; embedding comparisons only occur within same model.
4. **Backfill `events` second**
   - Recompute event embeddings from canonical summaries after raw-item backfill.
5. **Verify**
   - Re-run lineage command.
   - Expect `other_models=0`, `missing_model=0`, `reembed_scope=0`.
6. **Finalize**
   - Keep target model as default in environment/config.

## Rollback

If quality or cost regress:

1. Revert `EMBEDDING_MODEL` to prior model.
2. Re-run lineage report to understand mixed-state scope.
3. Re-embed affected vectors back to the previous model in batches.
4. Confirm with `horadus eval embedding-lineage`.

During rollback, similarity paths remain safe because cross-model comparisons are
blocked.
