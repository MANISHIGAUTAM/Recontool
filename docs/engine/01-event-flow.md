# Event Flow

## Overview

All engine communication happens through typed, immutable events dispatched via
the `EventBus`. Events carry a `scan_id`, `correlation_id`, and UTC timestamp
for traceability.

## Event Types

### Scan Lifecycle

| Event | When Fired | Handler |
|-------|-----------|---------|
| `ScanRequested` | User initiates a scan | Scheduler initializes state |
| `ScanCompleted` | Convergence detected | Orchestrator finalizes result |

### Tool Lifecycle

| Event | When Fired | Handler |
|-------|-----------|---------|
| `ToolSelected` | Scheduler picks a tool | Logged for audit |
| `ToolDependencyChecked` | Dependencies evaluated | Scheduler decides ready/blocked |
| `ToolReady` | All dependencies satisfied | Executor can proceed |
| `ToolBlocked` | Missing pending keys | Tool waits for resolution |
| `ToolRunning` | Execution started | Metrics counter incremented |
| `ToolArtifactProduced` | Output file created | Artifact store indexed |
| `ToolCompleted` | Successful execution | Scheduler marks complete, checks convergence |
| `ToolFailed` | Execution failed | Error recorded, retry evaluated |

### Data Flow

| Event | When Fired | Handler |
|-------|-----------|---------|
| `EntityDiscovered` | Tool output parsed | Scheduler updates available keys |
| `PendingKeyCreated` | New dependency registered | PendingKeyStore persists |
| `PendingKeyResolved` | Dependency satisfied | Scheduler unblocks waiting tools |

## Event Sequencing

```
ScanRequested
  -> ToolSelected (crtsh)
    -> ToolRunning (crtsh)
      -> EntityDiscovered (subdomain: sub.example.com)
      -> PendingKeyCreated (live_host: sub.example.com)
    -> ToolCompleted (crtsh)
  -> ToolSelected (httpx)
    -> ToolRunning (httpx)
      -> EntityDiscovered (live_host: sub.example.com)
      -> PendingKeyResolved (live_host: sub.example.com)
    -> ToolCompleted (httpx)
  -> ToolSelected (nuclei)  [unblocked by PendingKeyResolved]
    -> ToolRunning (nuclei)
    -> ToolCompleted (nuclei)
ScanCompleted
```

## Subscribing to Events

```python
from recontool.engine.events import EventBus, EntityDiscovered

bus = EventBus()

async def on_entity(event: EntityDiscovered) -> None:
    print(f"Found {event.entity_type}: {event.entity_value}")

bus.subscribe(EntityDiscovered, on_entity)
```

## Custom Events

All events inherit from `EngineEvent`. To add a new event type:

```python
@dataclass(frozen=True)
class MyCustomEvent(EngineEvent):
    custom_field: str = ""
```

The EventBus dispatches by exact type match - no inheritance-based routing.
