# Snap Map

> Provenance: extracted_from_spreadsheet · canonical slug `snap-map` · 1 source row(s).

**Purpose.** Finding public Snapchat activity. Useful for geo-social investigations.

| Field | Value |
|-------|-------|
| Category(s) | Geolocation OSINT |
| Classification | **passive** (source: Passive) |
| Integration | mobile, web |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Social media recon |
| Required input | `username / handle / org` |

## Invocation

Web/GUI/manual source — **no documented CLI/API** in the spreadsheet. Use via browser or a scripted headless browser; not part of the automated CLI chain by default.

## Inputs / outputs

- **Consumes:** `username / handle / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Web/GUI/manual only in source - no documented CLI/API; not directly automatable, flag for manual or scripted-browser handling.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 8 | Geolocation OSINT | Passive | Free | Mobile/Web | Finding public Snapchat activity | Medium | Useful for geo-social investigations |
