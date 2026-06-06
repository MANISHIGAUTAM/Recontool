# PTRArchive

> Provenance: extracted_from_spreadsheet · canonical slug `ptrarchive` · 1 source row(s).

**Purpose.** PTR lookups. Specialized use only.

| Field | Value |
|-------|-------|
| Category(s) | Reverse DNS |
| Classification | **passive** (source: Passive) |
| Integration | web |
| Cost | free (Free) |
| Scale | Medium |
| Reliability / worth | Niche (score 0.4) |
| Data quality (source) | Medium |
| Pipeline position | Subdomain discovery & DNS resolution |
| Required input | `domain / subdomain` |

## Invocation

Web/GUI/manual source — **no documented CLI/API** in the spreadsheet. Use via browser or a scripted headless browser; not part of the automated CLI chain by default.

## Inputs / outputs

- **Consumes:** `domain / subdomain` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Niche` (score 0.4). Lower-tier source — corroborate with another tool before trusting.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Web/GUI/manual only in source - no documented CLI/API; not directly automatable, flag for manual or scripted-browser handling.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 2 | Reverse DNS | Passive | Free | Web | PTR lookups | Niche | Specialized use only |
