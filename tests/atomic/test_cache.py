"""Atomic tests for the result caching module (InMemoryCache + hash_inputs)."""
from __future__ import annotations

import asyncio

import pytest

from recontool.cache import InMemoryCache, ResultCache, hash_inputs


# ── InMemoryCache: set/get cycle ────────────────────────────────────────────
async def test_set_get_cycle():
    cache = InMemoryCache()
    events = [{"entity": "subdomain", "tool": "crtsh", "data": {"value": "api.example.com"}}]
    await cache.set("crtsh", "hash1", "scope1", events, ttl_seconds=60)

    result = await cache.get("crtsh", "hash1", "scope1")
    assert result == events


# ── InMemoryCache: cache miss returns None ──────────────────────────────────
async def test_cache_miss_returns_none():
    cache = InMemoryCache()
    result = await cache.get("nonexistent", "hash1", "scope1")
    assert result is None


# ── InMemoryCache: TTL expiry ───────────────────────────────────────────────
async def test_ttl_expiry():
    cache = InMemoryCache()
    events = [{"entity": "domain", "tool": "otx", "data": {}}]
    # Use a very short TTL
    await cache.set("otx", "h1", "s1", events, ttl_seconds=0)

    # Even 0 TTL means expired immediately (expires_at = time.time() + 0)
    await asyncio.sleep(0.05)
    result = await cache.get("otx", "h1", "s1")
    assert result is None


async def test_ttl_not_expired():
    cache = InMemoryCache()
    events = [{"entity": "domain", "tool": "otx", "data": {}}]
    await cache.set("otx", "h1", "s1", events, ttl_seconds=60)

    result = await cache.get("otx", "h1", "s1")
    assert result == events


# ── InMemoryCache: invalidate by adapter name ───────────────────────────────
async def test_invalidate_by_adapter_name():
    cache = InMemoryCache()
    await cache.set("crtsh", "h1", "s1", [{"entity": "a"}], ttl_seconds=300)
    await cache.set("crtsh", "h2", "s2", [{"entity": "b"}], ttl_seconds=300)
    await cache.set("otx", "h1", "s1", [{"entity": "c"}], ttl_seconds=300)

    # Invalidate only crtsh entries
    await cache.invalidate("crtsh")

    assert await cache.get("crtsh", "h1", "s1") is None
    assert await cache.get("crtsh", "h2", "s2") is None
    # otx entries should still be present
    result = await cache.get("otx", "h1", "s1")
    assert result == [{"entity": "c"}]


# ── hash_inputs: consistency ────────────────────────────────────────────────
def test_hash_inputs_consistency():
    inputs = {"domain": ["example.com", "test.com"]}
    scope = {"allow_domains": ["example.com"]}

    hash1 = hash_inputs(inputs, scope)
    hash2 = hash_inputs(inputs, scope)
    assert hash1 == hash2
    assert isinstance(hash1, str)
    assert len(hash1) == 16  # sha256 hex truncated to 16 chars


def test_hash_inputs_different_for_different_inputs():
    scope = {"allow_domains": ["example.com"]}
    hash1 = hash_inputs({"domain": ["a.com"]}, scope)
    hash2 = hash_inputs({"domain": ["b.com"]}, scope)
    assert hash1 != hash2


def test_hash_inputs_order_independent():
    """Dict key order shouldn't matter since json.dumps uses sort_keys=True."""
    inputs_a = {"domain": ["a.com"], "ip": ["1.2.3.4"]}
    inputs_b = {"ip": ["1.2.3.4"], "domain": ["a.com"]}
    scope = {}
    assert hash_inputs(inputs_a, scope) == hash_inputs(inputs_b, scope)


# ── ResultCache: factory creates InMemoryCache backend ──────────────────────
async def test_result_cache_factory_no_redis():
    cache = ResultCache.create(redis_url=None)
    assert isinstance(cache._backend, InMemoryCache)

    # Verify it works end-to-end
    await cache.set("adapter1", "h1", "s1", [{"event": "data"}], ttl_seconds=60)
    result = await cache.get("adapter1", "h1", "s1")
    assert result == [{"event": "data"}]
