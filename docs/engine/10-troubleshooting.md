# Troubleshooting

## Common Issues

### Tool Never Gets Scheduled

**Symptoms:** A tool exists in the registry but never appears in ToolSelected events.

**Causes:**
1. Tool is disabled (`enabled: false` in YAML)
2. Tool's input types do not match any available keys
3. Tool already completed in this scan (check `_completed_tools`)
4. Tool is currently running (check `_running_tools`)

**Debug:**
```python
# Check if tool is in registry
spec = registry.get("mytool")
assert spec is not None and spec.enabled

# Check available keys
available = scheduler._available_keys[scan_id]
consumed = set(spec.supported_input_types) | set(spec.consumes)
print(f"Available: {available}, Needs: {consumed}, Overlap: {consumed & available}")
```

### Tool Stays Blocked Forever

**Symptoms:** ToolBlocked event fires but ToolReady never follows.

**Causes:**
1. No tool produces the required key type
2. The producing tool failed
3. Pending key was created but never resolved

**Debug:**
```python
# Check blocked state
blocked = scheduler._blocked_tools[scan_id]
print(f"Blocked tools: {blocked}")

# Check pending keys in DB
with session_scope() as s:
    store = PendingKeyStore(s)
    pending = store.get_pending_for_tool(scan_id, "live_host")
    print(f"Pending live_host keys: {len(pending)}")
```

### Duplicate Entities in Database

**Symptoms:** Same asset appears multiple times.

**Causes:**
1. Different `dedupe_key` computation (check hash inputs)
2. Missing UniqueConstraint on the table
3. Concurrent inserts without proper locking

**Fix:** Ensure `dedupe_key` is computed from `f"{type}:{value}"` consistently.

### Scan Never Converges

**Symptoms:** Scan runs until `max_iterations` is hit.

**Causes:**
1. Circular dependency: Tool A produces keys for Tool B which produces keys for A
2. Entity discovery triggers re-scheduling of already-completed tools
3. `max_iterations` set too low for the number of tools

**Debug:**
```python
# Check iteration count
print(f"Iterations: {scheduler._iterations[scan_id]}")
print(f"Running: {scheduler._running_tools[scan_id]}")
print(f"Eligible: {[t.name for t in scheduler.select_eligible_tools(scan_id)]}")
```

### Concurrency Limit Not Respected

**Symptoms:** More jobs run in parallel than the configured limit.

**Causes:**
1. Using `execute_batch` without going through `ParallelExecutor`
2. Multiple executor instances sharing the same event bus
3. Semaphore created with wrong limit value

**Debug:**
```python
print(f"Active: {executor.active_count}")
print(f"Global limit: {executor._global_semaphore._value}")
```

### Test Failures with "Table Already Exists"

**Symptoms:** Tests fail with SQLAlchemy errors about existing tables.

**Fix:** Each test should use `tmp_path` for an isolated SQLite database:
```python
@pytest.fixture()
def fresh_db(tmp_path):
    db.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_all()
    return tmp_path
```

### ToolFailed But No Error Details

**Symptoms:** ToolFailed event has empty error string.

**Causes:**
1. Exception was swallowed in the execute function
2. Tool exited with non-zero but wrote to a file instead of stderr

**Fix:** Always populate the `error` field in `ExecutionResult`:
```python
return ExecutionResult(
    tool_name=job.tool_name,
    scan_id=job.scan_id,
    success=False,
    exit_code=result.returncode,
    error=result.stderr or f"Exit code {result.returncode}",
)
```

## FAQ

**Q: Can I run the engine alongside the existing pipeline?**
A: Yes. The engine is additive. The `ReconPipeline` class is unmodified and
continues to work for linear scans.

**Q: How do I add a tool that needs multiple input types?**
A: Set `consumes: [type_a, type_b]`. The scheduler will only schedule the tool
when both types have resolved keys available.

**Q: What happens if a tool times out?**
A: The executor catches `asyncio.TimeoutError`, emits `ToolFailed` with
`retryable=True`, and records the failure. The scheduler marks it as completed
(failed) for this iteration.

**Q: How do I force a tool to re-run?**
A: Change its inputs (different fingerprint) or delete its `ToolRun` record
from the database.

**Q: Can I add custom events?**
A: Yes. Subclass `EngineEvent` and subscribe handlers via `bus.subscribe()`.
