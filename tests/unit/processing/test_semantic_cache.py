from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

import src.processing.semantic_cache as semantic_cache_module
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


def test_build_cache_key_changes_for_provider_schema_and_request_overrides() -> None:
    base_key = LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        prompt_path="ai/prompts/tier2.md",
        prompt_template="prompt-v1",
        schema_name="tier2_event_classification",
        schema_payload={"type": "object"},
        request_overrides={"service_tier": "default"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    provider_changed = LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider="openai-secondary",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        prompt_path="ai/prompts/tier2.md",
        prompt_template="prompt-v1",
        schema_name="tier2_event_classification",
        schema_payload={"type": "object"},
        request_overrides={"service_tier": "default"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    schema_changed = LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        prompt_path="ai/prompts/tier2.md",
        prompt_template="prompt-v1",
        schema_name="tier2_event_classification",
        schema_payload={"type": "array"},
        request_overrides={"service_tier": "default"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    overrides_changed = LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        prompt_path="ai/prompts/tier2.md",
        prompt_template="prompt-v1",
        schema_name="tier2_event_classification",
        schema_payload={"type": "object"},
        request_overrides={"service_tier": "flex"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )

    assert provider_changed != base_key
    assert schema_changed != base_key
    assert overrides_changed != base_key


def test_semantic_cache_initialization_normalizes_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(semantic_cache_module.settings, "LLM_SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(semantic_cache_module.settings, "LLM_SEMANTIC_CACHE_TTL_SECONDS", 0)
    monkeypatch.setattr(semantic_cache_module.settings, "LLM_SEMANTIC_CACHE_MAX_ENTRIES", 0)
    monkeypatch.setattr(semantic_cache_module.settings, "LLM_SEMANTIC_CACHE_REDIS_PREFIX", " ")
    monkeypatch.setattr(semantic_cache_module.settings, "REDIS_URL", "redis://runtime")

    cache = LLMSemanticCache(redis_prefix=" ", redis_url=" ")

    assert cache.enabled is True
    assert cache.ttl_seconds == 1
    assert cache.max_entries == 1
    assert cache.redis_prefix == "horadus:llm_semantic_cache"
    assert cache.redis_url == ""


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


def test_semantic_cache_handles_disabled_and_backend_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup_events: list[tuple[str, str]] = []

    class _ExplodingRedisClient(_FakeRedisClient):
        def get(self, key: str) -> str | None:
            _ = key
            raise RuntimeError("boom")

        def pipeline(self, transaction: bool = True) -> _FakeRedisPipeline:
            _ = transaction
            raise RuntimeError("boom")

    monkeypatch.setattr(
        semantic_cache_module,
        "record_llm_semantic_cache_lookup",
        lambda *, stage, result: lookup_events.append((stage, result)),
    )

    disabled_cache = LLMSemanticCache(enabled=False, redis_client=_FakeRedisClient())
    assert (
        disabled_cache.get(
            stage="tier1",
            model="gpt",
            prompt_template="prompt",
            payload={"x": 1},
        )
        is None
    )
    disabled_cache.set(
        stage="tier1",
        model="gpt",
        prompt_template="prompt",
        payload={"x": 1},
        value="cached",
    )

    wall_clock = {"now": 100.0}
    cache = LLMSemanticCache(
        enabled=True,
        redis_client=_ExplodingRedisClient(),
        wall_time_fn=lambda: wall_clock["now"],
    )

    assert (
        cache.get(
            stage="tier2",
            model="gpt",
            prompt_template="prompt",
            payload={"x": 1},
        )
        is None
    )
    assert cache._backend_unavailable_until == 130.0
    wall_clock["now"] = 110.0
    assert (
        cache.get(
            stage="tier2",
            model="gpt",
            prompt_template="prompt",
            payload={"x": 1},
        )
        is None
    )
    cache.set(
        stage="tier2",
        model="gpt",
        prompt_template="prompt",
        payload={"x": 1},
        value="cached",
    )

    assert lookup_events == [("tier2", "miss")]


def test_semantic_cache_builds_redis_client_on_demand(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(
        semantic_cache_module.redis, "from_url", lambda *_args, **_kwargs: fake_redis
    )

    cache = LLMSemanticCache(enabled=True, redis_client=None, redis_url="redis://cache")

    assert cache._get_redis_client() is fake_redis


def test_semantic_cache_set_handles_empty_evictions_and_write_failures() -> None:
    class _NoEvictRedis(_FakeRedisClient):
        def zrange(self, key: str, start: int, end: int) -> list[str]:
            _ = key, start, end
            return []

    class _ExplodingPipelineRedis(_FakeRedisClient):
        def pipeline(self, transaction: bool = True) -> _FakeRedisPipeline:
            _ = transaction
            raise RuntimeError("boom")

    no_evict = LLMSemanticCache(
        enabled=True,
        max_entries=1,
        redis_prefix="cache",
        redis_client=_NoEvictRedis(),
    )
    no_evict.set(
        stage="tier1",
        model="gpt",
        prompt_template="prompt",
        payload={"x": 1},
        value="cached",
    )
    no_evict.set(
        stage="tier1",
        model="gpt",
        prompt_template="prompt",
        payload={"x": 2},
        value="cached-2",
    )

    failing = LLMSemanticCache(
        enabled=True,
        redis_client=_ExplodingPipelineRedis(),
        wall_time_fn=lambda: 10.0,
    )
    failing.set(
        stage="tier1",
        model="gpt",
        prompt_template="prompt",
        payload={"x": 1},
        value="cached",
    )

    assert failing._backend_unavailable_until == 40.0
