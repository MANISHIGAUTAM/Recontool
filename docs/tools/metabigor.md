# metabigor

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `metabigor` · NOT in extracted inventory.

**Purpose.** OSINT ASN/IP/org discovery WITHOUT API keys.

| Field | Value |
|-------|-------|
| Closes gap | ASN/IP/org OSINT |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `org, asn, ip` |
| Produces (canonical) | `cidr, ip, asn` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Free org -> netblock pivot; great unauthenticated ASN expansion.

## Invocation

```bash
echo '<org>' | metabigor net --org
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `org, asn, ip`
- **Produces:** `cidr, ip, asn` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `metabigor.cidr.jsonl`, `metabigor.ip.jsonl`, `metabigor.asn.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/metabigor/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `org` key.
