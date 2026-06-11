# gf

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `gf` · NOT in extracted inventory.

**Purpose.** Tomnomnom grep wrapper with curated patterns (ssrf, xss, redirect, idor) to surface interesting URLs from a large set.

| Field | Value |
|-------|-------|
| Closes gap | Glue / pattern grep |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `url` |
| Produces (canonical) | `url` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Turns raw URL dumps into prioritized, classified leads.

## Invocation

```bash
cat urls.txt | gf ssrf
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `url`
- **Produces:** `url` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `gf.url.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/gf/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `url` key.
