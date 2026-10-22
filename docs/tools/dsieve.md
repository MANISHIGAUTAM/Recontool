# dsieve

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `dsieve` · NOT in extracted inventory.

**Purpose.** Filter/sort subdomains by level and extract the most relevant.

| Field | Value |
|-------|-------|
| Closes gap | Glue / domain filter |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `subdomain` |
| Produces (canonical) | `subdomain` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Keeps the frontier focused on meaningful host levels.

## Invocation

```bash
cat subs.txt | dsieve -f 3
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `subdomain`
- **Produces:** `subdomain` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `dsieve.subdomain.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/dsieve/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `subdomain` key.
