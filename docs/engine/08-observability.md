# Observability

## Overview

The engine provides structured logging, in-memory metrics, and correlation IDs
for end-to-end tracing of scan execution.

## Structured Logging

The `EngineLogger` emits dict-based log entries compatible with JSON logging
pipelines (structlog, ELK, CloudWatch).

### Log Entry Format

Every entry includes:
- `event` - event type string (e.g., `tool_start`, `tool_complete`)
- `scan_id` - scan identifier
- `correlation_id` - unique ID for tracing across events
- `timestamp` - ISO 8601 UTC timestamp

### Example Entries

```json
{"event": "tool_start", "scan_id": "abc-123", "tool_run_id": "run-456",
 "tool_name": "subfinder", "correlation_id": "corr-789", "timestamp": "2024-01-20T15:30:00Z"}

{"event": "tool_complete", "scan_id": "abc-123", "tool_run_id": "run-456",
 "tool_name": "subfinder", "duration_ms": 4520, "entity_count": 12,
 "correlation_id": "corr-789", "timestamp": "2024-01-20T15:30:04Z"}
```

### Usage

```python
from recontool.engine.logging import EngineLogger

logger = EngineLogger(correlation_id="my-trace-id")
logger.log_tool_start("run-001", "scan-001", "subfinder", inputs={"domain": ["ex.com"]})
logger.log_tool_complete("run-001", "scan-001", "subfinder", duration_ms=3000, entity_count=5)

# Access all entries
for entry in logger.entries:
    print(entry)
```

## Metrics

The `MetricsCollector` tracks counters, gauges, and histograms.

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `tool_runs_total` | Counter | Tool executions by (tool, status) |
| `tool_duration_seconds` | Histogram | Execution time per tool |
| `entities_discovered_total` | Counter | Entities by type |
| `pending_keys_created_total` | Counter | Total keys created |
| `pending_keys_resolved_total` | Counter | Total keys resolved |
| `duplicate_suppression_total` | Counter | Deduplicated entities |
| `retry_total` | Counter | Retry attempts per tool |
| `scan_depth_current` | Gauge | Current recursion depth |
| `queue_depth_current` | Gauge | Jobs waiting in queue |
| `blocked_tools_current` | Gauge | Tools blocked on keys |

### Usage

```python
from recontool.engine.metrics import MetricsCollector

metrics = MetricsCollector()
metrics.record_tool_run("subfinder", "success", duration=4.5)
metrics.record_entity("subdomain")
metrics.record_pending_key("created")

# Export snapshot
snapshot = metrics.snapshot()
json_str = metrics.to_json()
```

## Correlation IDs

Every `EngineEvent` carries a `correlation_id` (UUID). Use this to:
- Trace a single entity from discovery through persistence
- Link tool execution to its output entities
- Debug why a tool was scheduled or blocked

## Integration with External Systems

The structured logging format is compatible with:
- **ELK/OpenSearch** - ship JSON logs via Filebeat
- **Datadog/CloudWatch** - parse structured dict entries
- **Prometheus** - expose metrics snapshot via HTTP endpoint
- **Jaeger/Zipkin** - map correlation_ids to trace spans
