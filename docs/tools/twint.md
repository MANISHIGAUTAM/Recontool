# Twint

> Provenance: extracted_from_spreadsheet · canonical slug `twint` · 2 source row(s).

**Purpose.** Twitter scraping without API. Breaks frequently due to X changes.

| Field | Value |
|-------|-------|
| Category(s) | Twitter/X OSINT |
| Classification | **passive** (source: Passive) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Email / username / identity recon; Social media recon |
| Required input | `domain / email / person / username \| username / handle / org` |

## Invocation

```bash
twint <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain / email / person / username \| username / handle / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Marked deprecated/aging/niche in source notes - keep but verify.
- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 7 | Twitter/X OSINT | Passive | Free | CLI/API | Twitter scraping without API | High | Breaks frequently due to X changes |
| 8 | Twitter/X OSINT | Passive | Free | CLI | Scraping tweets without API | High | Popular but partially broken after X changes |
