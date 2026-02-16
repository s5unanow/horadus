"""
Redis-backed semantic cache for Tier-1/Tier-2 LLM outputs.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import redis
import structlog

from src.core.config import settings
from src.core.observability import record_llm_semantic_cache_lookup

logger = structlog.get_logger(__name__)


class LLMSemanticCache:
    """Optional cross-worker semantic cache for LLM JSON outputs."""

    _DEGRADE_RETRY_SECONDS = 30

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        ttl_seconds: int | None = None,
        max_entries: int | None = None,
        redis_prefix: str | None = None,
        redis_url: str | None = None,
        redis_client: redis.Redis[str] | None = None,
        wall_time_fn: Any | None = None,
    ) -> None:
        self.enabled = settings.LLM_SEMANTIC_CACHE_ENABLED if enabled is None else bool(enabled)
        self.ttl_seconds = max(
            1,
            settings.LLM_SEMANTIC_CACHE_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds),
        )
        self.max_entries = max(
            1,
            settings.LLM_SEMANTIC_CACHE_MAX_ENTRIES if max_entries is None else int(max_entries),
        )
        self.redis_prefix = (
            settings.LLM_SEMANTIC_CACHE_REDIS_PREFIX
            if redis_prefix is None
            else str(redis_prefix).strip()
        )
        if not self.redis_prefix:
            self.redis_prefix = "horadus:llm_semantic_cache"
        self.redis_url = settings.REDIS_URL if redis_url is None else str(redis_url).strip()
        self._redis_client = redis_client
        self._backend_unavailable_until = 0.0
        self._wall_time_fn = wall_time_fn or time.time

    @staticmethod
    def build_cache_key(
        *,
        stage: str,
        model: str,
        prompt_template: str,
        payload: Any,
        redis_prefix: str,
    ) -> str:
        prompt_hash = hashlib.sha256(prompt_template.strip().encode("utf-8")).hexdigest()
        payload_hash = hashlib.sha256(
            LLMSemanticCache._serialize_payload(payload).encode("utf-8")
        ).hexdigest()
        return f"{redis_prefix}:{stage}:v1:{model.strip()}:{prompt_hash}:{payload_hash}"

    def get(
        self,
        *,
        stage: str,
        model: str,
        prompt_template: str,
        payload: Any,
    ) -> str | None:
        if not self.enabled:
            return None

        key = self.build_cache_key(
            stage=stage,
            model=model,
            prompt_template=prompt_template,
            payload=payload,
            redis_prefix=self.redis_prefix,
        )
        now = self._wall_time_fn()
        if now < self._backend_unavailable_until:
            return None

        try:
            client = self._get_redis_client()
            value = client.get(key)
            if isinstance(value, str) and value.strip():
                record_llm_semantic_cache_lookup(stage=stage, result="hit")
                return value
            record_llm_semantic_cache_lookup(stage=stage, result="miss")
            return None
        except Exception:
            self._backend_unavailable_until = now + self._DEGRADE_RETRY_SECONDS
            record_llm_semantic_cache_lookup(stage=stage, result="miss")
            logger.warning(
                "Semantic cache backend unavailable; bypassing",
                stage=stage,
                retry_after_seconds=self._DEGRADE_RETRY_SECONDS,
            )
            return None

    def set(
        self,
        *,
        stage: str,
        model: str,
        prompt_template: str,
        payload: Any,
        value: str,
    ) -> None:
        if not self.enabled:
            return

        now = self._wall_time_fn()
        if now < self._backend_unavailable_until:
            return

        key = self.build_cache_key(
            stage=stage,
            model=model,
            prompt_template=prompt_template,
            payload=payload,
            redis_prefix=self.redis_prefix,
        )
        index_key = f"{self.redis_prefix}:index:{stage}"

        try:
            client = self._get_redis_client()
            pipeline = client.pipeline(transaction=True)
            pipeline.setex(key, self.ttl_seconds, value)
            pipeline.zadd(index_key, {key: now})
            pipeline.expire(index_key, self.ttl_seconds * 2)
            pipeline.zcard(index_key)
            _set_result, _zadd_result, _expire_result, current_size_raw = pipeline.execute()

            current_size = int(current_size_raw or 0)
            overflow = current_size - self.max_entries
            if overflow <= 0:
                return

            evicted_keys = client.zrange(index_key, 0, overflow - 1)
            if not evicted_keys:
                return
            eviction_pipeline = client.pipeline(transaction=True)
            eviction_pipeline.zrem(index_key, *evicted_keys)
            eviction_pipeline.delete(*evicted_keys)
            eviction_pipeline.execute()
        except Exception:
            self._backend_unavailable_until = now + self._DEGRADE_RETRY_SECONDS
            logger.warning(
                "Semantic cache write failed; bypassing",
                stage=stage,
                retry_after_seconds=self._DEGRADE_RETRY_SECONDS,
            )

    def _get_redis_client(self) -> redis.Redis[str]:
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.1,
                socket_timeout=0.1,
            )
        return self._redis_client

    @staticmethod
    def _serialize_payload(payload: Any) -> str:
        return json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
