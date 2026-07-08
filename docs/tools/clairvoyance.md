# clairvoyance

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `clairvoyance` · NOT in extracted inventory.

**Purpose.** Recovers a GraphQL schema when introspection is disabled.

| Field | Value |
|-------|-------|
| Closes gap | API & GraphQL recon |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `url` |
| Produces (canonical) | `endpoint` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Extracts the hidden API surface that feeds further testing.

## Invocation

```bash
clairvoyance https://<host>/graphql -o schema.json
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `url`
- **Produces:** `endpoint` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `clairvoyance.endpoint.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/clairvoyance/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `url` key.
