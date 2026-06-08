"""Parallel execution engine with concurrency controls.

Implements per-tool, per-host, and global concurrency limits using
asyncio.Semaphore. Policy: parallelize discovery fan-out, do not
parallelize tools sharing mutable output.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from recontool.engine.events import (
    EventBus,
    ToolCompleted,
    ToolFailed,
    ToolRunning,
)
from recontool.engine.scheduler import ScheduledJob

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a single tool execution."""

    tool_name: str
    scan_id: str
    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    artifacts: list[str] = field(default_factory=list)
    error: str = ""


# Type for the actual execution callback
ExecuteFunc = Callable[[ScheduledJob], Coroutine[Any, Any, ExecutionResult]]


class ParallelExecutor:
    """Parallel execution engine with layered concurrency controls.

    Concurrency layers (most restrictive wins):
    1. Global semaphore: absolute cap on parallel tasks
    2. Per-tool semaphore: limits concurrent instances of the same tool
    3. Per-host semaphore: limits concurrent requests to a single host/target

    Policy:
    - Tools marked parallel_safe=True can run concurrently
    - Tools with concurrency_safety=False are serialized per-tool
    - Discovery tools get higher concurrency
    - Tools with mutable shared state are restricted
    """

    def __init__(
        self,
        bus: EventBus,
        global_limit: int = 20,
        default_per_tool: int = 5,
        default_per_host: int = 3,
        per_tool_concurrency: dict[str, int] | None = None,
        per_host_concurrency: dict[str, int] | None = None,
    ) -> None:
        self._bus = bus
        self._global_semaphore = asyncio.Semaphore(global_limit)
        self._default_per_tool = default_per_tool
        self._default_per_host = default_per_host
        self._per_tool_limits = per_tool_concurrency or {}
        self._per_host_limits = per_host_concurrency or {}
        self._tool_semaphores: dict[str, asyncio.Semaphore] = {}
        self._host_semaphores: dict[str, asyncio.Semaphore] = {}
        self._active_count = 0
        self._total_executed = 0

    @property
    def active_count(self) -> int:
        """Number of currently executing jobs."""
        return self._active_count

    @property
    def total_executed(self) -> int:
        """Total jobs executed since creation."""
        return self._total_executed

    def _get_tool_semaphore(self, tool_name: str) -> asyncio.Semaphore:
        """Get or create a per-tool semaphore."""
        if tool_name not in self._tool_semaphores:
            limit = self._per_tool_limits.get(tool_name, self._default_per_tool)
            self._tool_semaphores[tool_name] = asyncio.Semaphore(limit)
        return self._tool_semaphores[tool_name]

    def _get_host_semaphore(self, host: str) -> asyncio.Semaphore:
        """Get or create a per-host semaphore."""
        if host not in self._host_semaphores:
            limit = self._per_host_limits.get(host, self._default_per_host)
            self._host_semaphores[host] = asyncio.Semaphore(limit)
        return self._host_semaphores[host]

    async def execute_batch(
        self,
        jobs: list[ScheduledJob],
        execute_fn: ExecuteFunc,
    ) -> list[ExecutionResult]:
        """Execute a batch of jobs with concurrency controls.

        Jobs run in parallel up to the configured limits. Results are
        gathered and returned once all jobs complete.
        """
        tasks = [self.execute_one(job, execute_fn) for job in jobs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        execution_results: list[ExecutionResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                execution_results.append(ExecutionResult(
                    tool_name=jobs[i].tool_name,
                    scan_id=jobs[i].scan_id,
                    success=False,
                    exit_code=1,
                    error=str(result),
                ))
            else:
                execution_results.append(result)
        return execution_results

    async def execute_one(
        self,
        job: ScheduledJob,
        execute_fn: ExecuteFunc,
    ) -> ExecutionResult:
        """Execute a single job with concurrency controls.

        Acquires global + per-tool semaphores before execution, emits
        lifecycle events via the EventBus.
        """
        tool_sem = self._get_tool_semaphore(job.tool_name)

        # Extract host from inputs for per-host limiting
        host = self._extract_host(job.inputs)
        host_sem = self._get_host_semaphore(host) if host else None

        # Acquire semaphores in order: global -> tool -> host
        async with self._global_semaphore:
            async with tool_sem:
                if host_sem:
                    async with host_sem:
                        return await self._run_job(job, execute_fn)
                else:
                    return await self._run_job(job, execute_fn)

    async def _run_job(
        self,
        job: ScheduledJob,
        execute_fn: ExecuteFunc,
    ) -> ExecutionResult:
        """Actually execute a job and emit events."""
        self._active_count += 1
        start_time = time.monotonic()

        # Emit ToolRunning event
        await self._bus.publish(ToolRunning(
            scan_id=job.scan_id,
            tool_name=job.tool_name,
        ))

        try:
            result = await execute_fn(job)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            result.duration_ms = duration_ms

            if result.success:
                await self._bus.publish(ToolCompleted(
                    scan_id=job.scan_id,
                    tool_name=job.tool_name,
                    exit_code=result.exit_code,
                    duration_ms=duration_ms,
                ))
            else:
                await self._bus.publish(ToolFailed(
                    scan_id=job.scan_id,
                    tool_name=job.tool_name,
                    exit_code=result.exit_code,
                    error=result.error,
                    retryable=True,
                ))
            return result
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await self._bus.publish(ToolFailed(
                scan_id=job.scan_id,
                tool_name=job.tool_name,
                exit_code=1,
                error=str(exc),
                retryable=True,
            ))
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=False,
                exit_code=1,
                error=str(exc),
                duration_ms=duration_ms,
            )
        finally:
            self._active_count -= 1
            self._total_executed += 1

    def _extract_host(self, inputs: dict[str, Any]) -> str:
        """Try to extract a host/target from job inputs for per-host limiting."""
        for key in ("host", "target", "domain"):
            val = inputs.get(key)
            if isinstance(val, str):
                return val
            if isinstance(val, list) and val and isinstance(val[0], str):
                return val[0]
        return ""
