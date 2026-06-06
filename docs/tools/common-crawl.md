# Common Crawl

> Provenance: extracted_from_spreadsheet · canonical slug `common-crawl` · 2 source row(s).

**Purpose.** Large-scale web mining. Best for big-data recon.

| Field | Value |
|-------|-------|
| Category(s) | Internet Dataset, Web Dataset Archive |
| Classification | **passive** (source: Passive) |
| Integration | api, dataset |
| Cost | free (Free) |
| Scale | Internet-scale |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Historical & archive harvesting; URL/dork/index harvesting |
| Required input | `domain / live_host \| domain / live_host / url` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> common-crawl)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain / live_host \| domain / live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 4 | Internet Dataset | Passive | Free | Dataset/API | Large-scale web mining | High | Best for big-data recon |
| 6 | Web Dataset Archive | Passive | Free | Dataset/API | Large-scale internet research | High | Massive raw crawl dataset requiring processing |
