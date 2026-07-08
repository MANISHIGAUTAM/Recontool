# anew

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `anew` · NOT in extracted inventory.

**Purpose.** Append-only dedupe: adds only lines not already present in a file and prints them — the incremental delta primitive.

| Field | Value |
|-------|-------|
| Closes gap | Glue / dedupe |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `any` |
| Produces (canonical) | `any` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

The single most important plumbing tool: gives you 'only the NEW keys this round' for free, which IS the recursion delta.

## Invocation

```bash
cat new.txt | anew all_subs.txt
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `any`
- **Produces:** `any` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `raw/anew/`
- **Raw output:** `artifacts/<scan_id>/raw/anew/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `any` key.
