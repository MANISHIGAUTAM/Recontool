"""Task worker for distributed adapter execution.

Pulls tasks from the queue, loads the appropriate adapter, reconstructs a
minimal AdapterContext, executes the adapter, and writes results back.

Usage (via CLI):
    recontool worker --concurrency 4
"""
from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from recontool.queue.base import TaskQueue

logger = logging.getLogger(__name__)


class TaskWorker:
    """Pulls adapter tasks from a queue and executes them."""

    def __init__(self, queue: TaskQueue, concurrency: int = 4) -> None:
        self._queue = queue
        self._concurrency = concurrency
        self._running = False
        self._sem = asyncio.Semaphore(concurrency)

    async def run(self) -> None:
        """Main worker loop. Runs until stopped or queue is idle."""
        self._running = True
        logger.info("TaskWorker starting (concurrency=%d)", self._concurrency)
        tasks: list[asyncio.Task[Any]] = []

        while self._running:
            item = await self._queue.dequeue(timeout=2.0)
            if item is None:
                # No work available; if no in-flight tasks, exit cleanly
                if not tasks or all(t.done() for t in tasks):
                    break
                # Clean up completed tasks
                tasks = [t for t in tasks if not t.done()]
                continue

            task_id, task_data = item
            await self._sem.acquire()
            t = asyncio.create_task(self._execute(task_id, task_data))
            tasks.append(t)

        # Wait for remaining tasks to finish
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("TaskWorker stopped")

    async def _execute(self, task_id: str, task_data: dict[str, Any]) -> None:
        """Execute a single adapter task."""
        try:
            adapter_name = task_data.get("adapter_name", "")
            phase = task_data.get("phase", "")
            scan_id = task_data.get("scan_id", "")
            context_data = task_data.get("context_data", {})

            logger.info("Executing task %s: adapter=%s phase=%s", task_id, adapter_name, phase)

            # Load the adapter from the registry
            from recontool.adapters.registry import all_adapters, load_builtin
            load_builtin()
            registry = all_adapters()

            cls = registry.get(adapter_name)
            if cls is None:
                await self._queue.fail(task_id, f"Unknown adapter: {adapter_name}")
                return

            inst = cls()

            # Reconstruct a minimal AdapterContext
            ctx = self._build_context(scan_id, context_data)

            # Execute the adapter
            events = await inst.run(ctx)

            # Serialize events for the result
            event_dicts = [
                {"entity": e.entity, "tool": e.tool, "data": e.data, "raw_ref": e.raw_ref}
                for e in events
            ]

            await self._queue.complete(task_id, {"events": event_dicts})
            logger.info("Task %s completed: %d events", task_id, len(events))

        except Exception as exc:  # noqa: BLE001
            logger.error("Task %s failed: %s", task_id, exc)
            await self._queue.fail(task_id, str(exc)[:2000])
        finally:
            self._sem.release()

    def _build_context(self, scan_id: str, context_data: dict[str, Any]) -> Any:
        """Reconstruct an AdapterContext from serialized data."""
        from recontool.adapters.base import AdapterContext
        from recontool.config import PROFILES, settings
        from recontool.core.artifacts import ArtifactStore
        from recontool.core.scope import Scope
        from recontool.net.http_client import HttpClient
        from recontool.net.proxy_pool import ProxyPool
        from recontool.net.rate_limiter import RateLimiter

        profile_name = context_data.get("profile_name", settings.profile_name)
        profile = PROFILES.get(profile_name, settings.profile())
        inputs = context_data.get("inputs", {})
        api_keys = context_data.get("api_keys", {})
        scope_json = context_data.get("scope_json", {})

        scope = Scope.from_json(scope_json) if scope_json else Scope.from_seed("unknown", "domain")

        proxies = ProxyPool(settings.proxies, strategy=settings.proxy_strategy)
        limiter = RateLimiter(default_rate=profile.requests_per_second)
        from recontool.net.circuit import BudgetLedger, CircuitRegistry
        circuits = CircuitRegistry(failure_threshold=5, cooldown=30.0)
        budget = BudgetLedger()
        http = HttpClient(
            profile=profile, proxy_pool=proxies, limiter=limiter,
            mode=settings.run_mode, mock_env=None,
            circuits=circuits, budget=budget,
        )
        artifacts = ArtifactStore(scan_id)

        return AdapterContext(
            scan_id=scan_id, scope=scope, profile=profile, http=http,
            artifacts=artifacts, inputs=inputs, api_keys=api_keys,
        )

    def stop(self) -> None:
        """Signal the worker to stop after current tasks complete."""
        self._running = False


def run_worker(queue: TaskQueue, concurrency: int = 4) -> None:
    """Entry point: run the worker with graceful shutdown on signals."""
    worker = TaskWorker(queue, concurrency=concurrency)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(sig: signal.Signals) -> None:
        logger.info("Received %s, shutting down worker...", sig.name)
        worker.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown, sig)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        loop.run_until_complete(worker.run())
    finally:
        loop.close()
