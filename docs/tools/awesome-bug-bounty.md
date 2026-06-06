# Awesome Bug Bounty

> Provenance: extracted_from_spreadsheet · canonical slug `awesome-bug-bounty` · 1 source row(s).

**Purpose.** BB learning/resources. Great starter collection.

| Field | Value |
|-------|-------|
| Category(s) | Bug Bounty Index |
| Classification | **passive** (source: Passive) |
| Integration | web |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Reference index (tool discovery, not executed) |
| Required input | `n/a` |

## Invocation

Web/GUI/manual source — **no documented CLI/API** in the spreadsheet. Use via browser or a scripted headless browser; not part of the automated CLI chain by default.

## Inputs / outputs

- **Consumes:** `n/a` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Web/GUI/manual only in source - no documented CLI/API; not directly automatable, flag for manual or scripted-browser handling.
- Reference list/index/framework, not a single executable tool.

## Possibly related (not merged)

Awesome DFIR, Awesome Honeypots, Awesome Incident Response, Awesome Malware Analysis, Awesome OSINT For Everything, Awesome Pentest, Awesome Search Engines, Awesome Threat Intelligence, awesome-osint

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 18 | Bug Bounty Index | Passive | Free | GitHub | BB learning/resources | High | Great starter collection |
