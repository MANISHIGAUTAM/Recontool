"""Integration tests for the event-driven orchestrator flow.

Verifies:
- Adapter with mocked execution producing events
- Orchestrator with in-memory SQLite processing discovery->enrichment flow
- Event flow: EntityDiscovered -> PendingKeyCreated -> PendingKeyResolved -> ToolSelected
- Parallel scheduling respects concurrency limits
- Retry and timeout handling
"""
from __future__ import annotations

import asyncio

import pytest

from recontool.engine.events import (
    EntityDiscovered,
    EventBus,
    PendingKeyCreated,
    PendingKeyResolved,
    ScanCompleted,
    ToolCompleted,
    ToolFailed,
    ToolSelected,
)
from recontool.engine.executor import ExecutionResult, ParallelExecutor, ScheduledJob
from recontool.engine.orchestrator import EventDrivenOrchestrator, ScanConfig
from recontool.engine.registry import ToolRegistry, ToolSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(*tool_specs: ToolSpec) -> ToolRegistry:
    """Build a registry from ToolSpec instances."""
    tools = {t.name: t for t in tool_specs}
    return ToolRegistry(tools=tools)


class EventCollector:
    """Collects all published events for assertion."""

    def __init__(self, bus: EventBus) -> None:
        self.events: list = []
        bus.subscribe(EntityDiscovered, self._collect)
        bus.subscribe(PendingKeyCreated, self._collect)
        bus.subscribe(PendingKeyResolved, self._collect)
        bus.subscribe(ToolSelected, self._collect)
        bus.subscribe(ToolCompleted, self._collect)
        bus.subscribe(ToolFailed, self._collect)
        bus.subscribe(ScanCompleted, self._collect)

    async def _collect(self, event) -> None:
        self.events.append(event)

    def of_type(self, cls):
        return [e for e in self.events if isinstance(e, cls)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrchestratorFlow:
    """Integration: orchestrator with mocked tool execution."""

    @pytest.mark.asyncio
    async def test_discovery_to_enrichment_flow(self):
        """A discovery tool produces entities, triggering enrichment scheduling."""
        bus = EventBus()
        collector = EventCollector(bus)

        crtsh = ToolSpec(
            name="crtsh",
            enabled=True,
            consumes=["domain"],
            produces=["subdomain"],
            supported_input_types=["domain"],
            output_types=["subdomain"],
        )
        httpx = ToolSpec(
            name="httpx",
            enabled=True,
            consumes=["subdomain"],
            produces=["live_host"],
            supported_input_types=["subdomain"],
            output_types=["live_host"],
        )
        registry = _make_registry(crtsh, httpx)

        call_count = {"crtsh": 0, "httpx": 0}

        async def mock_execute(job: ScheduledJob) -> ExecutionResult:
            call_count[job.tool_name] = call_count.get(job.tool_name, 0) + 1
            if job.tool_name == "crtsh":
                # Emit entity discovered for downstream scheduling
                await bus.publish(
                    EntityDiscovered(
                        scan_id=job.scan_id,
                        tool_name="crtsh",
                        entity_type="subdomain",
                        entity_value="sub.example.com",
                    )
                )
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        orchestrator = EventDrivenOrchestrator(
            bus=bus,
            registry=registry,
            execute_fn=mock_execute,
        )

        config = ScanConfig(seed="example.com", max_iterations=10)
        result = await orchestrator.run_scan("example.com", config)

        assert result.status == "completed"
        assert call_count["crtsh"] == 1
        assert call_count["httpx"] == 1

        # Verify event flow
        selected = collector.of_type(ToolSelected)
        tool_names = [e.tool_name for e in selected]
        assert "crtsh" in tool_names
        assert "httpx" in tool_names

    @pytest.mark.asyncio
    async def test_event_flow_entity_to_tool_selected(self):
        """EntityDiscovered events lead to ToolSelected for dependent tools."""
        bus = EventBus()
        collector = EventCollector(bus)

        discovery = ToolSpec(
            name="discovery",
            enabled=True,
            consumes=["domain"],
            produces=["subdomain"],
            supported_input_types=["domain"],
            output_types=["subdomain"],
        )
        enricher = ToolSpec(
            name="enricher",
            enabled=True,
            consumes=["subdomain"],
            produces=["live_host"],
            supported_input_types=["subdomain"],
            output_types=["live_host"],
        )
        registry = _make_registry(discovery, enricher)

        async def mock_execute(job: ScheduledJob) -> ExecutionResult:
            if job.tool_name == "discovery":
                await bus.publish(
                    EntityDiscovered(
                        scan_id=job.scan_id,
                        tool_name="discovery",
                        entity_type="subdomain",
                        entity_value="api.example.com",
                    )
                )
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        orchestrator = EventDrivenOrchestrator(
            bus=bus,
            registry=registry,
            execute_fn=mock_execute,
        )

        await orchestrator.run_scan("example.com", ScanConfig(seed="example.com", max_iterations=10))

        # Should have ToolSelected for enricher after EntityDiscovered(subdomain)
        selected = collector.of_type(ToolSelected)
        assert any(e.tool_name == "enricher" for e in selected)

    @pytest.mark.asyncio
    async def test_parallel_scheduling_respects_concurrency(self):
        """Parallel executor respects global concurrency limits."""
        bus = EventBus()
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def slow_execute(job: ScheduledJob) -> ExecutionResult:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            await asyncio.sleep(0.02)
            async with lock:
                current_concurrent -= 1
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        # Create executor with global limit of 2
        executor = ParallelExecutor(bus=bus, global_limit=2)

        jobs = [
            ScheduledJob(tool_name=f"tool{i}", scan_id="scan1", inputs={})
            for i in range(5)
        ]

        await executor.execute_batch(jobs, slow_execute)

        # max_concurrent should not exceed the global limit
        assert max_concurrent <= 2
        assert executor.total_executed == 5

    @pytest.mark.asyncio
    async def test_per_tool_concurrency_limit(self):
        """Per-tool semaphore limits concurrent instances of the same tool."""
        bus = EventBus()
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def slow_execute(job: ScheduledJob) -> ExecutionResult:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            await asyncio.sleep(0.02)
            async with lock:
                current_concurrent -= 1
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        # Global limit of 10, but per-tool limit of 1 for "nmap"
        executor = ParallelExecutor(
            bus=bus,
            global_limit=10,
            per_tool_concurrency={"nmap": 1},
        )

        jobs = [
            ScheduledJob(tool_name="nmap", scan_id="scan1", inputs={})
            for _ in range(4)
        ]

        await executor.execute_batch(jobs, slow_execute)

        assert max_concurrent <= 1
        assert executor.total_executed == 4

    @pytest.mark.asyncio
    async def test_retry_on_tool_failure(self):
        """A failing tool emits ToolFailed with retryable=True."""
        bus = EventBus()
        collector = EventCollector(bus)
        attempts = {"count": 0}

        async def failing_execute(job: ScheduledJob) -> ExecutionResult:
            attempts["count"] += 1
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=False,
                exit_code=1,
                error="connection timeout",
            )

        executor = ParallelExecutor(bus=bus, global_limit=5)
        job = ScheduledJob(tool_name="unstable_tool", scan_id="scan1", inputs={})

        results = await executor.execute_batch([job], failing_execute)

        assert len(results) == 1
        assert not results[0].success
        assert results[0].error == "connection timeout"

        # ToolFailed event should have been emitted
        failed = collector.of_type(ToolFailed)
        assert len(failed) == 1
        assert failed[0].tool_name == "unstable_tool"
        assert failed[0].retryable is True

    @pytest.mark.asyncio
    async def test_tool_timeout_handling(self):
        """A tool that raises an exception is handled gracefully."""
        bus = EventBus()
        collector = EventCollector(bus)

        async def timeout_execute(job: ScheduledJob) -> ExecutionResult:
            raise asyncio.TimeoutError("tool execution exceeded deadline")

        executor = ParallelExecutor(bus=bus, global_limit=5)
        job = ScheduledJob(tool_name="slow_tool", scan_id="scan1", inputs={})

        results = await executor.execute_batch([job], timeout_execute)

        assert len(results) == 1
        assert not results[0].success
        assert "exceeded deadline" in results[0].error

        # Should emit ToolFailed
        failed = collector.of_type(ToolFailed)
        assert len(failed) == 1
        assert failed[0].tool_name == "slow_tool"

    @pytest.mark.asyncio
    async def test_orchestrator_tracks_entities_discovered(self):
        """Orchestrator result includes total entities discovered."""
        bus = EventBus()

        tool = ToolSpec(
            name="scanner",
            enabled=True,
            consumes=["domain"],
            produces=["subdomain"],
            supported_input_types=["domain"],
            output_types=["subdomain"],
        )
        registry = _make_registry(tool)

        async def execute_with_entities(job: ScheduledJob) -> ExecutionResult:
            for i in range(3):
                await bus.publish(
                    EntityDiscovered(
                        scan_id=job.scan_id,
                        tool_name="scanner",
                        entity_type="subdomain",
                        entity_value=f"sub{i}.example.com",
                    )
                )
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        orchestrator = EventDrivenOrchestrator(
            bus=bus, registry=registry, execute_fn=execute_with_entities
        )
        result = await orchestrator.run_scan("example.com", ScanConfig(seed="example.com"))

        assert result.total_entities == 3

    @pytest.mark.asyncio
    async def test_orchestrator_records_errors(self):
        """Orchestrator result includes error details from failed tools."""
        bus = EventBus()

        tool = ToolSpec(
            name="broken",
            enabled=True,
            consumes=["domain"],
            supported_input_types=["domain"],
        )
        registry = _make_registry(tool)

        async def failing(job: ScheduledJob) -> ExecutionResult:
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=False,
                exit_code=2,
                error="segfault in parser",
            )

        orchestrator = EventDrivenOrchestrator(
            bus=bus, registry=registry, execute_fn=failing
        )
        result = await orchestrator.run_scan("example.com", ScanConfig(seed="example.com"))

        assert len(result.errors) >= 1
        assert "segfault" in result.errors[0]
