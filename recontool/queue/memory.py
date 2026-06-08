"""In-memory task queue implementation.

Default backend when no Redis is configured. Uses asyncio.Queue for the task
queue and asyncio.Event per task for result notification. Suitable for
single-process / demo mode.
"""
from __future__ import annotations

import asyncio
from typing import Any

from recontool.queue.base import TaskQueue


class InMemoryQueue(TaskQueue):
    """In-process queue backed by asyncio primitives."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._results: dict[str, dict[str, Any]] = {}
        self._events: dict[str, asyncio.Event] = {}

    async def enqueue(self, task_id: str, task_data: dict[str, Any]) -> str:
        self._events[task_id] = asyncio.Event()
        await self._queue.put((task_id, task_data))
        return task_id

    async def dequeue(self, timeout: float = 5.0) -> tuple[str, dict[str, Any]] | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            return None

    async def complete(self, task_id: str, result: dict[str, Any]) -> None:
        self._results[task_id] = {"status": "completed", "result": result}
        event = self._events.get(task_id)
        if event:
            event.set()

    async def fail(self, task_id: str, error: str) -> None:
        self._results[task_id] = {"status": "failed", "error": error}
        event = self._events.get(task_id)
        if event:
            event.set()

    async def get_result(self, task_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        event = self._events.get(task_id)
        if event is None:
            return self._results.get(task_id)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            return None
        return self._results.get(task_id)

    async def pending_count(self) -> int:
        return self._queue.qsize()

    async def close(self) -> None:
        self._results.clear()
        self._events.clear()
