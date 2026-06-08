"""Abstract task queue interface.

Defines the TaskQueue ABC and the Task dataclass used for adapter dispatch.
Two backends are provided: InMemoryQueue (default) and RedisQueue (distributed).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    """A serializable unit of work for the queue."""

    task_id: str
    adapter_name: str
    phase: str
    scan_id: str
    context_data: dict[str, Any] = field(default_factory=dict)


class TaskQueue(abc.ABC):
    """Abstract task queue supporting enqueue/dequeue/result lifecycle."""

    @abc.abstractmethod
    async def enqueue(self, task_id: str, task_data: dict[str, Any]) -> str:
        """Add a task to the queue. Returns the task_id."""

    @abc.abstractmethod
    async def dequeue(self, timeout: float = 5.0) -> tuple[str, dict[str, Any]] | None:
        """Pull the next task. Returns (task_id, task_data) or None on timeout."""

    @abc.abstractmethod
    async def complete(self, task_id: str, result: dict[str, Any]) -> None:
        """Mark a task as successfully completed with its result."""

    @abc.abstractmethod
    async def fail(self, task_id: str, error: str) -> None:
        """Mark a task as failed with an error message."""

    @abc.abstractmethod
    async def get_result(self, task_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        """Wait for and return the result of a task, or None on timeout."""

    @abc.abstractmethod
    async def pending_count(self) -> int:
        """Return the number of tasks waiting in the queue."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Release resources held by the queue backend."""
