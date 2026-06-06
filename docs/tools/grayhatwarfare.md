# GrayHatWarfare

> Provenance: extracted_from_spreadsheet · canonical slug `grayhatwarfare` · 2 source row(s).

**Purpose.** Finding exposed S3/GCS buckets. Excellent search engine for public cloud storage.

| Field | Value |
|-------|-------|
| Category(s) | Public Bucket Search, Cloud Bucket Search |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | freemium (Freemium, Freemium/Paid) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Cloud & storage recon; Common recon workflow preset |
| Required input | `domain (scope) \| org / domain / keyword` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> grayhatwarfare)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| org / domain / keyword` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 10 | Public Bucket Search | Passive | Freemium | Web/API | Finding exposed S3/GCS buckets | Very High | Excellent search engine for public cloud storage |
| 19 | Cloud Bucket Search | Passive | Freemium/Paid | API/Web | Public cloud bucket discovery | Very High | Extremely valuable cloud recon source |
