# Sonar RDNS

> Provenance: extracted_from_spreadsheet · canonical slug `sonar-rdns` · 1 source row(s).

**Purpose.** Reverse DNS analysis. Useful for internet-wide recon.

| Field | Value |
|-------|-------|
| Category(s) | DNS Dataset |
| Classification | **passive** (source: Passive) |
| Integration | dataset |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Subdomain discovery & DNS resolution |
| Required input | `domain / subdomain` |

## Invocation

Integration mode not specified in source — classify before wiring.

## Inputs / outputs

- **Consumes:** `domain / subdomain` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Possibly related (not merged)

Sonar DNS, Sonar FDNS, Sonar OMNI

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 2 | DNS Dataset | Passive | Free | Dataset | Reverse DNS analysis | High | Useful for internet-wide recon |
