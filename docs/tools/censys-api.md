# Censys API

> Provenance: extracted_from_spreadsheet · canonical slug `censys-api` · 1 source row(s).

**Purpose.** TLS/cert/service enumeration. Stronger academic-quality data.

| Field | Value |
|-------|-------|
| Category(s) | Internet Intelligence |
| Classification | **passive** (source: Passive) |
| Integration | api |
| Cost | freemium (Paid/Freemium) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise |
| Pipeline position | APIs & intelligence feeds (enrichment) |
| Required input | `domain / ip / email` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> censys-api)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain / ip / email` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Possibly related (not merged)

Censys, Censys ASM, Censys ASN Search, Censys screenshots

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 17 | Internet Intelligence | Passive | Paid/Freemium | API | TLS/cert/service enumeration | Very High | Stronger academic-quality data |
