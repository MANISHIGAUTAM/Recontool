# Katana Archive Mode

> Provenance: extracted_from_spreadsheet · canonical slug `katana-archive-mode` · 1 source row(s).

**Purpose.** Combining crawling with historical URLs. Modern ProjectDiscovery crawler.

| Field | Value |
|-------|-------|
| Category(s) | Web Crawling / Archive Recon |
| Classification | **hybrid** (source: Hybrid) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Historical & archive harvesting |
| Required input | `domain / live_host` |

## Invocation

```bash
katana-archive-mode <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain / live_host` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Possibly related (not merged)

Katana screenshots, katana

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 6 | Web Crawling / Archive Recon | Hybrid | Free | CLI/API | Combining crawling with historical URLs | Very High | Modern ProjectDiscovery crawler |
