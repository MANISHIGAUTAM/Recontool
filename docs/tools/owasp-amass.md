# OWASP Amass

> Provenance: extracted_from_spreadsheet · canonical slug `owasp-amass` · 1 source row(s).

**Purpose.** Full attack surface discovery. Same as Amass branding.

| Field | Value |
|-------|-------|
| Category(s) | Attack Surface Mapping |
| Classification | **hybrid** (source: Hybrid) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise |
| Pipeline position | Frameworks & automation (orchestration) |
| Required input | `domain (scope)` |

## Invocation

```bash
owasp-amass <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope)` (per pipeline position).
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
| 14 | Attack Surface Mapping | Hybrid | Free | CLI/API | Full attack surface discovery | Very High | Same as Amass branding |
