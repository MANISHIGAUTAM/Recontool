"""Atomic tests for the task queue abstraction (InMemoryQueue + factory)."""
from __future__ import annotations

import asyncio

import pytest

from recontool.queue import InMemoryQueue, RedisQueue, get_queue


# ── InMemoryQueue: basic enqueue/dequeue cycle ─────────────────────────────
async def test_enqueue_dequeue_cycle():
    q = InMemoryQueue()
    task_data = {"adapter_name": "crtsh", "phase": "p1_seed", "scan_id": "abc123"}
    await q.enqueue("task-1", task_data)

    item = await q.dequeue(timeout=1.0)
    assert item is not None
    task_id, data = item
    assert task_id == "task-1"
    assert data == task_data
    await q.close()


# ── InMemoryQueue: complete/get_result ──────────────────────────────────────
async def test_complete_and_get_result():
    q = InMemoryQueue()
    await q.enqueue("task-2", {"adapter_name": "otx"})

    result_payload = {"events": [{"entity": "subdomain", "tool": "otx"}]}
    await q.complete("task-2", result_payload)

    result = await q.get_result("task-2", timeout=1.0)
    assert result is not None
    assert result["status"] == "completed"
    assert result["result"] == result_payload
    await q.close()


# ── InMemoryQueue: fail handling ────────────────────────────────────────────
async def test_fail_handling():
    q = InMemoryQueue()
    await q.enqueue("task-3", {"adapter_name": "wayback"})

    await q.fail("task-3", "connection timeout")

    result = await q.get_result("task-3", timeout=1.0)
    assert result is not None
    assert result["status"] == "failed"
    assert result["error"] == "connection timeout"
    await q.close()


# ── InMemoryQueue: concurrent multiple tasks ────────────────────────────────
async def test_concurrent_multiple_tasks():
    q = InMemoryQueue()
    # Enqueue several tasks (fire-and-forget pattern)
    task_ids = [f"task-{i}" for i in range(5)]
    for tid in task_ids:
        await q.enqueue(tid, {"adapter_name": f"adapter_{tid}", "phase": "p1_seed"})

    # Dequeue all
    dequeued = []
    for _ in range(5):
        item = await q.dequeue(timeout=1.0)
        assert item is not None
        dequeued.append(item[0])

    assert sorted(dequeued) == sorted(task_ids)

    # Complete all concurrently
    await asyncio.gather(
        *(q.complete(tid, {"events": []}) for tid in task_ids)
    )

    # Verify all results available
    for tid in task_ids:
        result = await q.get_result(tid, timeout=1.0)
        assert result is not None
        assert result["status"] == "completed"
    await q.close()


# ── InMemoryQueue: pending_count tracking ───────────────────────────────────
async def test_pending_count_tracking():
    q = InMemoryQueue()
    assert await q.pending_count() == 0

    await q.enqueue("t1", {"x": 1})
    await q.enqueue("t2", {"x": 2})
    assert await q.pending_count() == 2

    await q.dequeue(timeout=1.0)
    assert await q.pending_count() == 1

    await q.dequeue(timeout=1.0)
    assert await q.pending_count() == 0
    await q.close()


# ── InMemoryQueue: dequeue timeout returns None ─────────────────────────────
async def test_dequeue_timeout_returns_none():
    q = InMemoryQueue()
    result = await q.dequeue(timeout=0.1)
    assert result is None
    await q.close()


# ── get_queue factory returns InMemoryQueue when no redis_url ───────────────
def test_get_queue_returns_inmemory_when_no_redis():
    q = get_queue(redis_url=None)
    assert isinstance(q, InMemoryQueue)


def test_get_queue_returns_inmemory_for_empty_string():
    q = get_queue(redis_url="")
    assert isinstance(q, InMemoryQueue)


# ── RedisQueue: importable and instantiable (no connection) ─────────────────
def test_redis_queue_importable_and_instantiable():
    rq = RedisQueue("redis://localhost:6379/0")
    assert rq._redis_url == "redis://localhost:6379/0"
    assert rq._redis is None  # no actual connection until first operation


def test_get_queue_returns_redis_queue_with_url():
    q = get_queue(redis_url="redis://localhost:6379/0")
    assert isinstance(q, RedisQueue)
