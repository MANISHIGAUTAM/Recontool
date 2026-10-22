# AI Decisioning

## Overview

The `AIDecisionService` classifies tool output entities and recommends actions.
The default implementation uses deterministic heuristics with zero AI API calls.
An AI-augmented path can override individual methods for smarter classification.

## Decision Buckets

| Bucket | Action | Example |
|--------|--------|---------|
| **persist** | Save to database | Valid subdomain discovered |
| **discard** | Drop (noise) | `localhost`, `example.com` references |
| **trigger_downstream** | Schedule more tools | New subdomain triggers httpx probe |
| **rescan_tools** | Re-run a tool | Low confidence suggests retry |
| **manual_review** | Flag for human | Findings always need review |

## Interface

```python
from recontool.engine.ai_decision import AIDecisionService
from recontool.engine.output import NormalizedOutput

service = AIDecisionService()
result = service.classify_results(normalized_output)

# Access decisions
for entity in result.persist:
    db.save(entity)
for entity in result.discard:
    pass  # dropped
for value in result.trigger_downstream:
    scheduler.schedule_for(value)
```

## Heuristic Rules

### Noise Detection

Entities matching these patterns are discarded:
- `localhost`, `127.0.0.1`, `::1`
- `example.com`, `example.org`, `example.net`
- `invalid`, `test.invalid`

### Downstream Triggers

Entity types that automatically trigger downstream processing:
- `subdomain` - triggers DNS resolve and HTTP probe
- `ip` - triggers port scanning
- `domain` - triggers subdomain enumeration

### Rescan Logic

A tool is recommended for rescan when its confidence score falls below 0.5.

### Manual Review

All entities of type `finding` are flagged for manual review.

## Mocking for Tests

```python
from unittest.mock import MagicMock

mock_service = MagicMock(spec=AIDecisionService)
mock_service.classify_results.return_value = DecisionResult(
    persist=[Event.asset("test", "domain", "real.com")],
    discard=[],
    trigger_downstream=["real.com"],
)

# Inject into orchestrator
orchestrator = EventDrivenOrchestrator(ai_service=mock_service)
```

## Extending with Real AI

To add LLM-based classification:

1. Subclass `AIDecisionService`
2. Override `classify_results()` to call your model
3. Keep the heuristic path as fallback
4. Respect the existing `RECON_AI_MAX_CALLS` budget

```python
class LLMDecisionService(AIDecisionService):
    def classify_results(self, output: NormalizedOutput) -> DecisionResult:
        # Try AI classification
        if self._budget_remaining > 0:
            return self._llm_classify(output)
        # Fall back to heuristics
        return super().classify_results(output)
```
