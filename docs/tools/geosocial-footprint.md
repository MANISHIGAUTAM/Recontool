# GeoSocial Footprint

> Provenance: extracted_from_spreadsheet · canonical slug `geosocial-footprint` · 2 source row(s).

**Purpose.** Location-based social footprinting. Generic category/toolset.

| Field | Value |
|-------|-------|
| Category(s) | Geo OSINT, GEOINT |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | free (Free, Mixed) |
| Scale | Large |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Physical / geo / wireless recon; Social media recon |
| Required input | `bssid / coords / org \| username / handle / org` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> geosocial-footprint)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `bssid / coords / org \| username / handle / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 8 | Geo OSINT | Passive | Free | Web | Location-based social footprinting | Medium | Generic category/toolset |
| 15 | GEOINT | Passive | Mixed | Web/API | Social geo profiling | Medium | Category/toolset concept |
