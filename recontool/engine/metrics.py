"""Metrics collection for the event-driven engine.

Provides in-memory counters and gauges for engine operations. No external
dependencies required - uses simple dict-based storage with JSON export.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """In-memory metrics collector for engine observability.

    Tracks counters, gauges, and histograms for tool runs, entity
    discovery, pending keys, and scheduling decisions.
    """

    def __init__(self) -> None:
        # Counters (monotonically increasing)
        self._tool_runs_total: dict[tuple[str, str], int] = defaultdict(int)
        self._tool_duration_seconds: dict[str, list[float]] = defaultdict(list)
        self._entities_discovered_total: dict[str, int] = defaultdict(int)
        self._pending_keys_created_total: int = 0
        self._pending_keys_resolved_total: int = 0
        self._duplicate_suppression_total: int = 0
        self._retry_total: dict[str, int] = defaultdict(int)

        # Gauges (can go up and down)
        self._scan_depth_current: int = 0
        self._queue_depth_current: int = 0
        self._blocked_tools_current: int = 0

        # Metadata
        self._started_at: float = time.time()

    def record_tool_run(
        self, tool: str, status: str, duration: float = 0.0
    ) -> None:
        """Record a tool execution.

        Args:
            tool: Name of the tool.
            status: Execution status (e.g., 'success', 'failed', 'timeout').
            duration: Duration in seconds.
        """
        self._tool_runs_total[(tool, status)] += 1
        if duration > 0:
            self._tool_duration_seconds[tool].append(duration)

    def record_entity(self, entity_type: str) -> None:
        """Record discovery of an entity."""
        self._entities_discovered_total[entity_type] += 1

    def record_pending_key(self, action: str) -> None:
        """Record a pending key action (created or resolved).

        Args:
            action: Either 'created' or 'resolved'.
        """
        if action == "created":
            self._pending_keys_created_total += 1
        elif action == "resolved":
            self._pending_keys_resolved_total += 1

    def record_duplicate_suppression(self) -> None:
        """Record that a duplicate entity was suppressed."""
        self._duplicate_suppression_total += 1

    def record_retry(self, tool: str) -> None:
        """Record a retry attempt for a tool."""
        self._retry_total[tool] += 1

    def set_scan_depth(self, depth: int) -> None:
        """Update the current scan depth gauge."""
        self._scan_depth_current = depth

    def set_queue_depth(self, depth: int) -> None:
        """Update the current queue depth gauge."""
        self._queue_depth_current = depth

    def set_blocked_tools(self, count: int) -> None:
        """Update the current blocked tools gauge."""
        self._blocked_tools_current = count

    def snapshot(self) -> dict[str, Any]:
        """Return a point-in-time snapshot of all metrics.

        Returns a dict suitable for JSON serialization.
        """
        # Aggregate tool run totals
        tool_runs: dict[str, dict[str, int]] = {}
        for (tool, status), count in self._tool_runs_total.items():
            tool_runs.setdefault(tool, {})[status] = count

        # Compute duration stats
        tool_durations: dict[str, dict[str, float]] = {}
        for tool, durations in self._tool_duration_seconds.items():
            if durations:
                tool_durations[tool] = {
                    "count": len(durations),
                    "total": sum(durations),
                    "min": min(durations),
                    "max": max(durations),
                    "avg": sum(durations) / len(durations),
                }

        return {
            "tool_runs_total": tool_runs,
            "tool_duration_seconds": tool_durations,
            "entities_discovered_total": dict(self._entities_discovered_total),
            "pending_keys_created_total": self._pending_keys_created_total,
            "pending_keys_resolved_total": self._pending_keys_resolved_total,
            "scan_depth_current": self._scan_depth_current,
            "duplicate_suppression_total": self._duplicate_suppression_total,
            "queue_depth_current": self._queue_depth_current,
            "retry_total": dict(self._retry_total),
            "blocked_tools_current": self._blocked_tools_current,
            "uptime_seconds": time.time() - self._started_at,
        }

    def to_json(self) -> str:
        """Export metrics snapshot as a JSON string."""
        return json.dumps(self.snapshot(), indent=2)
