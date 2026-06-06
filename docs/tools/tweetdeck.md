# TweetDeck

> Provenance: extracted_from_spreadsheet · canonical slug `tweetdeck` · 1 source row(s).

**Purpose.** Real-time Twitter monitoring. Still useful for live event tracking.

| Field | Value |
|-------|-------|
| Category(s) | Twitter Monitoring |
| Classification | **passive** (source: Passive) |
| Integration | web |
| Cost | freemium (Freemium) |
| Scale | Massive |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Social media recon |
| Required input | `username / handle / org` |

## Invocation

Web/GUI/manual source — **no documented CLI/API** in the spreadsheet. Use via browser or a scripted headless browser; not part of the automated CLI chain by default.

## Inputs / outputs

- **Consumes:** `username / handle / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Web/GUI/manual only in source - no documented CLI/API; not directly automatable, flag for manual or scripted-browser handling.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 8 | Twitter Monitoring | Passive | Freemium | Web | Real-time Twitter monitoring | High | Still useful for live event tracking |
