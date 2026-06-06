# FOFA

> Provenance: extracted_from_spreadsheet · canonical slug `fofa` · 2 source row(s).

**Purpose.** Chinese and APAC assets. Great ASN and body search.

| Field | Value |
|-------|-------|
| Category(s) | Cyberspace Search, Internet Exposure Search |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | freemium (Freemium, Freemium/Paid) |
| Scale | Massive |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Common recon workflow preset; Seed discovery (internet-wide search) |
| Required input | `domain (scope) \| domain / org / ip / asn` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> fofa)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / org / ip / asn` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Possibly related (not merged)

FOFA API, FOFA Hunt, FOFA IP Search

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Cyberspace Search | Passive | Freemium | Good | Chinese and APAC assets | High | Great ASN and body search |
| 19 | Internet Exposure Search | Passive | Freemium/Paid | API/Web | Chinese/global asset exposure | High | Huge Asian internet visibility |
