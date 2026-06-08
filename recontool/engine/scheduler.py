"""Event-driven job scheduler.

Consumes engine events and controls tool execution scheduling. Implements
the core loop: discover entities -> create pending keys -> resolve pending
keys -> schedule tools -> repeat until convergence or depth limit.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from recontool.engine.events import (
    EntityDiscovered,
    EventBus,
    PendingKeyResolved,
    ScanCompleted,
    ScanRequested,
    ToolCompleted,
    ToolFailed,
    ToolReady,
    ToolSelected,
)
from recontool.engine.registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """A job queued for execution."""

    tool_name: str
    scan_id: str
    inputs: dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    depth: int = 0


class EventDrivenScheduler:
    """Scheduler that subscribes to EventBus events and triggers downstream scheduling.

    The scheduler tracks:
    - Available keys (resolved pending keys per scan)
    - Running tools (to avoid double-scheduling)
    - Completed tools (to avoid redundant re-runs within an iteration)
    - Blocked tools (waiting on pending keys)
    """

    def __init__(
        self,
        bus: EventBus,
        registry: ToolRegistry,
        max_depth: int = 5,
        max_iterations: int = 50,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._max_depth = max_depth
        self._max_iterations = max_iterations

        # Per-scan state
        self._available_keys: dict[str, set[str]] = {}  # scan_id -> set of key_types
        self._available_entities: dict[str, dict[str, list[str]]] = {}  # scan_id -> {type: [values]}
        self._running_tools: dict[str, set[str]] = {}  # scan_id -> set of tool_names
        self._completed_tools: dict[str, set[str]] = {}  # scan_id -> set of tool_names
        self._blocked_tools: dict[str, dict[str, list[str]]] = {}  # scan_id -> {tool: [keys]}
        self._iterations: dict[str, int] = {}  # scan_id -> count
        self._job_queue: asyncio.Queue[ScheduledJob] = asyncio.Queue()

        # Subscribe to events
        self._bus.subscribe(EntityDiscovered, self.on_entity_discovered)
        self._bus.subscribe(ToolCompleted, self.on_tool_completed)
        self._bus.subscribe(ToolFailed, self.on_tool_failed)
        self._bus.subscribe(PendingKeyResolved, self._on_key_resolved)

    @property
    def job_queue(self) -> asyncio.Queue[ScheduledJob]:
        """Access the job queue for the executor."""
        return self._job_queue

    async def submit_scan(
        self, scan_id: str, seed: str, config: dict[str, Any] | None = None
    ) -> None:
        """Initialize scheduling for a new scan."""
        self._available_keys[scan_id] = set()
        self._available_entities[scan_id] = {}
        self._running_tools[scan_id] = set()
        self._completed_tools[scan_id] = set()
        self._blocked_tools[scan_id] = {}
        self._iterations[scan_id] = 0

        # Emit ScanRequested
        await self._bus.publish(ScanRequested(
            scan_id=scan_id,
            seed=seed,
            seed_type=(config or {}).get("seed_type", "domain"),
            profile=(config or {}).get("profile", "normal"),
        ))

        # Determine initial seed type and add it as an available key
        seed_type = (config or {}).get("seed_type", "domain")
        self._available_keys[scan_id].add(seed_type)
        self._available_entities[scan_id].setdefault(seed_type, []).append(seed)

        # Schedule tools that accept the seed type
        eligible = self.select_eligible_tools(scan_id)
        for tool_spec in eligible:
            await self.schedule_tool(scan_id, tool_spec.name, {seed_type: [seed]})

    async def on_entity_discovered(self, event: EntityDiscovered) -> None:
        """Handle entity discovery by updating available keys and scheduling."""
        scan_id = event.scan_id
        if scan_id not in self._available_keys:
            return

        # Add the entity type as an available key
        self._available_keys[scan_id].add(event.entity_type)

        # Track the entity value for downstream tool input context
        self._available_entities.setdefault(scan_id, {}).setdefault(
            event.entity_type, []
        ).append(event.entity_value)

        # Check if any blocked tools can now be scheduled
        await self._check_blocked_tools(scan_id)

    async def on_tool_completed(self, event: ToolCompleted) -> None:
        """Handle tool completion by updating state and checking convergence."""
        scan_id = event.scan_id
        if scan_id not in self._running_tools:
            return

        self._running_tools[scan_id].discard(event.tool_name)
        self._completed_tools[scan_id].add(event.tool_name)
        self._iterations[scan_id] = self._iterations.get(scan_id, 0) + 1

        # Check if we can schedule more tools
        eligible = self.select_eligible_tools(scan_id)
        for tool_spec in eligible:
            # Pass available key types as inputs context for downstream tools
            inputs = self._build_inputs_for_tool(scan_id, tool_spec)
            await self.schedule_tool(scan_id, tool_spec.name, inputs)

        # Check convergence
        if self.check_convergence(scan_id):
            await self._bus.publish(ScanCompleted(
                scan_id=scan_id,
                status="completed",
                total_tools_run=len(self._completed_tools[scan_id]),
            ))

    async def on_tool_failed(self, event: ToolFailed) -> None:
        """Handle tool failure by updating state."""
        scan_id = event.scan_id
        if scan_id not in self._running_tools:
            return

        self._running_tools[scan_id].discard(event.tool_name)
        # Mark as completed (failed) to avoid re-scheduling in this iteration
        self._completed_tools[scan_id].add(event.tool_name)

        # Check convergence
        if self.check_convergence(scan_id):
            await self._bus.publish(ScanCompleted(
                scan_id=scan_id,
                status="completed_with_errors",
                total_tools_run=len(self._completed_tools[scan_id]),
            ))

    async def _on_key_resolved(self, event: PendingKeyResolved) -> None:
        """Handle pending key resolution."""
        scan_id = event.scan_id
        if scan_id not in self._available_keys:
            return
        self._available_keys[scan_id].add(event.key_type)
        await self._check_blocked_tools(scan_id)

    async def _check_blocked_tools(self, scan_id: str) -> None:
        """Re-check blocked tools to see if they can now be scheduled."""
        if scan_id not in self._blocked_tools:
            return

        available = self._available_keys.get(scan_id, set())
        unblocked: list[str] = []

        for tool_name, required_keys in list(self._blocked_tools[scan_id].items()):
            if all(k in available for k in required_keys):
                unblocked.append(tool_name)

        for tool_name in unblocked:
            del self._blocked_tools[scan_id][tool_name]
            tool_spec = self._registry.get(tool_name)
            if tool_spec:
                await self._bus.publish(ToolReady(scan_id=scan_id, tool_name=tool_name))
                inputs = self._build_inputs_for_tool(scan_id, tool_spec)
                await self.schedule_tool(scan_id, tool_name, inputs)

    def select_eligible_tools(self, scan_id: str) -> list[ToolSpec]:
        """Find tools eligible to run based on available keys.

        A tool is eligible if:
        - It consumes input types that are available as keys
        - It is not currently running
        - It has not already completed in this scan
        - It is enabled
        """
        available = self._available_keys.get(scan_id, set())
        running = self._running_tools.get(scan_id, set())
        completed = self._completed_tools.get(scan_id, set())
        eligible: list[ToolSpec] = []

        for tool_spec in self._registry.all_tools().values():
            if not tool_spec.enabled:
                continue
            if tool_spec.name in running or tool_spec.name in completed:
                continue

            # Check if any of the tool's consumed types are available
            consumed = set(tool_spec.supported_input_types) | set(tool_spec.consumes)
            if not consumed:
                continue
            if consumed & available:
                eligible.append(tool_spec)

        return eligible

    async def schedule_tool(
        self, scan_id: str, tool_name: str, inputs: dict[str, Any]
    ) -> None:
        """Queue a tool for execution."""
        if scan_id in self._running_tools and tool_name in self._running_tools[scan_id]:
            return
        if scan_id in self._completed_tools and tool_name in self._completed_tools[scan_id]:
            return

        self._running_tools.setdefault(scan_id, set()).add(tool_name)

        # Emit ToolSelected event
        await self._bus.publish(ToolSelected(
            scan_id=scan_id,
            tool_name=tool_name,
            reason="eligible_keys_available",
        ))

        job = ScheduledJob(
            tool_name=tool_name,
            scan_id=scan_id,
            inputs=inputs,
        )
        await self._job_queue.put(job)

    def _build_inputs_for_tool(self, scan_id: str, tool_spec: ToolSpec) -> dict[str, Any]:
        """Build inputs dict for a tool from available entity values.

        Maps the tool's consumed types to the discovered entity values,
        giving downstream tools context about which entities triggered them.
        """
        inputs: dict[str, Any] = {}
        entities = self._available_entities.get(scan_id, {})
        consumed = set(tool_spec.supported_input_types) | set(tool_spec.consumes)
        for key_type in consumed:
            values = entities.get(key_type)
            if values:
                inputs[key_type] = list(values)
        return inputs

    def check_convergence(self, scan_id: str) -> bool:
        """Check if the scan has converged (no more work to do).

        Converged when:
        - No tools are running
        - No tools are eligible to run
        - Max iterations not exceeded
        """
        running = self._running_tools.get(scan_id, set())
        if running:
            return False

        iterations = self._iterations.get(scan_id, 0)
        if iterations >= self._max_iterations:
            return True

        eligible = self.select_eligible_tools(scan_id)
        return len(eligible) == 0

    def has_running_tools(self, scan_id: str) -> bool:
        """Return True if any tools are still running for this scan."""
        return bool(self._running_tools.get(scan_id))

    def completed_tool_count(self, scan_id: str) -> set[str]:
        """Return the set of completed tool names for this scan."""
        return self._completed_tools.get(scan_id, set())
