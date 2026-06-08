# Event-Driven Engine: Architecture Overview

## Summary

The event-driven engine is a parallel, reactive orchestration layer for Recontool.
It replaces the linear phase-based pipeline with an event bus that connects tool
execution, entity discovery, dependency tracking, and scheduling into a single
convergence loop.

## High-Level Architecture

```
                        ┌──────────────────┐
                        │  ScanRequested   │
                        └────────┬─────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────┐
│                       EventBus                           │
│  (in-process async pub/sub - routes all EngineEvents)    │
└───┬──────────┬──────────┬──────────┬──────────┬──────────┘
    │          │          │          │          │
    ▼          ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Scheduler│ │Executor│ │Pending │ │Incremental│ │Output │
│        │ │        │ │  Keys  │ │  Engine │ │Normal. │
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘
    │          │          │          │          │
    └──────────┴──────────┴──────────┴──────────┘
                        │
                        ▼
              ┌──────────────────┐
              │   SQLite / PG    │
              │  (Assets, Scans, │
              │  PendingKeys,    │
              │  ToolRuns)       │
              └──────────────────┘
```

## Components

| Component | Module | Responsibility |
|-----------|--------|----------------|
| **EventBus** | `engine/events.py` | Async pub/sub; routes typed events to subscribers |
| **Scheduler** | `engine/scheduler.py` | Selects eligible tools, manages job queue, detects convergence |
| **Executor** | `engine/executor.py` | Parallel execution with global/per-tool/per-host concurrency limits |
| **PendingKeyStore** | `engine/pending_keys.py` | Tracks inter-tool dependencies (data keys that must be resolved) |
| **IncrementalEngine** | `engine/incremental.py` | Fingerprint-based skip/rerun decisions |
| **ToolRegistry** | `engine/registry.py` | Pydantic-validated tool specs loaded from YAML |
| **DependencyChecker** | `engine/dependency.py` | Runtime checks: binary available, keys set, versions match |
| **OutputNormalizer** | `engine/output.py` | Parses raw tool output into structured entities |
| **AIDecisionService** | `engine/ai_decision.py` | Classifies entities: persist, discard, trigger downstream |
| **Orchestrator** | `engine/orchestrator.py` | Top-level `run_scan()` API that wires everything together |

## Data Flow

1. **ScanRequested** - orchestrator receives a seed domain and config
2. **ToolSelected** - scheduler picks tools whose input types match available keys
3. **ToolRunning** - executor acquires semaphores and starts execution
4. **EntityDiscovered** - tool output parsed into entities
5. **PendingKeyCreated** - new dependencies registered
6. **PendingKeyResolved** - dependencies satisfied by downstream tools
7. **ToolCompleted / ToolFailed** - lifecycle tracking
8. **ScanCompleted** - convergence detected, all tools done

## Convergence

The engine converges when:
- No tools are currently running
- No eligible tools remain (all inputs consumed, all completed)
- Or max iteration limit reached

## Relationship to Existing Pipeline

The event-driven engine runs alongside the existing `ReconPipeline`. The phased
pipeline (P1-P6) continues to work for simple linear scans. The engine adds:
- True parallelism with concurrency controls
- Dependency-driven scheduling (no fixed phase ordering)
- Incremental re-execution (fingerprint-based skip logic)
- Observable event stream for debugging and metrics
