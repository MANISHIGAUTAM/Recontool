# Searchcode

> Provenance: extracted_from_spreadsheet · canonical slug `searchcode` · 3 source row(s).

**Purpose.** Code pattern searching. Less accurate than Sourcegraph.

| Field | Value |
|-------|-------|
| Category(s) | Source Code Search, Code Search Engine, Code Search |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | free (Free, Web/API) |
| Scale | Large |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Common recon workflow preset; Seed discovery (internet-wide search); Source-code & secret recon |
| Required input | `domain (scope) \| domain / org / ip / asn \| org / domain / keyword` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> searchcode)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / org / ip / asn \| org / domain / keyword` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 3 rows across 3 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Source Code Search | Passive | Web/API | Easy | Code pattern searching | Medium | Less accurate than Sourcegraph |
| 9 | Code Search Engine | Passive | Free | Web/API | Public code indexing | Medium | Less comprehensive than modern alternatives |
| 19 | Code Search | Passive | Free | Web/API | Source code intelligence | Medium | Smaller ecosystem coverage |
