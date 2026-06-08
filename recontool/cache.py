"""Result caching for passive adapter outputs.

Caches adapter results with configurable TTL so that repeat scans against the
same target do not re-query providers unnecessarily.

Two backends:
    InMemoryCache - dict with expiry timestamps (single-process)
    RedisCache    - Redis GET/SET with native TTL (distributed)

Cache key format: recon:cache:{adapter_name}:{input_hash}:{scope_hash}
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "recon:cache"


def hash_inputs(inputs: dict[str, Any], scope_data: dict[str, Any]) -> str:
    """Produce a stable hash from adapter inputs and scope for cache keying."""
    payload = json.dumps({"inputs": inputs, "scope": scope_data}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class _CacheEntry:
    events: list[dict[str, Any]]
    expires_at: float


class InMemoryCache:
    """In-process result cache with TTL-based expiration."""

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}

    def _key(self, adapter_name: str, input_hash: str, scope_hash: str) -> str:
        return f"{_CACHE_PREFIX}:{adapter_name}:{input_hash}:{scope_hash}"

    async def get(
        self, adapter_name: str, input_hash: str, scope_hash: str
    ) -> list[dict[str, Any]] | None:
        key = self._key(adapter_name, input_hash, scope_hash)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._store[key]
            return None
        return entry.events

    async def set(
        self,
        adapter_name: str,
        input_hash: str,
        scope_hash: str,
        events: list[dict[str, Any]],
        ttl_seconds: int = 3600,
    ) -> None:
        key = self._key(adapter_name, input_hash, scope_hash)
        self._store[key] = _CacheEntry(
            events=events, expires_at=time.time() + ttl_seconds
        )

    async def invalidate(self, adapter_name: str) -> None:
        prefix = f"{_CACHE_PREFIX}:{adapter_name}:"
        to_remove = [k for k in self._store if k.startswith(prefix)]
        for k in to_remove:
            del self._store[k]


class RedisCache:
    """Redis-backed result cache with native TTL."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: Any = None

    async def _connect(self) -> Any:
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self._redis_url, decode_responses=True
                )
                await self._redis.ping()
            except Exception as exc:
                logger.warning("Redis cache connection failed: %s", exc)
                self._redis = None
                raise
        return self._redis

    def _key(self, adapter_name: str, input_hash: str, scope_hash: str) -> str:
        return f"{_CACHE_PREFIX}:{adapter_name}:{input_hash}:{scope_hash}"

    async def get(
        self, adapter_name: str, input_hash: str, scope_hash: str
    ) -> list[dict[str, Any]] | None:
        try:
            r = await self._connect()
        except Exception:
            return None
        key = self._key(adapter_name, input_hash, scope_hash)
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(
        self,
        adapter_name: str,
        input_hash: str,
        scope_hash: str,
        events: list[dict[str, Any]],
        ttl_seconds: int = 3600,
    ) -> None:
        try:
            r = await self._connect()
        except Exception:
            return
        key = self._key(adapter_name, input_hash, scope_hash)
        await r.set(key, json.dumps(events), ex=ttl_seconds)

    async def invalidate(self, adapter_name: str) -> None:
        try:
            r = await self._connect()
        except Exception:
            return
        # Use SCAN to find matching keys
        prefix = f"{_CACHE_PREFIX}:{adapter_name}:*"
        async for key in r.scan_iter(match=prefix):
            await r.delete(key)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


@dataclass
class ResultCache:
    """Unified cache interface that selects backend based on configuration."""

    _backend: InMemoryCache | RedisCache = field(default_factory=InMemoryCache)

    @classmethod
    def create(cls, redis_url: str | None = None) -> "ResultCache":
        """Factory: use RedisCache if redis_url is provided, else InMemoryCache."""
        if redis_url:
            return cls(_backend=RedisCache(redis_url))
        return cls(_backend=InMemoryCache())

    async def get(
        self, adapter_name: str, input_hash: str, scope_hash: str
    ) -> list[dict[str, Any]] | None:
        return await self._backend.get(adapter_name, input_hash, scope_hash)

    async def set(
        self,
        adapter_name: str,
        input_hash: str,
        scope_hash: str,
        events: list[dict[str, Any]],
        ttl_seconds: int = 3600,
    ) -> None:
        await self._backend.set(adapter_name, input_hash, scope_hash, events, ttl_seconds)

    async def invalidate(self, adapter_name: str) -> None:
        await self._backend.invalidate(adapter_name)
