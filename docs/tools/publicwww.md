# PublicWWW

> Provenance: extracted_from_spreadsheet · canonical slug `publicwww` · 4 source row(s).

**Purpose.** JS, analytics, tracking IDs. Extremely underrated recon engine.

| Field | Value |
|-------|-------|
| Category(s) | Source Code Search, Source / Web Fingerprinting, Web Source Search |
| Classification | **passive** (source: Passive) |
| Integration | api, web |
| Cost | freemium (Freemium, Paid/Freemium) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Common recon workflow preset; Seed discovery (internet-wide search); Source-code & secret recon |
| Required input | `domain (scope) \| domain / org / ip / asn \| org / domain / keyword` |

## Invocation

```text
# API integration (fill endpoint/auth in config/tools.yaml -> publicwww)
GET https://<provider-endpoint>/...   # key: see config/recontool.yaml
```
> Invocation template is a placeholder — wire the exact endpoint/flags in `config/tools.yaml` and implement an adapter under `recontool/adapters/`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / org / ip / asn \| org / domain / keyword` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 4 rows across 3 section(s); all memberships preserved.

## Possibly related (not merged)

PublicWWW Historical Search, PublicWWW Source Search

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Source Code Search | Passive | Freemium | Limited API | JS, analytics, tracking IDs | Very High | Extremely underrated recon engine |
| 9 | Source / Web Fingerprinting | Passive | Freemium | Web/API | JS keys, analytics IDs, reused code | High | Very effective for web asset correlation |
| 19 | Web Source Search | Passive | Paid/Freemium | Web/API | Tracking JS keys & web fingerprints | High | Excellent for frontend recon |
| 19 | Web Source Search | Passive | Paid/Freemium | Web/API | Finding leaked cloud references | High | Useful for JS/API key hunting |
