# SSLyze

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `sslyze` · NOT in extracted inventory.

**Purpose.** Deep TLS configuration and vulnerability analyzer.

| Field | Value |
|-------|-------|
| Closes gap | TLS/SSL analysis |
| Classification | **active** |
| Integration | cli |
| Consumes (canonical) | `live_host, host_port` |
| Produces (canonical) | `finding, tech` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Config-level TLS findings (weak ciphers, cert issues) tlsx skips.

## Invocation

```bash
sslyze --json_out out.json <host>:443
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `live_host, host_port`
- **Produces:** `finding, tech` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `sslyze.finding.jsonl`, `sslyze.tech.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/sslyze/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `live_host` key.
