# BuiltWith

> Provenance: extracted_from_spreadsheet · canonical slug `builtwith` · 1 source row(s).

**Purpose.** Tech stack identification. Industry-leading commercial dataset.

| Field | Value |
|-------|-------|
| Category(s) | Web Technology Fingerprinting |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | freemium (Paid/Freemium) |
| Scale | Massive |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Enterprise |
| Pipeline position | Web tech fingerprinting & probing |
| Required input | `live_host / url` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> builtwith)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Possibly related (not merged)

BuiltWith API, BuiltWith Historical Lookup, BuiltWith Lookup, BuiltWith Trends

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 5 | Web Technology Fingerprinting | Passive | Paid/Freemium | API/Web | Tech stack identification | High | Industry-leading commercial dataset |
