# tlsx

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `tlsx` · NOT in extracted inventory.

**Purpose.** TLS grabber: SANs, JARM, cipher, cert details from live endpoints.

| Field | Value |
|-------|-------|
| Closes gap | TLS/SSL analysis |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `live_host, ip` |
| Produces (canonical) | `subdomain, cert, tech` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Live cert SANs are a subdomain SOURCE and a fingerprint input — a pivot CT-log search alone misses. MULTI-MODE: -san -> subdomain, -jarm -> tech.

## Invocation

```bash
tlsx -l hosts.txt -san -cn -json
```
> Confirm exact flags against the installed version before wiring.

**Multi-mode tool.** Each mode produces a different entity type and writes a separate typed output file:
- `san->subdomain`
- `jarm/cipher->tech`

## Inputs / outputs

- **Consumes:** `live_host, ip`
- **Produces:** `subdomain, cert, tech` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `tlsx.subdomain.jsonl`, `tlsx.cert.jsonl`, `tlsx.tech.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/tlsx/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
