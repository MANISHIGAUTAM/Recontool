# Maltego

> Provenance: extracted_from_spreadsheet · canonical slug `maltego` · 2 source row(s).

**Purpose.** Relationship mapping. OSINT industry standard.

| Field | Value |
|-------|-------|
| Category(s) | Link Analysis / OSINT |
| Classification | **hybrid** (source: Hybrid, Passive) |
| Integration | api, gui |
| Cost | freemium (Freemium/Paid) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise |
| Pipeline position | Email / username / identity recon; Frameworks & automation (orchestration) |
| Required input | `domain (scope) \| domain / email / person / username` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> maltego)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / email / person / username` (per pipeline position).
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
| 7 | Link Analysis / OSINT | Hybrid | Freemium/Paid | GUI/API | Relationship mapping | Very High | OSINT industry standard |
| 14 | Link Analysis / OSINT | Passive | Freemium/Paid | GUI/API | Relationship mapping & investigations | Very High | Industry standard visual OSINT tool |
