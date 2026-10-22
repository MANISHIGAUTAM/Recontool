# dnsgen

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `dnsgen` · NOT in extracted inventory.

**Purpose.** Generates permutations/word-mutations of known subdomains.

| Field | Value |
|-------|-------|
| Closes gap | Subdomain permutation |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `subdomain` |
| Produces (canonical) | `subdomain` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Overlaps alterx/gotator — wire ONE permutation engine, not all three, to avoid redundant candidate explosion.

## Invocation

```bash
dnsgen subs.txt | massdns -r resolvers.txt
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `subdomain`
- **Produces:** `subdomain` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `dnsgen.subdomain.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/dnsgen/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `subdomain` key.
