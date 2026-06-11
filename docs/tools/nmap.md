# Nmap

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `nmap` · NOT in extracted inventory.

**Purpose.** The reference port scanner + NSE service/version detection.

| Field | Value |
|-------|-------|
| Closes gap | Port scanning & service detection |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `ip, live_host` |
| Produces (canonical) | `service` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Run on confirmed-live hosts only; naabu for fast sweep, nmap for depth/NSE on interesting ports.

## Invocation

```bash
nmap -sV -Pn -oX out.xml <ip>
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `ip, live_host`
- **Produces:** `service` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `nmap.service.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/nmap/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `ip` key.
