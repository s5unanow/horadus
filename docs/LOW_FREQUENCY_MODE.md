# Low-Frequency Operations (6-Hour Mode)

## Baseline Profile

Use this profile for the intended low-frequency operating mode:

```dotenv
RSS_COLLECTION_INTERVAL=360
GDELT_COLLECTION_INTERVAL=360
PROCESS_PENDING_INTERVAL_MINUTES=15
PROCESSING_PIPELINE_BATCH_SIZE=200
INGESTION_WINDOW_OVERLAP_SECONDS=300
```

Source-window defaults:
- RSS: `default_max_items_per_fetch=200` (`config/sources/rss_feeds.yaml`)
- GDELT: `default_lookback_hours=12` (`config/sources/gdelt_queries.yaml`)

Per-source overrides remain available:
- RSS feed-level `max_items_per_fetch`
- GDELT query-level `lookback_hours`, `max_records_per_page`, `max_pages`

## Catch-Up Runbook (Service Down Multiple Days)

1. **Increase source windows temporarily**
   - Raise GDELT query `lookback_hours` for affected queries.
   - Raise RSS `max_items_per_fetch` for high-volume feeds.
2. **Run collectors manually**
   - Keep workers running, then trigger ingestion bursts:
   ```bash
   uv run celery -A src.workers.celery_app call workers.collect_rss
   uv run celery -A src.workers.celery_app call workers.collect_gdelt
   ```
3. **Drain processing backlog in bounded batches**
   ```bash
   uv run celery -A src.workers.celery_app call workers.process_pending_items --args='[200]'
   ```
   Repeat until pending backlog stabilizes.
4. **Return to baseline**
   - Revert temporary source-window overrides.
   - Keep 6-hour schedule defaults.
5. **Verify freshness SLO recovery**
   ```bash
   uv run horadus eval source-freshness --fail-on-stale
   ```

Deduplication and pipeline idempotency remain authoritative during overlap/catch-up runs.
