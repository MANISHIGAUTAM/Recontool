# qsreplace

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `qsreplace` · NOT in extracted inventory.

**Purpose.** Swaps query-string values across a URL set (fuzzing prep).

| Field | Value |
|-------|-------|
| Closes gap | Glue / fuzz prep |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `url` |
| Produces (canonical) | `url` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Normalizes parameterized URLs for dedupe and prepares fuzz targets.

## Invocation

```bash
cat urls.txt | qsreplace FUZZ
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `url`
- **Produces:** `url` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `qsreplace.url.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/qsreplace/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `url` key.
