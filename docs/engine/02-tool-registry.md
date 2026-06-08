# Tool Registry

## Overview

The `ToolRegistry` is the single source of truth for tool metadata. It loads
tool specifications from `config/tools.yaml` (detailed) and
`config/tools_generic.yaml` (declarative) into validated `ToolSpec` models.

## ToolSpec Schema

```python
class ToolSpec(BaseModel):
    name: str                          # Unique identifier
    category: int = 0                  # Category number (1-19)
    purpose: str = ""                  # Human-readable description
    phase: str = ""                    # Pipeline phase (p1_seed, p2_expand, etc.)
    type: str = "passive"              # passive | active
    binary: str = ""                   # Executable name on PATH
    invocation: str = ""               # Command template
    supported_input_types: list[str]   # What this tool accepts
    output_types: list[str]            # What this tool produces
    consumes: list[str]                # Event-driven: input key types
    produces: list[str]                # Event-driven: output key types
    timeout: int = 300                 # Max execution seconds
    retry_policy: RetryPolicy          # Retry configuration
    parallel_safe: bool = True         # Can run concurrently
    concurrency_safety: bool = True    # Thread-safe output
    enabled: bool = True               # Active in registry
```

## Loading the Registry

```python
from recontool.engine.registry import ToolRegistry

# Load from default config directory
registry = ToolRegistry.load()

# Or build programmatically for testing
registry = ToolRegistry(tools={"mytool": ToolSpec(name="mytool", ...)})
```

## Querying Tools

```python
# By name
spec = registry.get("subfinder")

# By category
cat2_tools = registry.by_category(2)

# By input type
domain_tools = registry.by_input_type("domain")

# By output type
subdomain_producers = registry.by_output_type("subdomain")

# All tools
all_tools = registry.all_tools()
```

## Adding a New Tool

### Option 1: YAML (declarative, no code)

Add to `config/tools_generic.yaml`:

```yaml
- name: certspotter
  phase: p1_seed
  category: 2
  integration: api
  consumes: [domain]
  produces: [subdomain]
  endpoint: "https://api.certspotter.com/v1/issuances?domain={domain}"
  enabled: true
```

### Option 2: tools.yaml (detailed)

Add to `config/tools.yaml` under the `tools:` key:

```yaml
tools:
  subfinder:
    category: 2
    phase: p2_expand
    type: passive
    binary: subfinder
    invocation: "subfinder -d {domain} -all -silent -oJ"
    input: domain
    output: subdomain
```

### Option 3: Programmatic (testing)

```python
spec = ToolSpec(
    name="custom_scanner",
    consumes=["live_host"],
    produces=["finding"],
    enabled=True,
)
registry = ToolRegistry(tools={"custom_scanner": spec})
```
