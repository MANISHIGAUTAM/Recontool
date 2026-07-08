# shosubgo

> Provenance: wired in `config/tools_generic.d/subdomain-cli-2.yaml` · canonical slug `shosubgo`.

**Purpose.** Passive subdomain enumeration via the Shodan API. Given a domain and a Shodan API key, it queries Shodan and prints discovered subdomains.

| Field | Value |
|-------|-------|
| Category(s) | Passive DNS & Subdomain Enumeration (Cat 2) |
| Classification | **passive** (Shodan-API-backed source) |
| Integration | cli |
| Cost | free tool; needs a Shodan API key (`SHODAN_API_KEY`) |
| Pipeline position | Subdomain discovery / horizontal expansion |
| Required input | `domain` |
| Default state | OFF (`default_on: false`, `is_active: false`) |

## Invocation

Verified against the official source: <https://github.com/incogbyte/shosubgo>

```bash
shosubgo -d example.com -s $SHODAN_API_KEY
```

- `-d` — target domain.
- `-s` — Shodan API key.
- `-fail` — (optional) exit immediately on any error.

## Inputs / outputs

- **Consumes:** `domain`.
- **Produces:** `subdomain` (scope-filtered to the seed domain).
- **Output format (raw):** plain text, one FQDN per line. Verified from
  the program source (`fmt.Println(fullDomain)` over `subdomain.SubDomains`):
  <https://raw.githubusercontent.com/incogbyte/shosubgo/master/main.go>.
  A `-json` flag exists for JSON-array output, but the contract parses the
  default per-line text output.

## Operational behavior

- **Requires key:** declares `requires_key: SHODAN_API_KEY`. Without a key it cannot query Shodan.
- **If the binary is missing:** adapter reports unavailable (graceful skip).
- **If it returns nothing:** treat as empty (valid); do not block the chain.
- **Scope safety:** emitted subdomains are filtered to the seed domain's scope (`scope_filter: subdomain`); out-of-scope hosts are dropped (see `docs/D6-opsec.md`).

## Caveats

- Coverage is bounded by Shodan's dataset for the domain; complement with other passive sources (assetfinder, findomain, certspotter) for breadth.
