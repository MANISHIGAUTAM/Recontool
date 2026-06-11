# anubis-jldc

> Provenance: **suggested_addition** (keyless passive-DNS source) · slug `anubis-jldc` · NOT in extracted inventory.

**Purpose.** Keyless subdomain lookup via the JonLuca Anubis DB mirror (`jldc.me`); returns a JSON array of known subdomains for a domain. A free corroborating source alongside crt.sh / certspotter / hackertarget.

| Field | Value |
|-------|-------|
| Closes gap | extra keyless passive-DNS coverage |
| Classification | **passive** |
| Integration | api (keyless) |
| Consumes (canonical) | `domain` |
| Produces (canonical) | `subdomain` |
| Status | **wired** — `config/tools_generic.yaml` (`anubis-jldc`) |

## Why it's needed

More independent passive sources raise confidence on each discovered subdomain
(noisy-OR corroboration) at zero cost — no API key required.

## Invocation

```bash
curl -s "https://jldc.me/anubis/subdomains/example.com"
# -> ["api.example.com", "vpn.example.com", ...]
```

## Inputs / outputs

- **Consumes:** `domain`
- **Produces:** `subdomain` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md). Scope-filtered to the seed domain.
- **Typed output files:** `anubis-jldc.subdomain.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/anubis-jldc/`.

## Integration checklist

Wired and covered by a parser fixture test (`tests/atomic/test_new_generic_specs.py`):
keyless API, JSON-array parse, `scope_filter: subdomain`, selectable by the scheduler
on an available `domain` key.
