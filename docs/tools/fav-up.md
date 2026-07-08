# fav-up

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `fav-up` · NOT in extracted inventory.

**Purpose.** Maps favicon hashes to real IPs via Shodan (origin-IP discovery).

| Field | Value |
|-------|-------|
| Closes gap | Favicon pivot |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `live_host, url` |
| Produces (canonical) | `ip` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Helps de-cloak origin IPs behind a CDN via favicon hash search.

## Invocation

```bash
python3 favUp.py -w <host> -sc
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `live_host, url`
- **Produces:** `ip` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `fav-up.ip.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/fav-up/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
