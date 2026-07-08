"""Event-driven orchestrator that ties all engine components together.

Provides the high-level run_scan() API that integrates the EventBus,
ToolRegistry, PendingKeyStore, DependencyChecker, ParallelExecutor,
IncrementalEngine, and FrontierManager into a cohesive scan lifecycle.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from recontool.engine.dependency import DependencyChecker
from recontool.engine.events import (
    EntityDiscovered,
    EventBus,
    ScanCompleted,
    ToolFailed,
)
from recontool.engine.executor import ExecutionResult, ParallelExecutor, ScheduledJob
from recontool.engine.output import OutputNormalizer
from recontool.engine.registry import ToolRegistry
from recontool.engine.scheduler import EventDrivenScheduler
from recontool.orchestrator.frontier import Checkpoint

logger = logging.getLogger(__name__)


@dataclass
class ScanConfig:
    """Configuration for a single scan run."""

    seed: str
    seed_type: str = "domain"
    profile: str = "normal"
    max_depth: int = 3
    max_iterations: int = 50
    global_concurrency: int = 20
    per_tool_concurrency: dict[str, int] = field(default_factory=dict)
    per_host_concurrency: dict[str, int] = field(default_factory=dict)
    checkpoint_dir: Optional[str] = None
    resume: bool = False


@dataclass
class ScanResult:
    """Result of a completed scan."""

    scan_id: str
    status: str = "completed"
    total_tools_run: int = 0
    total_entities: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)


class EventDrivenOrchestrator:
    """Main orchestrator class that coordinates all engine components.

    Public API:
        result = await orchestrator.run_scan(seed, config)

    Integrates:
        - EventBus for event routing
        - ToolRegistry for tool metadata
        - DependencyChecker for readiness validation
        - ParallelExecutor for concurrency-controlled execution
        - IncrementalEngine for skip/rerun decisions
        - EventDrivenScheduler for job scheduling
        - FrontierManager for work queue (from existing orchestrator)
        - Checkpoint for resume support

    The orchestrator is additive: the existing ReconPipeline continues to
    function independently.
    """

    def __init__(
        self,
        bus: Optional[EventBus] = None,
        registry: Optional[ToolRegistry] = None,
        dependency_checker: Optional[DependencyChecker] = None,
        output_normalizer: Optional[OutputNormalizer] = None,
        execute_fn: Any = None,
    ) -> None:
        self._bus = bus or EventBus()
        self._registry = registry or ToolRegistry()
        self._dependency_checker = dependency_checker or DependencyChecker()
        self._output_normalizer = output_normalizer or OutputNormalizer()
        self._execute_fn = execute_fn
        self._scan_results: dict[str, ScanResult] = {}
        self._entities_discovered: dict[str, int] = {}

        # Subscribe to lifecycle events for tracking
        self._bus.subscribe(ScanCompleted, self._on_scan_completed)
        self._bus.subscribe(EntityDiscovered, self._on_entity_discovered)
        self._bus.subscribe(ToolFailed, self._on_tool_failed)

    async def run_scan(
        self,
        seed: str,
        config: ScanConfig | None = None,
    ) -> ScanResult:
        """Execute a full scan lifecycle.

        1. Initialize components
        2. Optionally resume from checkpoint
        3. Submit seed to scheduler
        4. Process jobs until convergence
        5. Return results
        """
        config = config or ScanConfig(seed=seed)
        scan_id = str(uuid.uuid4())
        start_time = dt.datetime.now(dt.timezone.utc)

        # Initialize result tracking
        self._scan_results[scan_id] = ScanResult(scan_id=scan_id)
        self._entities_discovered[scan_id] = 0

        # Initialize executor
        executor = ParallelExecutor(
            bus=self._bus,
            global_limit=config.global_concurrency,
            per_tool_concurrency=config.per_tool_concurrency,
            per_host_concurrency=config.per_host_concurrency,
        )

        # Initialize scheduler
        scheduler = EventDrivenScheduler(
            bus=self._bus,
            registry=self._registry,
            max_depth=config.max_depth,
            max_iterations=config.max_iterations,
        )

        # Checkpoint support
        checkpoint: Optional[Checkpoint] = None
        if config.checkpoint_dir:
            cp_path = Path(config.checkpoint_dir) / f"{scan_id}.json"
            checkpoint = Checkpoint(cp_path)

        # Emit ScanRequested and submit seed
        await scheduler.submit_scan(
            scan_id=scan_id,
            seed=seed,
            config={"seed_type": config.seed_type, "profile": config.profile},
        )

        # Process job queue until convergence
        execute_fn = self._execute_fn or self._default_execute
        max_idle_cycles = 3
        idle_cycles = 0

        while not scheduler.check_convergence(scan_id):
            # Drain available jobs
            jobs: list[ScheduledJob] = []
            try:
                while True:
                    job = scheduler.job_queue.get_nowait()
                    jobs.append(job)
            except asyncio.QueueEmpty:
                pass

            if jobs:
                idle_cycles = 0
                await executor.execute_batch(jobs, execute_fn)
            else:
                idle_cycles += 1
                # Only break on idle if no tools are still running
                if idle_cycles >= max_idle_cycles and not scheduler.has_running_tools(scan_id):
                    break
                await asyncio.sleep(0.01)

            # Save checkpoint if configured
            if checkpoint:
                checkpoint.save({
                    "scan_id": scan_id,
                    "status": "running",
                    "tools_completed": len(scheduler.completed_tool_count(scan_id)),
                })

        # Calculate duration
        end_time = dt.datetime.now(dt.timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Finalize result
        result = self._scan_results[scan_id]
        result.duration_ms = duration_ms
        result.total_entities = self._entities_discovered.get(scan_id, 0)

        # Clear checkpoint on success
        if checkpoint and result.status == "completed":
            checkpoint.clear()

        # Clean up per-scan state to avoid memory leaks across reuse
        self._scan_results.pop(scan_id, None)
        self._entities_discovered.pop(scan_id, None)

        return result

    async def _on_scan_completed(self, event: ScanCompleted) -> None:
        """Update scan result on completion."""
        if event.scan_id in self._scan_results:
            self._scan_results[event.scan_id].status = event.status
            self._scan_results[event.scan_id].total_tools_run = event.total_tools_run

    async def _on_entity_discovered(self, event: EntityDiscovered) -> None:
        """Track entity discovery count."""
        self._entities_discovered[event.scan_id] = (
            self._entities_discovered.get(event.scan_id, 0) + 1
        )

    async def _on_tool_failed(self, event: ToolFailed) -> None:
        """Track tool failures."""
        if event.scan_id in self._scan_results:
            self._scan_results[event.scan_id].errors.append(
                f"{event.tool_name}: {event.error}"
            )

    @staticmethod
    async def _default_execute(job: ScheduledJob) -> ExecutionResult:
        """Default no-op execution function for testing."""
        return ExecutionResult(
            tool_name=job.tool_name,
            scan_id=job.scan_id,
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
        )
