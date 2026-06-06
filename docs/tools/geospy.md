# GeoSpy

> Provenance: extracted_from_spreadsheet · canonical slug `geospy` · 2 source row(s).

**Purpose.** AI-assisted image geolocation. Extremely powerful modern GEOINT tool.

| Field | Value |
|-------|-------|
| Category(s) | Image Geolocation AI, Image Geolocation |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | freemium (Paid/Freemium) |
| Scale | Large |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Physical / geo / wireless recon; Social media recon |
| Required input | `bssid / coords / org \| username / handle / org` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> geospy)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `bssid / coords / org \| username / handle / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 8 | Image Geolocation AI | Passive | Paid/Freemium | Web/API | AI-assisted image geolocation | Very High | Extremely powerful modern GEOINT tool |
| 15 | Image Geolocation | Passive | Paid/Freemium | API/Web | AI image geolocation | High | Emerging GEOINT platform |
