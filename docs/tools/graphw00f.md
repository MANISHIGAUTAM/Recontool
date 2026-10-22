# graphw00f

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `graphw00f` · NOT in extracted inventory.

**Purpose.** Fingerprints GraphQL engines and detects introspection exposure.

| Field | Value |
|-------|-------|
| Closes gap | API & GraphQL recon |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `live_host, url` |
| Produces (canonical) | `tech` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Identifies GraphQL surface for follow-up introspection.

## Invocation

```bash
graphw00f -d -t https://<host>/graphql
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `live_host, url`
- **Produces:** `tech` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `graphw00f.tech.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/graphw00f/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
