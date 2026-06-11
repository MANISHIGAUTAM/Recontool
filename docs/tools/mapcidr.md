# mapcidr

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `mapcidr` · NOT in extracted inventory.

**Purpose.** Expand/aggregate CIDR ranges; pairs with asnmap to turn an ASN into scannable IPs.

| Field | Value |
|-------|-------|
| Closes gap | CIDR utility |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `cidr, ip` |
| Produces (canonical) | `ip, cidr` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

The asn -> cidr -> ip expansion glue; without it ASN pivots dead-end.

## Invocation

```bash
echo <cidr> | mapcidr -silent
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `cidr, ip`
- **Produces:** `ip, cidr` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `mapcidr.ip.jsonl`, `mapcidr.cidr.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/mapcidr/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `cidr` key.
