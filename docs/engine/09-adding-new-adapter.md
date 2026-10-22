# Adding a New Adapter

> **The registry already knows about every canonical tool.** All 531 unique tools
> from `data/tool_inventory.json` are loaded as `ToolSpec`s (see
> `docs/engine/02-tool-registry.md`). "Adding an adapter" almost always means
> **promoting an existing inventory-derived stub** to a full, executable contract —
> not registering a brand-new name. Check first:
>
> ```python
> reg = ToolRegistry.load()
> reg.by_slug("my-tool")      # already present as a stub?
> reg.get("my-tool").non_executable, reg.get("my-tool").validation_status
> ```
>
> Inventory-derived tools are routed through the same generic adapter machinery as
> curated tools via `recontool/engine/execution.py` (`plan_execution` /
> `build_adapter_for`). A CLI stub runs with a synthesised `"{binary} {value}"`
> invocation once its binary is installed; an API stub is *blocked with a reason*
> until you give it an endpoint. Promoting a stub = adding the curated entry below;
> its slug overrides the stub automatically.

## Step-by-Step Guide

This guide walks through adding a new tool adapter to the event-driven engine.

### Step 1: Choose Your Integration Type

| Type | When to Use | Example |
|------|-------------|---------|
| **Declarative YAML** | Simple API/CLI tools | certspotter, shodan |
| **Full adapter class** | Complex parsing, multi-step | crtsh, pycrawl |

### Step 2a: Declarative (No Code)

Add to `config/tools_generic.yaml`:

```yaml
- name: certspotter
  phase: p1_seed
  category: 2
  integration: api
  consumes: [domain]
  produces: [subdomain]
  requires_key: CERTSPOTTER_API_KEY
  key_optional: true
  endpoint: "https://api.certspotter.com/v1/issuances?domain={domain}&include_subdomains=true&expand=dns_names"
  timeout: 30
  parse:
    format: json
    emit:
      - entity: asset
        value_each: dns_names
        type: subdomain
        scope_filter: subdomain
  enabled: true
```

That is it. The generic adapter engine handles execution, parsing, and event emission.

### Step 2b: Full Adapter Class

Create `recontool/adapters/my_tool.py`:

```python
from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register

@register("p2_expand")
class MyTool(Adapter):
    name = "mytool"
    category = "CAT-3"
    is_active = False
    consumes = ("subdomain",)
    produces = ("ip",)

    def install_check(self) -> bool:
        import shutil
        return shutil.which("mytool") is not None

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        errors = []
        if not inputs.get("subdomain"):
            errors.append("At least one subdomain required")
        return errors

    def build_command(self, ctx: AdapterContext) -> str | None:
        domains = ctx.seeds_of("subdomain")
        return f"mytool resolve {' '.join(domains)}"

    def parse_stdout(self, stdout: str) -> dict[str, Any]:
        ips = [line.strip() for line in stdout.splitlines() if line.strip()]
        return {"ips": ips}

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events = []
        # ... execution logic ...
        for ip in resolved_ips:
            events.append(Event.asset(self.name, "ip", ip))
        return events
```

### Step 3: Register in Tool Registry

For YAML tools, registration is automatic on load.

For class-based adapters, the `@register` decorator handles it.

### Step 4: Add Test Fixtures

Create `tests/fixtures/mytool_output.json`:

```json
{"ips": ["93.184.216.34", "93.184.216.35"]}
```

### Step 5: Write Tests

```python
def test_mytool_parse_stdout():
    adapter = MyTool()
    result = adapter.parse_stdout("93.184.216.34\n93.184.216.35\n")
    assert result == {"ips": ["93.184.216.34", "93.184.216.35"]}

def test_mytool_validate_inputs():
    adapter = MyTool()
    errors = adapter.validate_inputs({"subdomain": []})
    assert errors
    errors = adapter.validate_inputs({"subdomain": ["sub.example.com"]})
    assert not errors
```

### Step 6: Define Dependencies

If your tool requires specific pending keys to be resolved before execution,
document this in the ToolSpec:

```yaml
- name: mytool
  consumes: [live_host]      # Only runs after live_host confirmed
  produces: [open_port]      # Produces keys that unlock port-specific tools
```

### Step 7: Verify End-to-End

```bash
# Run the full test suite
pytest -q

# Check linting
ruff check recontool/ tests/

# Test your adapter specifically
pytest tests/atomic/test_mytool.py -v
```
