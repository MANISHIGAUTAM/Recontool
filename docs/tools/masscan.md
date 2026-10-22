# masscan

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `masscan` · NOT in extracted inventory.

**Purpose.** Internet-scale asynchronous port sweeper.

| Field | Value |
|-------|-------|
| Closes gap | Port scanning |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `ip, cidr` |
| Produces (canonical) | `host_port` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Fast wide sweep feeding nmap/fingerprintx; rate-limit aware.

## Invocation

```bash
masscan <cidr> -p1-65535 --rate 1000 -oJ out.json
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `ip, cidr`
- **Produces:** `host_port` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `masscan.host_port.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/masscan/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `ip` key.
