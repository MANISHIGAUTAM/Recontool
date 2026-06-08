# Incremental Scans

## Overview

The `IncrementalEngine` uses SHA-256 fingerprinting to determine whether a
tool needs to re-execute. This avoids redundant work on repeated scans and
enables efficient delta reprocessing.

## Fingerprinting

Three fingerprints are computed per tool run:

| Fingerprint | What It Hashes | Detects |
|-------------|---------------|---------|
| **Input** | Tool name + sorted inputs dict | Changed targets/seeds |
| **Output** | Tool name + raw output | Changed results |
| **Config** | Name + version + invocation + timeout + retry + rate limits | Updated tool configuration |

### Computing Fingerprints

```python
from recontool.engine.fingerprint import (
    fingerprint_inputs,
    fingerprint_output,
    fingerprint_config,
    has_changed,
)

fp1 = fingerprint_inputs("subfinder", {"domain": ["example.com"]})
fp2 = fingerprint_inputs("subfinder", {"domain": ["other.com"]})
assert has_changed(fp1, fp2)  # True - different inputs
```

## Rerun Decision Logic

A tool should re-run if ANY of these conditions hold:

1. **Never run before** in this scan
2. **Previous run failed** (always retry failures)
3. **Input fingerprint changed** (new targets available)
4. **Config fingerprint changed** (tool updated)
5. **Staleness exceeded** (default: 1 hour)

```python
from recontool.engine.incremental import IncrementalEngine

engine = IncrementalEngine(session)
should_run = engine.should_rerun(
    tool_name="subfinder",
    scan_id="scan-001",
    current_inputs={"domain": ["example.com"]},
    tool_spec=registry.get("subfinder"),
    max_age_seconds=3600,
)
```

## Staleness

Tools that ran successfully but exceeded `max_age_seconds` are considered
stale and eligible for re-execution:

```python
stale = engine.get_stale_tools("scan-001", max_age_seconds=3600)
# Returns: ["subfinder", "crtsh"]  (ran > 1 hour ago)
```

## Delta Reprocessing

When a tool re-runs with changed inputs:
1. New output is compared against previous output fingerprint
2. Only genuinely new entities are emitted as `EntityDiscovered`
3. Existing entities are not re-persisted (dedupe_key prevents duplicates)
4. The ToolRun record is updated with new fingerprints

## Database Schema

```sql
CREATE TABLE tool_run (
    id INTEGER PRIMARY KEY,
    scan_id VARCHAR(36),
    tool_name VARCHAR(128),
    status VARCHAR(24),
    input_fingerprint VARCHAR(64),
    output_fingerprint VARCHAR(64),
    started_at DATETIME,
    finished_at DATETIME,
    exit_code INTEGER,
    duration_ms INTEGER,
    retry_count INTEGER DEFAULT 0
);
```
