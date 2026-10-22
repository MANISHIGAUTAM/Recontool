# Parallel Execution

## Concurrency Model

The `ParallelExecutor` implements three layers of concurrency control:

```
┌─────────────────────────────────────────────────┐
│           Global Semaphore (default: 20)        │
│  ┌──────────────────────────────────────────┐   │
│  │     Per-Tool Semaphore (default: 5)      │   │
│  │  ┌───────────────────────────────────┐   │   │
│  │  │  Per-Host Semaphore (default: 3)  │   │   │
│  │  │     [actual execution here]       │   │   │
│  │  └───────────────────────────────────┘   │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

The most restrictive limit wins.

## Configuration

```python
from recontool.engine.orchestrator import ScanConfig

config = ScanConfig(
    seed="example.com",
    global_concurrency=20,           # Max parallel tasks overall
    per_tool_concurrency={
        "nuclei": 3,                 # Max 3 nuclei instances
        "naabu": 2,                  # Max 2 port scanners
    },
    per_host_concurrency={
        "target.com": 5,             # Max 5 connections to target
    },
)
```

## Safety Rules

1. **Tools marked `parallel_safe=False`** are serialized (per-tool limit = 1)
2. **Tools with `concurrency_safety=False`** share mutable output and must not overlap
3. **Discovery tools** get higher default concurrency (fan-out is safe)
4. **Active tools** respect per-host limits to avoid rate-limiting

## Execution Flow

```python
async def execute_one(job, execute_fn):
    # 1. Acquire global semaphore
    async with global_semaphore:
        # 2. Acquire per-tool semaphore
        async with tool_semaphore:
            # 3. Acquire per-host semaphore (if applicable)
            async with host_semaphore:
                # 4. Emit ToolRunning event
                # 5. Call execute_fn(job)
                # 6. Emit ToolCompleted/ToolFailed
```

## Batch Execution

```python
executor = ParallelExecutor(bus=bus, global_limit=10)
jobs = [ScheduledJob(tool_name="subfinder", scan_id="s1", inputs={})]
results = await executor.execute_batch(jobs, my_execute_fn)
```

All jobs in a batch run concurrently (within limits). Results are gathered
when all complete. Exceptions are caught and returned as failed results.

## Monitoring

```python
executor.active_count    # Currently running jobs
executor.total_executed  # Total jobs completed since start
```
