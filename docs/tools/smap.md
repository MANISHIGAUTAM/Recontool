# smap

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `smap` · NOT in extracted inventory.

**Purpose.** Returns ports/services from Shodan's free InternetDB data — port intel WITHOUT sending packets.

| Field | Value |
|-------|-------|
| Closes gap | Passive port scan |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `ip, domain` |
| Produces (canonical) | `service` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Cheap passive 'nmap' for the passive phase; defer real naabu/nmap to confirmed-live hosts only.

## Invocation

```bash
smap -iL hosts.txt
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `ip, domain`
- **Produces:** `service` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `smap.service.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/smap/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `ip` key.
