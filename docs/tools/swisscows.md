# Swisscows

> Provenance: extracted_from_spreadsheet · canonical slug `swisscows` · 1 source row(s).

**Purpose.** Privacy-focused indexing. Minimal recon value.

| Field | Value |
|-------|-------|
| Category(s) | Privacy Search |
| Classification | **passive** (source: Passive) |
| Integration | web |
| Cost | free (Free) |
| Scale | Medium |
| Reliability / worth | Low (score 0.3) |
| Data quality (source) | Medium |
| Pipeline position | Seed discovery (internet-wide search) |
| Required input | `domain / org / ip / asn` |

## Invocation

Web/GUI/manual source — **no documented CLI/API** in the spreadsheet. Use via browser or a scripted headless browser; not part of the automated CLI chain by default.

## Inputs / outputs

- **Consumes:** `domain / org / ip / asn` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Low` (score 0.3). Lower-tier source — corroborate with another tool before trusting.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Web/GUI/manual only in source - no documented CLI/API; not directly automatable, flag for manual or scripted-browser handling.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Privacy Search | Passive | Free | Web | Privacy-focused indexing | Low | Minimal recon value |
