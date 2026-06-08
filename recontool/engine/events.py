"""Typed event classes and in-process async pub/sub EventBus.

All engine events are immutable dataclasses carrying a timestamp, scan_id,
and correlation_id for traceability.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Type


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineEvent:
    """Base class for all engine events."""

    scan_id: str
    correlation_id: str = field(default_factory=_uuid)
    timestamp: dt.datetime = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Scan lifecycle
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScanRequested(EngineEvent):
    """A new scan has been requested."""

    seed: str = ""
    seed_type: str = "domain"
    profile: str = "normal"


@dataclass(frozen=True)
class ScanCompleted(EngineEvent):
    """The scan has finished (all tools done, no more pending keys)."""

    status: str = "completed"
    total_tools_run: int = 0
    total_entities: int = 0


# ---------------------------------------------------------------------------
# Tool lifecycle
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolSelected(EngineEvent):
    """A tool has been selected by the scheduler for this scan."""

    tool_name: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ToolDependencyChecked(EngineEvent):
    """Dependencies for a tool have been evaluated."""

    tool_name: str = ""
    satisfied: bool = True
    missing_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolReady(EngineEvent):
    """A tool is ready to execute (all dependencies satisfied)."""

    tool_name: str = ""


@dataclass(frozen=True)
class ToolBlocked(EngineEvent):
    """A tool cannot run because of missing pending keys."""

    tool_name: str = ""
    blocked_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolRunning(EngineEvent):
    """A tool has started executing."""

    tool_name: str = ""
    command: str = ""


@dataclass(frozen=True)
class ToolArtifactProduced(EngineEvent):
    """A tool produced an output artifact (file, data blob)."""

    tool_name: str = ""
    artifact_path: str = ""
    artifact_type: str = ""


@dataclass(frozen=True)
class EntityDiscovered(EngineEvent):
    """A new entity has been discovered by a tool."""

    tool_name: str = ""
    entity_type: str = ""
    entity_value: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PendingKeyCreated(EngineEvent):
    """A new pending key was created (output from a tool)."""

    tool_name: str = ""
    key_type: str = ""
    key_value: str = ""


@dataclass(frozen=True)
class PendingKeyResolved(EngineEvent):
    """A pending key has been resolved (dependency satisfied)."""

    tool_name: str = ""
    key_type: str = ""
    key_value: str = ""


@dataclass(frozen=True)
class ToolCompleted(EngineEvent):
    """A tool finished successfully."""

    tool_name: str = ""
    exit_code: int = 0
    entity_count: int = 0
    duration_ms: int = 0


@dataclass(frozen=True)
class ToolFailed(EngineEvent):
    """A tool failed."""

    tool_name: str = ""
    exit_code: int = 1
    error: str = ""
    retryable: bool = False


# ---------------------------------------------------------------------------
# EventBus - in-process async pub/sub
# ---------------------------------------------------------------------------

Handler = Callable[[EngineEvent], Coroutine[Any, Any, None]]


class EventBus:
    """In-process async pub/sub for engine events.

    Usage:
        bus = EventBus()
        bus.subscribe(ToolCompleted, my_handler)
        await bus.publish(ToolCompleted(scan_id="abc", tool_name="nmap"))
    """

    def __init__(self) -> None:
        self._handlers: dict[Type[EngineEvent], list[Handler]] = {}

    def subscribe(self, event_type: Type[EngineEvent], handler: Handler) -> None:
        """Register a handler for a specific event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: Type[EngineEvent], handler: Handler) -> None:
        """Remove a handler for a specific event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: EngineEvent) -> None:
        """Dispatch an event to all registered handlers for its type."""
        handlers = self._handlers.get(type(event), [])
        if handlers:
            await asyncio.gather(*(h(event) for h in handlers))

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
