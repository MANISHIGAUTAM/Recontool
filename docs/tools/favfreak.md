# FavFreak

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `favfreak` · NOT in extracted inventory.

**Purpose.** Hashes favicons (mmh3) to fingerprint tech and find related hosts via Shodan/ZoomEye.

| Field | Value |
|-------|-------|
| Closes gap | Favicon pivot |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `live_host, url` |
| Produces (canonical) | `tag` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Underused correlation: a favicon hash pivots to an org's other assets across the internet — a real recursion multiplier.

## Invocation

```bash
cat hosts.txt | favfreak
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `live_host, url`
- **Produces:** `tag` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `favfreak.tag.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/favfreak/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
