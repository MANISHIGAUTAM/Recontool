# FollowerWonk

> Provenance: extracted_from_spreadsheet · canonical slug `followerwonk` · 1 source row(s).

**Purpose.** Twitter bio/account analysis. Less useful after Twitter API restrictions.

| Field | Value |
|-------|-------|
| Category(s) | Twitter/X Analytics |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | freemium (Freemium) |
| Scale | Large |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Social media recon |
| Required input | `username / handle / org` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> followerwonk)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `username / handle / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 8 | Twitter/X Analytics | Passive | Freemium | Web/API | Twitter bio/account analysis | Medium | Less useful after Twitter API restrictions |
