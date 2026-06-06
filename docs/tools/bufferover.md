# BufferOver

> Provenance: extracted_from_spreadsheet · canonical slug `bufferover` · 2 source row(s).

**Purpose.** Subdomain enumeration. Great free source.

| Field | Value |
|-------|-------|
| Category(s) | DNS Recon, Passive DNS |
| Classification | **passive** (source: Passive) |
| Integration | api |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Medium |
| Pipeline position | Common recon workflow preset; Subdomain discovery & DNS resolution |
| Required input | `domain (scope) \| domain / subdomain` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> bufferover)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / subdomain` (per pipeline position).
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
| 2 | DNS Recon | Passive | Free | API | Subdomain enumeration | High | Great free source |
| 19 | Passive DNS | Passive | Free | API | Additional subdomain enumeration | High | Strong free enrichment source |
