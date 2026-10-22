# ffuf

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `ffuf` · NOT in extracted inventory.

**Purpose.** Fast web fuzzer for directories, files, vhosts, and parameters.

| Field | Value |
|-------|-------|
| Closes gap | Content & directory discovery |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `live_host, url` |
| Produces (canonical) | `url` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Core active recon gap. MULTI-MODE: dir mode -> url file, vhost mode -> subdomain file, param mode -> param file (typed outputs).

## Invocation

```bash
ffuf -u https://<host>/FUZZ -w wordlist.txt -mc 200,301,403
```
> Confirm exact flags against the installed version before wiring.

**Multi-mode tool.** Each mode produces a different entity type and writes a separate typed output file:
- `dir->url`
- `vhost->subdomain`
- `param->param`

## Inputs / outputs

- **Consumes:** `live_host, url`
- **Produces:** `url` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `ffuf.url.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/ffuf/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
