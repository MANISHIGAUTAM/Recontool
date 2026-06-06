# Wigle

> Provenance: extracted_from_spreadsheet · canonical slug `wigle` · 2 source row(s).

**Purpose.** WiFi/BSSID geolocation. Best wireless OSINT database.

| Field | Value |
|-------|-------|
| Category(s) | Wireless Mapping, Wireless Recon |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | freemium (Free/Freemium, Freemium) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Excellent, Very High |
| Pipeline position | Physical / geo / wireless recon; Seed discovery (internet-wide search) |
| Required input | `bssid / coords / org \| domain / org / ip / asn` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> wigle)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `bssid / coords / org \| domain / org / ip / asn` (per pipeline position).
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

WiGLE WiFi Search

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Wireless Mapping | Passive | Freemium | API | WiFi/BSSID geolocation | Very High | Best wireless OSINT database |
| 15 | Wireless Recon | Passive | Free/Freemium | API/Web | WiFi/BSSID geolocation | Very High | Best public WiFi mapping DB |
