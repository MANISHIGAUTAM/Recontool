"""Async token-bucket rate limiter.

Keyed per bucket -- typically per (provider) or per (provider, egress_ip) -- so
that many concurrent workers sharing one API key cannot collectively exceed a
provider's limit (docs/D6-opsec.md S3-4, ADR-010).

Each bucket has its own lock so that waiting on one bucket never blocks
acquisition from a different bucket. This is critical for parallel probing
of many hosts (each host = separate bucket).

In-process by default; can be backed by Redis for multi-node deployments
(interface is the same; Redis impl is a drop-in).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    rate: float          # tokens per second
    capacity: float      # max burst
    tokens: float
    last: float


class RateLimiter:
    """Multiple named token buckets with async acquisition.

    Each bucket is independent -- waiting for tokens in bucket A does NOT block
    callers trying to acquire from bucket B. This ensures per-host rate limits
    do not serialize the entire scan.
    """

    def __init__(self, default_rate: float = 10.0, default_capacity: float | None = None):
        self.default_rate = default_rate
        self.default_capacity = default_capacity or max(default_rate, 1.0)
        self._buckets: dict[str, _Bucket] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def configure(self, key: str, rate: float, capacity: float | None = None) -> None:
        cap = capacity if capacity is not None else max(rate, 1.0)
        self._buckets[key] = _Bucket(rate=rate, capacity=cap, tokens=cap, last=time.monotonic())
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

    async def _get_bucket(self, key: str) -> tuple[_Bucket, asyncio.Lock]:
        """Return (bucket, per-bucket lock), creating lazily if needed."""
        if key in self._buckets:
            return self._buckets[key], self._locks[key]
        async with self._global_lock:
            if key not in self._buckets:
                self.configure(key, self.default_rate, self.default_capacity)
        return self._buckets[key], self._locks[key]

    async def acquire(self, key: str = "_global", tokens: float = 1.0) -> None:
        """Block until `tokens` are available in bucket `key`.

        Only the per-bucket lock is held during the check-and-debit, so
        concurrent acquires on different buckets proceed in parallel.
        """
        bucket, lock = await self._get_bucket(key)
        while True:
            async with lock:
                now = time.monotonic()
                elapsed = now - bucket.last
                bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.rate)
                bucket.last = now
                if bucket.tokens >= tokens:
                    bucket.tokens -= tokens
                    return
                deficit = tokens - bucket.tokens
                wait = deficit / bucket.rate
            # Sleep WITHOUT holding the lock so other coroutines on the same
            # bucket can check/refill while we wait.
            await asyncio.sleep(min(wait, 0.5))

    def snapshot(self) -> dict[str, float]:
        return {k: round(b.tokens, 2) for k, b in self._buckets.items()}
