# unfurl

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `unfurl` · NOT in extracted inventory.

**Purpose.** Extracts/format parts of URLs (domains, paths, params, keys) at scale.

| Field | Value |
|-------|-------|
| Closes gap | Glue / URL parsing |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `url` |
| Produces (canonical) | `domain, endpoint` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Decomposes URLs into typed keys — the bridge from url back to subdomain/endpoint/param entities.

## Invocation

```bash
cat urls.txt | unfurl -u domains
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `url`
- **Produces:** `domain, endpoint` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `unfurl.domain.jsonl`, `unfurl.endpoint.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/unfurl/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `url` key.
