# github-subdomains

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `github-subdomains` · NOT in extracted inventory.

**Purpose.** Harvests subdomains referenced in public GitHub code/issues.

| Field | Value |
|-------|-------|
| Closes gap | Subdomain enum (code) |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `domain` |
| Produces (canonical) | `subdomain` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Code platforms leak internal hostnames passive DNS never sees.

## Invocation

```bash
github-subdomains -d <domain> -t $GITHUB_TOKEN
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `domain`
- **Produces:** `subdomain` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `github-subdomains.subdomain.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/github-subdomains/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `domain` key.
