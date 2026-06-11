# alterx

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `alterx` · NOT in extracted inventory.

**Purpose.** Pattern-based subdomain permutation engine (modern AltDNS) to generate candidate names for resolution.

| Field | Value |
|-------|-------|
| Closes gap | Subdomain permutation |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `subdomain` |
| Produces (canonical) | `subdomain` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Replaces AltDNS/dnsgen for cleaner, template-driven permutations; feeds the resolver, gated by wildcard filtering.

## Invocation

```bash
alterx -l subs.txt -enrich | dnsx -silent
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `subdomain`
- **Produces:** `subdomain` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `alterx.subdomain.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/alterx/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `subdomain` key.
