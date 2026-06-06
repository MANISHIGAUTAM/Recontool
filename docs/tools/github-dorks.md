# GitHub Dorks

> Provenance: extracted_from_spreadsheet · canonical slug `github-dorks` · 2 source row(s).

**Purpose.** Secret discovery in repos. Extremely effective OSINT technique.

| Field | Value |
|-------|-------|
| Category(s) | Code Recon, Secret Discovery |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High, Medium |
| Pipeline position | Common recon workflow preset; URL/dork/index harvesting |
| Required input | `domain (scope) \| domain / live_host / url` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> github-dorks)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / live_host / url` (per pipeline position).
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

GitHub

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 4 | Code Recon | Passive | Free | Web/API | Secret discovery in repos | Very High | Extremely effective OSINT technique |
| 19 | Secret Discovery | Passive | Free | Web/API | Searching exposed secrets/code | Very High | Core OSINT technique |
