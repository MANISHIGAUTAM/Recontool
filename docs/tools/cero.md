# cero

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `cero` · NOT in extracted inventory.

**Purpose.** Scrapes domain names from TLS certificates of an IP/CIDR range.

| Field | Value |
|-------|-------|
| Closes gap | Cert-to-host pivot |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `ip, cidr` |
| Produces (canonical) | `subdomain` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Turns network ranges back into hostnames — a real pivot CT logs miss (live cert SANs, not just logged issuance).

## Invocation

```bash
cero <cidr-or-ip>
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `ip, cidr`
- **Produces:** `subdomain` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `cero.subdomain.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/cero/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `ip` key.
