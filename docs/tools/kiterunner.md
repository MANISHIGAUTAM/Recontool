# kiterunner

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `kiterunner` · NOT in extracted inventory.

**Purpose.** API route discovery using Assetnote route-based wordlists.

| Field | Value |
|-------|-------|
| Closes gap | API & GraphQL recon |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `live_host, url` |
| Produces (canonical) | `endpoint` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Modern apps are API-first; directory brute force misses API routes.

## Invocation

```bash
kr scan https://<host> -w routes.kite
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `live_host, url`
- **Produces:** `endpoint` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `kiterunner.endpoint.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/kiterunner/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
