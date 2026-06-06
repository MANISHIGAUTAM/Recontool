# GreyNoise

> Provenance: extracted_from_spreadsheet · canonical slug `greynoise` · 2 source row(s).

**Purpose.** Internet noise filtering. Essential SOC enrichment source.

| Field | Value |
|-------|-------|
| Category(s) | Threat Intelligence, Threat Intel |
| Classification | **passive** (source: Passive) |
| Integration | api |
| Cost | freemium (Freemium, Paid/Freemium) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise, Excellent |
| Pipeline position | Common recon workflow preset; Seed discovery (internet-wide search) |
| Required input | `domain (scope) \| domain / org / ip / asn` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> greynoise)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / org / ip / asn` (per pipeline position).
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

GreyNoise API, GreyNoise IP Lookup

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Threat Intelligence | Passive | Freemium | Excellent | Internet noise filtering | Very High | Essential SOC enrichment source |
| 19 | Threat Intel | Passive | Paid/Freemium | API | Noise filtering & scanner attribution | Very High | Excellent for prioritization |
