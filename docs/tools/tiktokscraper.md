# TikTokScraper

> Provenance: extracted_from_spreadsheet · canonical slug `tiktokscraper` · 1 source row(s).

**Purpose.** TikTok profile/video scraping. Useful for influencer/social investigations.

| Field | Value |
|-------|-------|
| Category(s) | TikTok OSINT |
| Classification | **passive** (source: Passive) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Medium |
| Pipeline position | Social media recon |
| Required input | `username / handle / org` |

## Invocation

```bash
tiktokscraper <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `username / handle / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 8 | TikTok OSINT | Passive | Free | CLI/API | TikTok profile/video scraping | High | Useful for influencer/social investigations |
