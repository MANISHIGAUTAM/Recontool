# Adapter Contract

## Overview

Adapters bridge external tools/APIs into the engine. Each adapter implements
a standard contract that the executor calls during tool execution.

## Contract Methods

| Method | Required | Purpose |
|--------|----------|---------|
| `install_check()` | Yes | Returns True if the tool is available |
| `prepare(ctx)` | No | Pre-execution setup (create dirs, acquire locks) |
| `validate_inputs(inputs)` | Yes | Validate inputs, return list of error strings |
| `build_command(ctx)` | No | Build CLI command string (None for API adapters) |
| `run(ctx)` | Yes | Execute the tool and return Events |
| `parse_stdout(stdout)` | No | Parse raw stdout into structured dict |

## Reference Implementation: CrtSh

```python
@register("p1_seed")
class CrtSh(Adapter):
    name = "crtsh"
    category = "CAT-2"
    is_active = False
    consumes = ("domain",)
    produces = ("subdomain", "cert")

    def install_check(self) -> bool:
        # API-based: always available
        return True

    def prepare(self, ctx: AdapterContext) -> None:
        # No preparation needed
        pass

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        errors = []
        domains = inputs.get("domain", [])
        if not domains:
            errors.append("At least one domain seed is required")
        return errors

    def build_command(self, ctx: AdapterContext) -> str | None:
        # API adapter, not CLI
        return None

    def parse_stdout(self, stdout: str) -> dict[str, Any]:
        rows = json.loads(stdout)
        subdomains = []
        for row in rows:
            for name in str(row.get("name_value", "")).splitlines():
                name = name.strip().lstrip("*.").lower()
                if name:
                    subdomains.append(name)
        return {"subdomains": subdomains}
```

## CLI vs API Adapters

**CLI adapters** (subfinder, nuclei, naabu):
- `install_check()` uses `shutil.which(binary)`
- `build_command()` returns the full command string
- `parse_stdout()` parses the tool's stdout

**API adapters** (crtsh, HackerTarget, SecurityTrails):
- `install_check()` returns True (or checks API key)
- `build_command()` returns None
- `run()` makes HTTP requests directly

## Error Handling

Adapters should:
1. Never raise exceptions from `run()` - return empty results on failure
2. Set `exit_code != 0` in the result on failure
3. Include error details in stderr or error fields
4. Mark whether the failure is retryable

## Testing Adapters

```python
# Unit test: validate_inputs
adapter = CrtSh()
errors = adapter.validate_inputs({"domain": []})
assert errors  # should report missing domain

# Integration test: mock HTTP, verify parse
with respx.mock:
    respx.get(...).respond(json=fixture_data)
    events = await adapter.run(ctx)
    assert len(events) > 0
```
