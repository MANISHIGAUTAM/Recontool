# fingerprintx

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `fingerprintx` · NOT in extracted inventory.

**Purpose.** Fingerprints non-HTTP services (databases, RDP, SSH, etc.).

| Field | Value |
|-------|-------|
| Closes gap | Service fingerprinting |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `host_port, service` |
| Produces (canonical) | `service, tech` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Port scan gives open ports; fingerprintx says WHAT they are for non-web services httpx can't fingerprint.

## Invocation

```bash
fingerprintx -l host_ports.txt --json
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `host_port, service`
- **Produces:** `service, tech` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `fingerprintx.service.jsonl`, `fingerprintx.tech.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/fingerprintx/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `host_port` key.
