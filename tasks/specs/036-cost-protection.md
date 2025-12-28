# TASK-036: Cost Protection & Budget Limits

**Priority**: P1 (Critical)
**Estimate**: 2-3 hours
**Dependencies**: TASK-013 (Tier 1), TASK-014 (Tier 2)

## Overview

Prevent runaway API costs from bugs, infinite loops, or high-volume news events (e.g., election night, breaking crisis). A personal project should never wake up to a $500 API bill.

## Problem Statement

Without cost protection:
- A bug in RSS fetcher could loop infinitely
- A major news event could generate 10x normal volume
- No visibility into spend until monthly invoice

## Implementation

### 1. Cost Tracking Table

```sql
CREATE TABLE api_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    tier VARCHAR(20) NOT NULL,  -- 'tier1', 'tier2', 'embedding'
    call_count INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd DECIMAL(10, 4) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(date, tier)
);

CREATE INDEX idx_api_usage_date ON api_usage(date);
```

### 2. Cost Tracker Service

```python
# src/processing/cost_tracker.py

from datetime import date
from decimal import Decimal

from src.core.config import settings

# Approximate costs per 1M tokens (as of 2025)
COST_PER_1M_TOKENS = {
    "tier1": {"input": Decimal("0.25"), "output": Decimal("1.25")},   # Haiku
    "tier2": {"input": Decimal("3.00"), "output": Decimal("15.00")},  # Sonnet
    "embedding": {"input": Decimal("0.10"), "output": Decimal("0")},
}


class CostTracker:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_budget(self, tier: str) -> tuple[bool, str | None]:
        """
        Check if we're within budget for this tier.

        Returns:
            (allowed, reason) - allowed=False means budget exceeded
        """
        today = date.today()
        usage = await self._get_or_create_usage(today, tier)

        # Check call limits
        limits = {
            "tier1": settings.TIER1_MAX_DAILY_CALLS,
            "tier2": settings.TIER2_MAX_DAILY_CALLS,
            "embedding": settings.EMBEDDING_MAX_DAILY_CALLS,
        }

        limit = limits.get(tier, 0)
        if limit > 0 and usage.call_count >= limit:
            return False, f"{tier} daily call limit ({limit}) exceeded"

        # Check total daily cost
        total_cost = await self._get_total_cost_today()
        if settings.DAILY_COST_LIMIT_USD > 0:
            if total_cost >= Decimal(str(settings.DAILY_COST_LIMIT_USD)):
                return False, f"Daily cost limit (${settings.DAILY_COST_LIMIT_USD}) exceeded"

        return True, None

    async def record_usage(
        self,
        tier: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record API usage and update costs."""
        today = date.today()
        usage = await self._get_or_create_usage(today, tier)

        # Calculate cost
        rates = COST_PER_1M_TOKENS.get(tier, {"input": Decimal("0"), "output": Decimal("0")})
        cost = (
            (Decimal(input_tokens) / 1_000_000) * rates["input"] +
            (Decimal(output_tokens) / 1_000_000) * rates["output"]
        )

        # Update usage
        usage.call_count += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.estimated_cost_usd += cost
        usage.updated_at = datetime.utcnow()

        # Check alert threshold
        await self._check_alert_threshold()

    async def get_daily_summary(self) -> dict:
        """Get today's usage summary."""
        today = date.today()
        result = await self.session.execute(
            select(ApiUsage).where(ApiUsage.date == today)
        )
        usages = result.scalars().all()

        return {
            "date": today.isoformat(),
            "tiers": {u.tier: {
                "calls": u.call_count,
                "cost_usd": float(u.estimated_cost_usd),
            } for u in usages},
            "total_cost_usd": sum(float(u.estimated_cost_usd) for u in usages),
            "budget_remaining_usd": max(0, settings.DAILY_COST_LIMIT_USD - sum(
                float(u.estimated_cost_usd) for u in usages
            )),
        }
```

### 3. Integration with LLM Classifier

```python
# In src/processing/llm_classifier.py

class LLMClassifier:
    async def classify_tier1(self, items: list[RawItem]) -> list[Tier1Result]:
        # Check budget BEFORE making call
        allowed, reason = await self.cost_tracker.check_budget("tier1")
        if not allowed:
            logger.warning("Budget exceeded, entering sleep mode", reason=reason)
            raise BudgetExceededError(reason)

        # Make API call
        response = await self.client.messages.create(...)

        # Record usage AFTER call
        await self.cost_tracker.record_usage(
            tier="tier1",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        return results
```

### 4. Sleep Mode Behavior

When budget is exceeded:
1. Log warning with details
2. Skip all LLM processing
3. Continue ingesting items (stored as `status=pending`)
4. Resume processing when budget resets (midnight UTC)

```python
class BudgetExceededError(Exception):
    """Raised when API budget is exceeded."""
    pass

# In processing pipeline
async def process_item(item: RawItem) -> None:
    try:
        result = await classifier.classify_tier1([item])
    except BudgetExceededError:
        # Leave item as pending, will retry tomorrow
        logger.info("Item queued for tomorrow due to budget", item_id=item.id)
        return
```

### 5. CLI Command

```bash
# Check current budget status
horadus budget status

# Output:
# Daily Budget Status (2025-01-15)
# ================================
# Tier 1 (Haiku):   142/1000 calls  ($0.18)
# Tier 2 (Sonnet):   28/200 calls   ($1.42)
# Embeddings:        89/500 calls   ($0.02)
# --------------------------------
# Total:            $1.62 / $5.00 (32%)
# Status:           ACTIVE
```

## Acceptance Criteria

- [ ] `api_usage` table created via migration
- [ ] `CostTracker` service with `check_budget()` and `record_usage()`
- [ ] All LLM calls check budget before execution
- [ ] Calls record usage after execution
- [ ] `BudgetExceededError` raised when limits hit
- [ ] Pipeline gracefully handles budget exceeded (items stay pending)
- [ ] Alert logged when reaching threshold (80% by default)
- [ ] `GET /api/v1/budget` endpoint returns daily summary
- [ ] Unit tests for CostTracker
- [ ] Integration test: simulate budget exceeded

## Configuration

Already added to `src/core/config.py`:

```python
TIER1_MAX_DAILY_CALLS: int = 1000      # ~$0.25/day max
TIER2_MAX_DAILY_CALLS: int = 200       # ~$3.00/day max
EMBEDDING_MAX_DAILY_CALLS: int = 500   # ~$0.05/day max
DAILY_COST_LIMIT_USD: float = 5.0      # Hard limit
COST_ALERT_THRESHOLD_PCT: int = 80     # Alert at 80%
```

## Edge Cases

1. **Midnight rollover**: Budget resets at midnight UTC, pending items automatically processed
2. **Partial batch**: If budget exceeded mid-batch, remaining items stay pending
3. **Config = 0**: Setting limit to 0 means unlimited (disabled)
4. **Token estimation**: Use actual response tokens, not estimates

## Testing

```python
@pytest.mark.asyncio
async def test_budget_exceeded():
    tracker = CostTracker(session)

    # Simulate hitting limit
    for _ in range(settings.TIER2_MAX_DAILY_CALLS):
        await tracker.record_usage("tier2", 1000, 500)

    allowed, reason = await tracker.check_budget("tier2")
    assert allowed is False
    assert "limit" in reason.lower()
```
