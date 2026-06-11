# mantra

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `mantra` · NOT in extracted inventory.

**Purpose.** Hunts API keys/secrets in JS files and pages.

| Field | Value |
|-------|-------|
| Closes gap | JavaScript analysis |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `js_file, url` |
| Produces (canonical) | `secret` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Secret-focused JS miner; overlaps jsluice secrets — keep one primary.

## Invocation

```bash
cat urls.txt | mantra
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `js_file, url`
- **Produces:** `secret` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `mantra.secret.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/mantra/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `js_file` key.
