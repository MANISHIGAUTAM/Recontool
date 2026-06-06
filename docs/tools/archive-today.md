# Archive.today

> Provenance: extracted_from_spreadsheet · canonical slug `archive-today` · 1 source row(s).

**Purpose.** Preserved pages bypassing robots.txt. Useful when Wayback misses pages.

| Field | Value |
|-------|-------|
| Category(s) | Web Archive |
| Classification | **passive** (source: Passive) |
| Integration | unspecified |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Medium |
| Pipeline position | Historical & archive harvesting |
| Required input | `domain / live_host` |

## Invocation

Integration mode not specified in source — classify before wiring.

## Inputs / outputs

- **Consumes:** `domain / live_host` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 6 | Web Archive | Passive | Free | Limited | Preserved pages bypassing robots.txt | High | Useful when Wayback misses pages |
