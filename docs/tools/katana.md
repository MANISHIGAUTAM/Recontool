# katana

> Provenance: extracted_from_spreadsheet · canonical slug `katana` · 2 source row(s).

**Purpose.** Modern web crawling & JS parsing. Best modern crawler in recon.

| Field | Value |
|-------|-------|
| Category(s) | Web Crawling |
| Classification | **hybrid** (source: Active, Hybrid) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise, Very High |
| Pipeline position | URL/dork/index harvesting; Web tech fingerprinting & probing |
| Required input | `domain / live_host / url \| live_host / url` |

## Invocation

```bash
katana <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain / live_host / url \| live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Possibly related (not merged)

Katana Archive Mode, Katana screenshots

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 4 | Web Crawling | Hybrid | Free | CLI/API | Modern web crawling & JS parsing | Very High | Best modern crawler in recon |
| 5 | Web Crawling | Active | Free | CLI/API | Fast modern crawling | Very High | One of the best modern crawlers |
