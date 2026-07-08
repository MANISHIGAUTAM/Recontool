# feroxbuster

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `feroxbuster` · NOT in extracted inventory.

**Purpose.** Recursive content discovery (Rust) with auto-recursion into found dirs.

| Field | Value |
|-------|-------|
| Closes gap | Content & directory discovery |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `live_host, url` |
| Produces (canonical) | `url` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Recursive-by-design dir brute force — pairs naturally with the engine's own recursion; pick ffuf OR feroxbuster as primary.

## Invocation

```bash
feroxbuster -u https://<host> -w wordlist.txt --json
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `live_host, url`
- **Produces:** `url` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `feroxbuster.url.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/feroxbuster/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
