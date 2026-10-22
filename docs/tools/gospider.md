# gospider

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `gospider` · NOT in extracted inventory.

**Purpose.** Fast web spider (alternative to katana/hakrawler).

| Field | Value |
|-------|-------|
| Closes gap | Crawling |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `live_host, url` |
| Produces (canonical) | `url` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Alternative crawler; wire katana as primary, gospider as fallback.

## Invocation

```bash
gospider -s https://<host> -o out -c 10 -d 3
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `live_host, url`
- **Produces:** `url` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `gospider.url.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/gospider/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
