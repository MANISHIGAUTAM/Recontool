# gotator

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `gotator` · NOT in extracted inventory.

**Purpose.** Permutation generator with depth/number controls.

| Field | Value |
|-------|-------|
| Closes gap | Subdomain permutation |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `subdomain` |
| Produces (canonical) | `subdomain` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Same role as alterx/dnsgen — keep as an alternative, not a parallel.

## Invocation

```bash
gotator -sub subs.txt -perm words.txt -depth 1
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `subdomain`
- **Produces:** `subdomain` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `gotator.subdomain.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/gotator/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `subdomain` key.
