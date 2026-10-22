# dalfox

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `dalfox` · NOT in extracted inventory.

**Purpose.** Fast XSS scanner/parameter analyzer.

| Field | Value |
|-------|-------|
| Closes gap | Active vuln detection |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `url, param` |
| Produces (canonical) | `finding` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Turns discovered params into validated findings; pairs with nuclei.

## Invocation

```bash
dalfox file urls.txt --format json
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `url, param`
- **Produces:** `finding` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `dalfox.finding.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/dalfox/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `url` key.
