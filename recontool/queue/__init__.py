"""Task queue abstraction for adapter dispatch.

Exports:
    TaskQueue      - abstract base class
    Task           - task dataclass
    InMemoryQueue  - default in-process backend
    RedisQueue     - distributed Redis backend
    get_queue()    - factory that returns the appropriate backend
"""
from __future__ import annotations

from recontool.queue.base import Task, TaskQueue
from recontool.queue.memory import InMemoryQueue
from recontool.queue.redis_queue import RedisQueue


def get_queue(redis_url: str | None = None) -> TaskQueue:
    """Return a queue backend based on configuration.

    If redis_url is provided, attempts to create a RedisQueue.
    Falls back to InMemoryQueue if Redis package is not installed or not configured.
    """
    if redis_url:
        try:
            import redis  # noqa: F401 — check if package is installed
            return RedisQueue(redis_url)
        except ImportError:
            import logging
            logging.getLogger(__name__).warning(
                "redis package not installed; falling back to InMemoryQueue. "
                "Install with: pip install redis"
            )
            return InMemoryQueue()
    return InMemoryQueue()


__all__ = [
    "Task",
    "TaskQueue",
    "InMemoryQueue",
    "RedisQueue",
    "get_queue",
]
