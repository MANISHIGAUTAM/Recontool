# SearchDiggity

> Provenance: extracted_from_spreadsheet · canonical slug `searchdiggity` · 1 source row(s).

**Purpose.** Advanced search engine recon. Trusted by pentesters.

| Field | Value |
|-------|-------|
| Category(s) | Dorking Toolkit |
| Classification | **passive** (source: Passive) |
| Integration | gui |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | URL/dork/index harvesting |
| Required input | `domain / live_host / url` |

## Invocation

Web/GUI/manual source — **no documented CLI/API** in the spreadsheet. Use via browser or a scripted headless browser; not part of the automated CLI chain by default.

## Inputs / outputs

- **Consumes:** `domain / live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Web/GUI/manual only in source - no documented CLI/API; not directly automatable, flag for manual or scripted-browser handling.
- Reference list/index/framework, not a single executable tool.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 4 | Dorking Toolkit | Passive | Free | GUI | Advanced search engine recon | High | Trusted by pentesters |
