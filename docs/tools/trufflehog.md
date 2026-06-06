# TruffleHog

> Provenance: extracted_from_spreadsheet · canonical slug `trufflehog` · 3 source row(s).

**Purpose.** Credential & token hunting. One of the best modern scanners.

| Field | Value |
|-------|-------|
| Category(s) | Secret Scanning |
| Classification | **hybrid** (source: Active, Passive) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise, High |
| Pipeline position | Common recon workflow preset; Source-code & secret recon; URL/dork/index harvesting |
| Required input | `domain (scope) \| domain / live_host / url \| org / domain / keyword` |

## Invocation

```bash
trufflehog <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / live_host / url \| org / domain / keyword` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Source rows disagree on passive/active classification; treated as hybrid.
- Appears in 3 rows across 3 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 4 | Secret Scanning | Passive | Free | CLI/API | Credential & token hunting | Very High | One of the best modern scanners |
| 9 | Secret Scanning | Passive | Free | CLI/API | Deep git history secret hunting | Very High | Excellent entropy + regex detection |
| 19 | Secret Scanning | Active | Free | CLI/API | High-accuracy credential discovery | Very High | Strong entropy + regex detection |
