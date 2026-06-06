# Shodan

> Provenance: extracted_from_spreadsheet · canonical slug `shodan` · 2 source row(s).

**Purpose.** Exposed services, IoT, banners. Industry standard internet search engine.

| Field | Value |
|-------|-------|
| Category(s) | Internet Asset Search, Internet Exposure Search |
| Classification | **passive** (source: Passive) |
| Integration | api, cli |
| Cost | freemium (Freemium, Freemium/Paid) |
| Scale | Internet-scale |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise, Excellent |
| Pipeline position | Common recon workflow preset; Seed discovery (internet-wide search) |
| Required input | `domain (scope) \| domain / org / ip / asn` |

## Invocation

```bash
shodan <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / org / ip / asn` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Possibly related (not merged)

Shodan API, Shodan ASN Search, Shodan screenshots

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Internet Asset Search | Passive | Freemium | Excellent | Exposed services, IoT, banners | Very High | Industry standard internet search engine |
| 19 | Internet Exposure Search | Passive | Freemium/Paid | API/CLI | Discover exposed internet services | Very High | Recon industry standard |
