# cdncheck

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `cdncheck` · NOT in extracted inventory.

**Purpose.** Flags whether a host/IP is behind a CDN/WAF/cloud so the engine does not waste active scans on shared edge infrastructure.

| Field | Value |
|-------|-------|
| Closes gap | Noise control / CDN exclusion |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `ip, domain` |
| Produces (canonical) | `tag` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Without CDN exclusion, recursion port-scans Cloudflare edge ranges and treats shared IPs as pivots — a major false-lead amplifier.

## Invocation

```bash
cdncheck -i <ip> -resp -json
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `ip, domain`
- **Produces:** `tag` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `cdncheck.tag.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/cdncheck/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `ip` key.
