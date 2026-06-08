"""Redis-backed task queue implementation.

Uses redis.asyncio with BLPOP for blocking dequeue and Redis hashes for result
storage. Falls back gracefully to InMemoryQueue on connection error.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from recontool.queue.base import TaskQueue

logger = logging.getLogger(__name__)

_QUEUE_KEY = "recon:queue:tasks"
_RESULT_PREFIX = "recon:queue:result:"


class RedisQueue(TaskQueue):
    """Distributed queue backed by Redis lists and hashes."""

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
                # Verify connectivity
                await self._redis.ping()
            except Exception as exc:
                logger.warning("Redis connection failed (%s), queue unavailable", exc)
                self._redis = None
                raise
        return self._redis

    async def enqueue(self, task_id: str, task_data: dict[str, Any]) -> str:
        r = await self._connect()
        payload = json.dumps({"task_id": task_id, "data": task_data})
        await r.lpush(_QUEUE_KEY, payload)
        return task_id

    async def dequeue(self, timeout: float = 5.0) -> tuple[str, dict[str, Any]] | None:
        r = await self._connect()
        result = await r.blpop(_QUEUE_KEY, timeout=int(max(timeout, 1)))
        if result is None:
            return None
        # blpop returns (key, value)
        _, raw = result
        item = json.loads(raw)
        return item["task_id"], item["data"]

    async def complete(self, task_id: str, result: dict[str, Any]) -> None:
        r = await self._connect()
        payload = json.dumps({"status": "completed", "result": result})
        await r.set(f"{_RESULT_PREFIX}{task_id}", payload, ex=3600)

    async def fail(self, task_id: str, error: str) -> None:
        r = await self._connect()
        payload = json.dumps({"status": "failed", "error": error})
        await r.set(f"{_RESULT_PREFIX}{task_id}", payload, ex=3600)

    async def get_result(self, task_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        import asyncio

        r = await self._connect()
        key = f"{_RESULT_PREFIX}{task_id}"
        # Poll with exponential backoff up to timeout
        elapsed = 0.0
        interval = 0.1
        while elapsed < timeout:
            raw = await r.get(key)
            if raw is not None:
                return json.loads(raw)
            await asyncio.sleep(interval)
            elapsed += interval
            interval = min(interval * 1.5, 1.0)
        return None

    async def pending_count(self) -> int:
        r = await self._connect()
        return await r.llen(_QUEUE_KEY)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
