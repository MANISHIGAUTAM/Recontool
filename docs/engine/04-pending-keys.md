# Pending Keys

## Overview

Pending keys track data dependencies between tools. A pending key represents
a piece of data that one tool produces and another tool requires before it
can execute.

## Lifecycle

```
                create_key()          resolve_key()
  [nonexistent] ──────────> [pending] ────────────> [resolved]
                               │
                               └─── (timeout) ───> [expired]
```

## Key Types

| Key Type | Created By | Resolved By | Unlocks |
|----------|-----------|-------------|---------|
| `live_host` | crtsh, subfinder | httpx, dnsx | nuclei, katana, naabu |
| `open_port` | naabu | - (self-resolving) | service-specific scanners |
| `subdomain` | crtsh | - (immediately available) | httpx, dnsx |

## Usage

### Creating a Key

```python
from recontool.engine.pending_keys import PendingKeyStore
from recontool.core.db import session_scope

with session_scope() as session:
    store = PendingKeyStore(session)
    record = store.create_key(
        scan_id="scan-001",
        key_type="live_host",
        key_value="api.example.com",
        created_by_tool="crtsh",
    )
```

### Resolving a Key

```python
with session_scope() as session:
    store = PendingKeyStore(session)
    resolved = store.resolve_key(
        scan_id="scan-001",
        key_type="live_host",
        key_value="api.example.com",
        resolved_by_tool="httpx",
    )
```

### Checking Tool Readiness

```python
with session_scope() as session:
    store = PendingKeyStore(session)
    # nuclei needs live_host and open_port
    ready = store.is_tool_ready("scan-001", ["live_host", "open_port"])
```

## Rules

1. **One key per (scan_id, key_type, key_value)** - no duplicates
2. **Resolution is permanent** - once resolved, a key cannot revert to pending
3. **Readiness requires at least one resolved key per type** - `is_tool_ready()`
   checks that every required key type has at least one resolved record
4. **The scheduler uses pending keys to decide blocking** - tools that consume
   a key type stay blocked until that type has resolved keys

## Database Schema

```sql
CREATE TABLE pending_key (
    id INTEGER PRIMARY KEY,
    scan_id VARCHAR(36),
    key_type VARCHAR(64),
    key_value VARCHAR(1024),
    status VARCHAR(16) DEFAULT 'pending',
    created_by_tool VARCHAR(128),
    resolved_by_tool VARCHAR(128),
    created_at DATETIME,
    resolved_at DATETIME,
    fingerprint VARCHAR(64)
);
```

## Integration with Scheduler

When a `PendingKeyResolved` event fires:
1. Scheduler adds the key type to `_available_keys`
2. Scheduler re-checks all blocked tools
3. Any tool whose required keys are now all available gets unblocked
4. `ToolReady` event is emitted for each unblocked tool
