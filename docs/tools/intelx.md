# IntelX

> Provenance: extracted_from_spreadsheet · canonical slug `intelx` · 2 source row(s).

**Purpose.** Leaks, archives, darknet intel. One of the broadest OSINT engines.

| Field | Value |
|-------|-------|
| Category(s) | Deep Search Engine, Deep OSINT / Breaches |
| Classification | **passive** (source: Passive) |
| Integration | api |
| Cost | freemium (Paid, Paid/Freemium) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise, Excellent |
| Pipeline position | Email / username / identity recon; Seed discovery (internet-wide search) |
| Required input | `domain / email / person / username \| domain / org / ip / asn` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> intelx)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain / email / person / username \| domain / org / ip / asn` (per pipeline position).
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

IntelX API, IntelX Tor Search

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Deep Search Engine | Passive | Paid | API | Leaks, archives, darknet intel | Very High | One of the broadest OSINT engines |
| 7 | Deep OSINT / Breaches | Passive | Paid/Freemium | API | Deep leak & darknet intelligence | Very High | Elite OSINT platform |
