# Have I Been Pwned

> Provenance: extracted_from_spreadsheet · canonical slug `have-i-been-pwned` · 1 source row(s).

**Purpose.** Breach verification. Trusted breach source.

| Field | Value |
|-------|-------|
| Category(s) | Breach Lookup |
| Classification | **passive** (source: Passive) |
| Integration | api |
| Cost | freemium (Freemium) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Email / username / identity recon |
| Required input | `domain / email / person / username` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> have-i-been-pwned)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain / email / person / username` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 7 | Breach Lookup | Passive | Freemium | API | Breach verification | Very High | Trusted breach source |
