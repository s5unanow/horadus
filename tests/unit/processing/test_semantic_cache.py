from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.processing.semantic_cache import LLMSemanticCache

pytestmark = pytest.mark.unit


@dataclass(slots=True)
class _FakeRedisPipeline:
    client: _FakeRedisClient
    operations: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def setex(self, key: str, ttl_seconds: int, value: str) -> _FakeRedisPipeline:
        self.operations.append(("setex", (key, ttl_seconds, value)))
        return self

    def zadd(self, key: str, mapping: dict[str, float]) -> _FakeRedisPipeline:
        self.operations.append(("zadd", (key, mapping)))
        return self

    def expire(self, key: str, ttl_seconds: int) -> _FakeRedisPipeline:
        self.operations.append(("expire", (key, ttl_seconds)))
        return self

    def zcard(self, key: str) -> _FakeRedisPipeline:
        self.operations.append(("zcard", (key,)))
        return self

    def zrem(self, key: str, *members: str) -> _FakeRedisPipeline:
        self.operations.append(("zrem", (key, *members)))
        return self

    def delete(self, *keys: str) -> _FakeRedisPipeline:
        self.operations.append(("delete", keys))
        return self

    def execute(self) -> list[Any]:
        results: list[Any] = []
        for operation, args in self.operations:
            method = getattr(self.client, operation)
            results.append(method(*args))
        return results


@dataclass(slots=True)
class _FakeRedisClient:
    values: dict[str, str] = field(default_factory=dict)
    zsets: dict[str, dict[str, float]] = field(default_factory=dict)

    def pipeline(self, transaction: bool = True) -> _FakeRedisPipeline:
        _ = transaction
        return _FakeRedisPipeline(client=self)

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        _ = ttl_seconds
        self.values[key] = value
        return True

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[member] = float(score)
        return len(mapping)

    def expire(self, key: str, ttl_seconds: int) -> bool:
        _ = key, ttl_seconds
        return True

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def zrange(self, key: str, start: int, end: int) -> list[str]:
        bucket = self.zsets.get(key, {})
        ordered = sorted(bucket.items(), key=lambda item: item[1])
        window = ordered[start : end + 1] if end >= 0 else ordered[start:]
        return [member for member, _score in window]

    def zrem(self, key: str, *members: str) -> int:
        bucket = self.zsets.setdefault(key, {})
        removed = 0
        for member in members:
            if member in bucket:
                bucket.pop(member, None)
                removed += 1
        return removed

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.values:
                self.values.pop(key, None)
                removed += 1
        return removed


def test_build_cache_key_is_stable_for_payload_key_order() -> None:
    key_one = LLMSemanticCache.build_cache_key(
        stage="tier1",
        model="gpt-4.1-nano",
        prompt_template="prompt",
        payload={"b": 2, "a": 1},
        redis_prefix="cache",
    )
    key_two = LLMSemanticCache.build_cache_key(
        stage="tier1",
        model="gpt-4.1-nano",
        prompt_template="prompt",
        payload={"a": 1, "b": 2},
        redis_prefix="cache",
    )

    assert key_one == key_two


def test_build_cache_key_changes_for_model_and_prompt_versions() -> None:
    base_key = LLMSemanticCache.build_cache_key(
        stage="tier2",
        model="gpt-4.1-mini",
        prompt_template="prompt-v1",
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    model_changed = LLMSemanticCache.build_cache_key(
        stage="tier2",
        model="gpt-4o-mini",
        prompt_template="prompt-v1",
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    prompt_changed = LLMSemanticCache.build_cache_key(
        stage="tier2",
        model="gpt-4.1-mini",
        prompt_template="prompt-v2",
        payload={"event_id": "1"},
        redis_prefix="cache",
    )

    assert model_changed != base_key
    assert prompt_changed != base_key


def test_semantic_cache_get_set_and_eviction() -> None:
    fake_redis = _FakeRedisClient()
    cache = LLMSemanticCache(
        enabled=True,
        ttl_seconds=3600,
        max_entries=1,
        redis_prefix="cache",
        redis_client=fake_redis,
    )
    payload_one = {"item_id": "1"}
    payload_two = {"item_id": "2"}

    initial = cache.get(
        stage="tier1",
        model="gpt-4.1-nano",
        prompt_template="prompt",
        payload=payload_one,
    )
    assert initial is None

    cache.set(
        stage="tier1",
        model="gpt-4.1-nano",
        prompt_template="prompt",
        payload=payload_one,
        value='{"items":[{"item_id":"1"}]}',
    )
    first_hit = cache.get(
        stage="tier1",
        model="gpt-4.1-nano",
        prompt_template="prompt",
        payload=payload_one,
    )
    assert first_hit == '{"items":[{"item_id":"1"}]}'

    cache.set(
        stage="tier1",
        model="gpt-4.1-nano",
        prompt_template="prompt",
        payload=payload_two,
        value='{"items":[{"item_id":"2"}]}',
    )
    evicted = cache.get(
        stage="tier1",
        model="gpt-4.1-nano",
        prompt_template="prompt",
        payload=payload_one,
    )
    second_hit = cache.get(
        stage="tier1",
        model="gpt-4.1-nano",
        prompt_template="prompt",
        payload=payload_two,
    )
    assert evicted is None
    assert second_hit == '{"items":[{"item_id":"2"}]}'
