# Riddler.io

> Provenance: extracted_from_spreadsheet · canonical slug `riddler-io` · 1 source row(s).

**Purpose.** Infra correlation. Limited adoption now.

| Field | Value |
|-------|-------|
| Category(s) | Search Engine |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | freemium (Freemium) |
| Scale | Medium |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Subdomain discovery & DNS resolution |
| Required input | `domain / subdomain` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> riddler-io)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain / subdomain` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Marked deprecated/aging/niche in source notes - keep but verify.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 2 | Search Engine | Passive | Freemium | Web/API | Infra correlation | Medium | Limited adoption now |
