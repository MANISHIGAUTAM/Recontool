# WhoisXML API

> Provenance: extracted_from_spreadsheet · canonical slug `whoisxml-api` · 2 source row(s).

**Purpose.** WHOIS + passive DNS automation. Enterprise-grade APIs.

| Field | Value |
|-------|-------|
| Category(s) | WHOIS / DNS |
| Classification | **passive** (source: Passive) |
| Integration | api |
| Cost | paid (Paid) |
| Scale | Massive |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Enterprise |
| Pipeline position | APIs & intelligence feeds (enrichment); Subdomain discovery & DNS resolution |
| Required input | `domain / ip / email \| domain / subdomain` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> whoisxml-api)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain / ip / email \| domain / subdomain` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 2 | WHOIS / DNS | Passive | Paid | API | WHOIS + passive DNS automation | High | Enterprise-grade APIs |
| 17 | WHOIS / DNS | Passive | Paid | API | WHOIS & DNS automation | High | Excellent enrichment |
