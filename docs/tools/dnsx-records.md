# dnsx-records

DNS-record intelligence variant of [dnsx](dnsx.md) — Batch-12 F1 (opt-in `dns-records`
family, off by default). Where the default `dnsx` resolves A/AAAA/CNAME → ip, this captures
the records it does not: NS, MX, TXT, CAA.

## Purpose
Passive DNS enrichment: surface DNS infrastructure and posture.
- **NS** hostnames that are in scope → new `subdomain` (self-hosted nameservers); third-party
  NS (e.g. `ns1.cloudflare.com`) are scope-dropped.
- **MX / TXT / CAA** → `dns_record` evidence (mail provider, SaaS-verification TXT, CAA pinning)
  for the OSINT/forest layer + future SaaS/NS-takeover & mail-posture analyzers.

## Inputs / outputs
- **Input:** `subdomain` (stdin list).
- **Output:** `subdomain` (from NS) + `dns_record` (MX/TXT/CAA). Raw JSONL under
  `artifacts/<scan_id>/raw/dnsx-records/`; typed under `out/dnsx-records.<type>.jsonl`.

## Invocation
`dnsx -ns -mx -txt -caa -json -silent` (reads hosts from stdin). Binary: `dnsx`
(install: `go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest`).

## Pipeline position
Stage: subdomain → DNS enrichment. Passive. Off by default; enable via the `dns-records`
profile. `dns_record` is recursion-terminal evidence (recorded, fed to reports/OSINT, not
re-queued); discovered in-scope NS subdomains re-enter the subdomain pipeline.
