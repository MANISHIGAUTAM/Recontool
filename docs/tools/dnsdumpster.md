# DNSDumpster

> Provenance: extracted_from_spreadsheet · canonical slug `dnsdumpster` · 2 source row(s).

**Purpose.** Quick DNS visualization. Better for manual recon.

| Field | Value |
|-------|-------|
| Category(s) | DNS Recon |
| Classification | **passive** (source: Passive) |
| Integration | unspecified |
| Cost | freemium (Freemium) |
| Scale | Medium |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Common recon workflow preset; Subdomain discovery & DNS resolution |
| Required input | `domain (scope) \| domain / subdomain` |

## Invocation

Integration mode not specified in source — classify before wiring.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / subdomain` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 2 | DNS Recon | Passive | Freemium | Limited | Quick DNS visualization | Medium | Better for manual recon |
| 19 | DNS Recon | Passive | Freemium | Limited | Visual DNS mapping | Medium | Better for manual investigations |
